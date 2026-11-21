"""Kernel-certified relabel audit of in-library negatives (mathgraph-6vm).

The time-split run (mathgraph-269, `timesplit.py`) scores every holdout,
deletion and positive docstring query against one control index. A holdout or
deletion query answered at the 10%-coverage threshold counts as a false match.
This module asks a different question. Does the retrieved top-1 T actually
*prove* the held-out theorem H? If it does, the label is wrong, not the
retriever.

The oracle is fixed in the pre-registration
(`sandbox-handoffs/mathgraph-6vm.md`) and runs in the mathlib4 checkout built
at the index pin. It uses the batch template `lean/KAudit.lean`.

* Real check, per (H, T):
  `attribute [-simp] H T in theorem _ : type_of% @H := by intros; first | ...`,
  with the alternatives in `REAL`. Only names that are `[simp]` lemmas are
  erased.
* Null check, per (H, T if T is a simp lemma): the same statement and the same
  erasure, with the alternatives in `NULL`, which never mention T.
* CERTIFIED: the real check closes (its proof term has no `sorryAx`), that
  term uses T and not H, and the null check fails. A theorem that elaborates
  has passed `addDecl`, so the kernel has checked it.

Stages, each writing into `--work`:
`resolve` -> `check` -> `reverse` -> `elab` -> `report` (results/kaudit.json).
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import signal
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .bench_pretrained import wilson
from .timesplit import _jsonl, _rate, clean_doc, halves, score_system, statement

QUERY_ARMS = ("holdout", "deletion", "positive")
NEG = ("holdout", "deletion")
SYSTEMS = (("lexical", "lexical.jsonl"), ("bge-small", "dense.jsonl"))
TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "lean", "KAudit.lean")
HEARTBEATS = 200000            # Lean's default, per declaration
JOBS = 2                       # Lean processes at once (bead resource limit)

# The bead's five alternatives verbatim (K*), then the pre-registered deviations
# (D*). `T ..` leaves T's hypothesis arguments as holes that `exact` refuses,
# so D* hand them to `assumption` from H's own context.
REAL = (("K1", "exact {T} .."),
        ("K2", "exact ({T} ..).symm"),
        ("K3", "exact ({T} ..).1"),
        ("K4", "exact ({T} ..).2"),
        ("K5", "simpa only [] using {T} .."),
        ("D1", "apply {T} <;> assumption"),
        ("D2", "symm; apply {T} <;> assumption"),
        ("D3", "apply ({T} ..).1 <;> assumption"),
        ("D4", "apply ({T} ..).2 <;> assumption"))
NULL = (("N1", "trivial"),
        ("N2", "simp; done"),
        ("N3", "positivity"))

_MSG = re.compile(r"^(?P<file>.*?):(?P<line>\d+):(?P<col>\d+): "
                  r"(?P<sev>error|warning|info)(?:\([^)]*\))?:\s?(?P<msg>.*)$")


# -- Lean batches -----------------------------------------------------------


def check_cmd(cid: str, H: str, T: str, erase: list[str], alts=REAL) -> str:
    """One check on one line: messages map back to it by line number."""
    pre = f"attribute [-simp] {' '.join(erase)} in " if erase else ""
    first = " ".join(f'| kalt "{tag}" ({tac.format(T=T)})' for tag, tac in alts)
    return f"{pre}theorem kaudit.{cid} : type_of% @{H} := by intros; first {first}"


def batch_text(cmds: list[tuple[str, str]], kdump: bool = True) -> tuple[str, dict]:
    """The template plus the commands (each check followed by its `#kdump`
    line), and {line number: (id, line within the command)}. A sentinel at
    the end shows the file was elaborated to the end."""
    with open(TEMPLATE, encoding="utf-8") as fh:
        head = fh.read().rstrip("\n") + f"\n\nset_option maxHeartbeats {HEARTBEATS}\n"
    line, body, at = head.count("\n") + 1, [], {}
    for cid, cmd in cmds:
        for k in range(cmd.count("\n") + 1):
            at[line + k] = (cid, k)
        line += cmd.count("\n") + 1
        body.append(cmd)
        if kdump:
            body.append(f"#kdump kaudit.{cid}")
            line += 1
    body += ["theorem kaudit.end : True := trivial", "#kdump kaudit.end"]
    return head + "\n".join(body) + "\n", at


def run_lean(text: str, path: str, mathlib: str, timeout: float,
             stall: float = 1800) -> tuple[str, list[str], float, str | None]:
    """Elaborate `text` as `path` from inside the built checkout. Returns the
    log, the `.kdump.jsonl` lines, the seconds taken and why the process was
    killed, if it was. The process group is killed after `timeout` seconds,
    or once neither file has grown for `stall` seconds. The stall limit is
    longer than the import, which prints nothing."""
    path = os.path.abspath(path)
    log, dump = path[:-len(".lean")] + ".log", path + ".kdump.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    if os.path.exists(dump):
        os.unlink(dump)
    size = lambda f: os.path.getsize(f) if os.path.exists(f) else 0
    t0 = last = time.time()
    seen, killed = 0, None
    with open(log, "w", encoding="utf-8") as out:
        # maxErrors 0: most checks fail by design, and Lean exits at 100 errors
        p = subprocess.Popen(["lake", "env", "lean", "-DmaxErrors=0", path], cwd=mathlib, stdout=out,
                             stderr=subprocess.STDOUT, start_new_session=True)
        while p.poll() is None:
            time.sleep(5)
            now = size(log) + size(dump)
            if now != seen:
                seen, last = now, time.time()
            killed = ("timeout" if time.time() - t0 > timeout
                      else "stall" if time.time() - last > stall else None)
            if killed:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
    with open(log, encoding="utf-8") as fh:
        text_log = fh.read()
    lines = []
    if os.path.exists(dump):
        with open(dump, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    return text_log, lines, time.time() - t0, killed


def messages(log: str, path: str) -> list[tuple[int, str, str]]:
    """(line, severity, first line of text) of every message about `path`."""
    path = os.path.abspath(path)
    return [(int(m["line"]), m["sev"], m["msg"]) for ln in log.splitlines()
            if (m := _MSG.match(ln)) and m["file"] == path]


def parse_checks(log: str, path: str, at: dict, dump: list[str]) -> dict:
    """{id: {closed, used, absent, tag, error}} from one batch. Closure, used
    constants and the closing alternative come from the dump file, errors from
    the log. An id with no `closed` was not reached."""
    res: dict[str, dict] = {}
    tag = None
    for ln in dump:
        try:
            d = json.loads(ln)
        except ValueError:          # a line cut short by a crash
            continue
        if "tag" in d:
            tag = d["tag"]
            continue
        r = res.setdefault(d["kdump"].removeprefix("kaudit."), {})
        r["absent"] = d.get("absent", False)
        r["used"] = d.get("used", [])
        r["closed"] = not r["absent"] and "sorryAx" not in r["used"]
        if "ms" in d:
            r["ms"] = d["ms"]
        if tag:
            r["tag"], tag = tag, None
    for line, sev, msg in messages(log, path):
        if sev == "error" and line in at:
            cid, k = at[line]
            r = res.setdefault(cid, {})
            r.setdefault("error", msg[:300])
            r.setdefault("errors", {}).setdefault(k, msg[:300])
    return res


def run_batches(cmds: list[tuple[str, str]], work: str, stem: str, mathlib: str,
                jobs: int = JOBS, timeout: float = 8 * 3600, kdump: bool = True,
                rounds: int = 4) -> dict:
    """Deal `cmds` round-robin into `jobs` files, run them at once, and merge the
    parsed results.

    If a file dies before its end, the first check without a result is
    recorded as `crashed` and the rest are run again. This needs `kdump`,
    since otherwise a command leaves no trace of its own. A timeout ends the
    run instead: the budget is spent."""
    out, info, crashed, todo = {}, [], [], list(cmds)
    for rnd in range(rounds):
        parts = [p for p in (todo[i::jobs] for i in range(jobs)) if p]

        def one(i):
            path = os.path.join(work, f"{stem}{i}" + (f"r{rnd}" if rnd else "") + ".lean")
            text, at = batch_text(parts[i], kdump)
            return (at, path) + run_lean(text, path, mathlib, timeout)

        with ThreadPoolExecutor(max_workers=len(parts)) as ex:
            for part, (at, path, log, dump, secs, killed) in zip(
                    parts, ex.map(one, range(len(parts)))):
                res = parse_checks(log, path, at, dump)
                done = res.pop("end", {}).get("closed", False)
                out.update(res)
                t = [r["ms"] for r in res.values() if "ms" in r]     # in dump order
                ms = sorted(b - a for a, b in zip(t, t[1:]))
                info.append({"file": os.path.basename(path), "commands": len(part),
                             "seconds": round(secs, 1), "completed": done, "killed": killed,
                             "check_ms_median_p90_max": [ms[len(ms) // 2], ms[9 * len(ms) // 10],
                                                         ms[-1]] if ms else None})
                if not done and kdump and killed != "timeout":
                    first = next((c for c, _ in part if "closed" not in out.get(c, {})), None)
                    if first:
                        crashed.append(first)
        if not kdump or all(b["completed"] or b["killed"] == "timeout"
                            for b in info[-len(parts):]):
            break
        todo = [(c, t) for c, t in cmds if "closed" not in out.get(c, {}) and c not in crashed]
        if not todo:
            break
    return {"results": out, "batches": info, "crashed": crashed}


# -- units: one per (system, query) -----------------------------------------


def load_units(src: str, seed: int = 0) -> tuple[list[dict], dict]:
    """Every holdout, deletion and positive query of both systems, with its
    top-1, score, whether it is answered at the 10%-coverage threshold that
    `timesplit.score_system` fits, and which half it is in."""
    units, taus = [], {}
    for system, fname in SYSTEMS:
        recs = [r for r in _jsonl(os.path.join(src, fname)) if r["corpus"] == "ctrl"]
        s = score_system(recs, seed)
        ans, taus[system] = s["answered"], s["threshold"]
        for a in QUERY_ARMS:
            ev = halves([r["name"] for r in recs if r["arm"] == a], seed)[1]
            units += [{"system": system, "arm": a, "H": r["name"], "T": r["top1"],
                       "score": r["score"], "above": bool(ans(r)),
                       "half": "eval" if r["name"] in ev else "fit"}
                      for r in recs if r["arm"] == a]
    return units, taus


def name_modules(src: str) -> dict[str, str]:
    """Name -> module for every query and every control-index row, the modules
    a private name is resolved against."""
    from .index import load
    mods = {}
    for r in load(os.path.join(src, "idx_ctrl"))["rows"]:
        mods.setdefault(r["name"], r["module"])
    for r in _jsonl(os.path.join(src, "arms.jsonl")):
        mods.setdefault(r["name"], r["module"])
    return mods


def resolve(units: list[dict], mods: dict, work: str, mathlib: str) -> dict:
    names = {n for u in units for n in (u["H"], u["T"]) if n}
    tsv = os.path.abspath(os.path.join(work, "names.tsv"))
    facts = os.path.abspath(os.path.join(work, "facts.jsonl"))
    with open(tsv, "w", encoding="utf-8") as fh:
        for n in sorted(names):
            fh.write(f"{n}\t{mods.get(n, '')}\n")
    text, _ = batch_text([("resolve", f'#kresolve "{tsv}" "{facts}"')], kdump=False)
    log, _, secs, _ = run_lean(text, os.path.join(work, "resolve.lean"), mathlib, 3 * 3600)
    errors = [m for m in messages(log, os.path.join(work, "resolve.lean")) if m[1] == "error"]
    if errors:
        raise RuntimeError(f"#kresolve failed: {errors[:3]}")
    return {"names": len(names), "seconds": round(secs, 1)}


def status(u: dict, facts: dict) -> str:
    """checked, gold (a positive whose top-1 is itself), or why not checked."""
    if not u["T"]:
        return "no_top1"
    if u["T"] == u["H"]:
        return "gold"
    for role in ("H", "T"):
        f = facts.get(u[role], {})
        if "const" not in f:
            return f"{role}_missing"
        if f["private"]:
            return f"{role}_private"
    return "checked"


def _erase(facts: dict, *names: str) -> list[str]:
    return [facts[n]["const"] for n in names if facts[n]["simp"]]


def plan(units: list[dict], facts: dict, which=("eval",)) -> tuple[list, list]:
    """Number the distinct real checks (H, T) of the units in the halves
    `which`, gate population first so a partial run still answers the kill
    test. The pre-registered run is the eval halves only; the fit halves would
    double the compute and no number needs them."""
    order = sorted(units, key=lambda u: (not (u["arm"] in NEG and u["half"] == "eval"),
                                         u["system"], u["arm"], u["H"]))
    real = {}
    for u in order:
        u["status"] = status(u, facts) if u["half"] in which else "not_planned"
        if u["status"] == "checked":
            u["cid"] = real.setdefault((u["H"], u["T"]), f"c{len(real)}")
    cmds = [(cid, check_cmd(cid, facts[H]["const"], facts[T]["const"], _erase(facts, H, T)))
            for (H, T), cid in real.items()]
    return cmds, order


def plan_followup(units: list[dict], facts: dict, real: dict) -> list[tuple[str, str]]:
    """Null checks (per H, and T when T is a simp lemma) and reverse checks
    (does H prove T?) for every pair whose real check closed. Only these need
    them, since a pair that does not close cannot be certified."""
    nulls, revs = {}, {}
    # canonical order: the ids must not depend on how the caller sorted units
    for u in sorted(units, key=lambda u: (u["H"], u["T"] or "", u["system"], u["arm"])):
        if u.get("status") == "checked" and real.get(u["cid"], {}).get("closed"):
            H, T = u["H"], u["T"]
            key = (H, T if facts[T]["simp"] else None)
            u["nid"] = nulls.setdefault(key, f"n{len(nulls)}")
            u["rid"] = revs.setdefault((H, T), f"r{len(revs)}")
    return ([(nid, check_cmd(nid, facts[H]["const"], "", _erase(facts, H, *([T] if T else [])), NULL))
             for (H, T), nid in nulls.items()]
            + [(rid, check_cmd(rid, facts[T]["const"], facts[H]["const"], _erase(facts, H, T)))
               for (H, T), rid in revs.items()])


def certify(units: list[dict], facts: dict, real: dict, follow: dict | None = None) -> None:
    """CERTIFIED: the real check closes, its term uses T and not H, and the
    null fails. EQUIV: the reverse check closes, using H and not T."""
    follow = follow or {}
    for u in units:
        u["certified"] = False
        if u.get("status") != "checked":
            continue
        r = real.get(u["cid"], {})
        if "closed" not in r:
            u["status"] = "not_run"
            continue
        H, T = facts[u["H"]]["const"], facts[u["T"]]["const"]
        u.update(closed=r["closed"], tag=r.get("tag"), uses_T=T in r["used"],
                 uses_H=H in r["used"], null_closed=None,
                 timeout="maximum number of heartbeats" in (r.get("error") or ""))
        if not r["closed"]:
            continue
        n = follow.get(u.get("nid"), {})
        if "closed" not in n:
            u["status"] = "null_not_run"
            continue
        u.update(null_closed=n["closed"], null_tag=n.get("tag"))
        u["certified"] = u["uses_T"] and not u["uses_H"] and not n["closed"]
        v = follow.get(u.get("rid"), {})
        u["equiv"] = None if "closed" not in v else bool(
            v["closed"] and H in v["used"] and T not in v["used"])


# -- time arm: do its heads elaborate at PIN? -------------------------------


def elab_cmds(rows: list[dict]) -> tuple[list[tuple[str, str]], dict]:
    """Each time-arm head as `example <statement> := sorry` in the declaration's
    namespace, once with autoImplicit off (mathlib's setting) and once on (a
    crude stand-in for the `variable` lines a head cannot carry)."""
    cmds = []
    for i, r in enumerate(rows):
        ns = r["name"].rpartition(".")[0]
        stmt = re.sub(r"\s+where$", "", statement(r["head"]))
        cmds.append((f"e{i}", "\n".join([
            f"namespace {ns}" if ns else "section",
            f"set_option autoImplicit false in example {stmt} := sorry",
            "set_option autoImplicit true in set_option relaxedAutoImplicit true in "
            f"example {stmt} := sorry",
            f"end {ns}" if ns else "end"])))
    return cmds, {f"e{i}": r["name"] for i, r in enumerate(rows)}


def error_kind(msg: str) -> str:
    m = msg.lower()
    for kind, pat in (("unknown name", r"unknown (identifier|constant|namespace)"),
                      ("universe", r"universe"),
                      ("instance", r"failed to synthesize"),
                      ("syntax", r"unexpected|expected")):
        if re.search(pat, m):
            return kind
    return "other"


# -- report -----------------------------------------------------------------


def newcombe(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float]:
    """95% interval for p1 - p2 from the two Wilson intervals (Newcombe's
    hybrid score method)."""
    p1, p2 = k1 / n1, k2 / n2
    (l1, u1), (l2, u2) = wilson(k1, n1), wilson(k2, n2)
    d = p1 - p2
    return d - math.hypot(p1 - l1, u2 - p2), d + math.hypot(u1 - p1, p2 - l2)


def auroc(pos: list[float], neg: list[float]) -> float | None:
    """P(score of a positive > score of a negative), ties counted half."""
    if not pos or not neg:
        return None
    xs = sorted([(s, 1) for s in pos] + [(s, 0) for s in neg])
    rank_sum, i = 0.0, 0
    while i < len(xs):
        j = i
        while j < len(xs) and xs[j][0] == xs[i][0]:
            j += 1
        rank_sum += (i + j + 1) / 2 * sum(lab for _, lab in xs[i:j])
        i = j
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def auroc_ci(pos: list[float], neg: list[float], b: int = 1000, seed: int = 0) -> dict:
    a = auroc(pos, neg)
    if a is None:
        return {"auroc": None, "n_pos": len(pos), "n_neg": len(neg)}
    rng = random.Random(seed)
    boot = sorted(auroc(rng.choices(pos, k=len(pos)), rng.choices(neg, k=len(neg)))
                  for _ in range(b))
    return {"auroc": round(a, 4), "bootstrap95": [round(boot[int(0.025 * b)], 4),
                                                  round(boot[int(0.975 * b) - 1], 4)],
            "n_pos": len(pos), "n_neg": len(neg)}


def _certified_rate(us: list[dict]) -> dict:
    return _rate(sum(u["certified"] for u in us), len(us))


def gate(units: list[dict]) -> dict:
    """The pre-registered kill test on eval-half holdout+deletion units, both
    systems pooled. (a) KILL if the Wilson upper bound of the certified rate
    above tau is below 15%. (b) KILL if the above-minus-below gap is 5 pp or
    less (point estimate)."""
    ev = [u for u in units if u["arm"] in NEG and u["half"] == "eval"]
    out = {}
    for label, us in (("checked", [u for u in ev if u["status"] == "checked"]),
                      ("all_units_unchecked_as_not_certified", ev)):
        above = [u for u in us if u["above"]]
        below = [u for u in us if not u["above"]]
        ka, kb = sum(u["certified"] for u in above), sum(u["certified"] for u in below)
        ua = wilson(ka, len(above))[1]
        gap = ka / len(above) - kb / len(below)
        lo, hi = newcombe(ka, len(above), kb, len(below))
        out[label] = {
            "above_tau": _rate(ka, len(above)), "below_tau": _rate(kb, len(below)),
            "a_wilson_upper": round(ua, 4), "a_kill": ua < 0.15,
            "b_gap": round(gap, 4), "b_gap_newcombe95": [round(lo, 4), round(hi, 4)],
            "b_kill": gap <= 0.05,
            "by_system_arm_above": {f"{s}/{a}": _certified_rate(
                [u for u in above if u["system"] == s and u["arm"] == a])
                for s, _ in SYSTEMS for a in NEG}}
    p = out["checked"]
    out["verdict"] = "KILL" if p["a_kill"] or p["b_kill"] else "SURVIVES"
    return out


def relabel(units: list[dict], seed: int = 0) -> dict:
    """FMR, positive precision and AUROC on eval halves, before and after the
    symmetric relabel. Under the relabel, a top-1 that certifiably proves H is
    a correct answer, for negatives and positives alike."""
    out = {}
    for s, _ in SYSTEMS:
        us = [u for u in units if u["system"] == s]
        gold = lambda u: u["arm"] == "positive" and u["T"] == u["H"]
        ok = lambda u: gold(u) or u["certified"]
        ev = [u for u in us if u["half"] == "eval"]
        r = {}
        for a in NEG:
            xs = [u for u in ev if u["arm"] == a]
            r[a] = {"fmr_before": _rate(sum(u["above"] for u in xs), len(xs)),
                    "fmr_after": _rate(sum(u["above"] and not u["certified"] for u in xs),
                                       len(xs))}
        ans = [u for u in ev if u["arm"] == "positive" and u["above"]]
        r["positive_precision"] = {"before": _rate(sum(map(gold, ans)), len(ans)),
                                   "after": _rate(sum(map(ok, ans)), len(ans))}
        pos = [u for u in ev if u["arm"] == "positive"]
        neg = [u for u in ev if u["arm"] in NEG]
        r["auroc_correct_positives_vs_negatives"] = {
            "before": auroc_ci([u["score"] for u in pos if gold(u)],
                               [u["score"] for u in neg], seed=seed),
            "after": auroc_ci([u["score"] for u in pos + neg if ok(u)],
                              [u["score"] for u in neg if not u["certified"]], seed=seed)}
        r["auroc_correct_vs_incorrect"] = {
            "before": auroc_ci([u["score"] for u in pos + neg if gold(u)],
                               [u["score"] for u in pos + neg if not gold(u)], seed=seed),
            "after": auroc_ci([u["score"] for u in pos + neg if ok(u)],
                              [u["score"] for u in pos + neg if not ok(u)], seed=seed)}
        out[s] = r
    return out


def breakdowns(units: list[dict], facts: dict, dup: set) -> dict:
    chk = [u for u in units if u["status"] == "checked"]
    gate_pop = [u for u in chk if u["arm"] in NEG and u["half"] == "eval"]
    cert = [u for u in chk if u["certified"]]
    c = lambda us: {"units": len(us), "closed": sum(u["closed"] for u in us),
                    "certified": sum(u["certified"] for u in us)}
    add = [u for u in chk if facts[u["T"]].get("additive") == facts[u["H"]]["const"]
           or facts[u["H"]].get("additive") == facts[u["T"]]["const"]]
    dep = [u for u in chk if facts[u["T"]]["deprecated"]]
    return {
        "status": {f"{s}/{a}": dict(Counter(u["status"] for u in units
                                            if u["system"] == s and u["arm"] == a))
                   for s, _ in SYSTEMS for a in QUERY_ARMS},
        "closing_alternative": dict(Counter(u["tag"] for u in chk if u["closed"])),
        "heartbeat_timeouts": {"gate_population": sum(u["timeout"] for u in gate_pop),
                               "all_checked": sum(u["timeout"] for u in chk)},
        "certified_by_alternative": dict(Counter(u["tag"] for u in cert)),
        "closed_but_not_certified": dict(Counter(
            "null closes" if u["null_closed"] else "uses H" if u["uses_H"] else "no T"
            for u in chk if u["closed"] and not u["certified"])),
        "null_closes_among_closed": {
            "gate_population": _rate(sum(bool(u["null_closed"]) for u in gate_pop if u["closed"]),
                                     sum(u["closed"] for u in gate_pop)),
            "all_checked": _rate(sum(bool(u["null_closed"]) for u in chk if u["closed"]),
                                 sum(u["closed"] for u in chk))},
        "kernel_equiv_vs_implies": dict(Counter(
            "EQUIV" if u.get("equiv") else "IMPLIES" if u.get("equiv") is False
            else "not run" for u in cert)),
        "to_additive_map": {"metadata_only": "a to_additive twin is not a kernel proof",
                            **c(add), "above_tau_eval_neg": c(
                                [u for u in add if u in gate_pop and u["above"]])},
        "deprecated_top1": {**c(dep), "alias_of_H": sum(
            facts[u["T"]].get("new_name") == facts[u["H"]]["const"] for u in dep)},
        "verbatim_sibling_docstring": {
            "dup": c([u for u in gate_pop if (u["arm"], u["H"]) in dup]),
            "not_dup": c([u for u in gate_pop if (u["arm"], u["H"]) not in dup]),
            "dup_above_tau": c([u for u in gate_pop if (u["arm"], u["H"]) in dup
                                and u["above"]]),
            "not_dup_above_tau": c([u for u in gate_pop if (u["arm"], u["H"]) not in dup
                                    and u["above"]])},
    }


def hand_check_sample(units: list[dict], facts: dict, n: int = 20, seed: int = 0) -> list:
    """Certified pairs to read for vacuity, from the gate population first."""
    def pairs(us):
        return sorted({(u["H"], u["T"]): u for u in us}.items())
    cert = [u for u in units if u["certified"]]
    first = pairs([u for u in cert if u["arm"] in NEG and u["half"] == "eval" and u["above"]])
    rest = [p for p in pairs(cert) if p not in first]
    rng = random.Random(seed)
    pick = rng.sample(first, min(n, len(first)))
    pick += rng.sample(rest, min(n - len(pick), len(rest)))
    return [{"H": H, "T": T, "system": u["system"], "arm": u["arm"], "above": u["above"],
             "tag": u["tag"], "equiv": u.get("equiv"),
             "H_type": facts[H].get("type"), "T_type": facts[T].get("type")}
            for (H, T), u in pick]


def verbatim_dups(src: str) -> set:
    """(arm, name) of negatives whose docstring sits verbatim on a row that
    stayed indexed, as timesplit.report counts them."""
    from .index import load
    docs = Counter(clean_doc(r["doc"]) for r in load(os.path.join(src, "idx_ctrl"))["rows"]
                   if r.get("doc"))
    return {(a["arm"], a["name"]) for a in _jsonl(os.path.join(src, "arms.jsonl"))
            if a["arm"] in NEG and docs[a["query"]]}


# -- CLI --------------------------------------------------------------------


def _load(work: str, name: str):
    with open(os.path.join(work, name), encoding="utf-8") as fh:
        return json.load(fh)


def _save(work: str, name: str, obj) -> None:
    with open(os.path.join(work, name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)


def _facts(work: str) -> dict:
    return {f["name"]: f for f in _jsonl(os.path.join(work, "facts.jsonl"))}


def main(argv=None) -> None:
    import argparse
    p = argparse.ArgumentParser(prog="python -m mathgraph.kaudit")
    p.add_argument("stage", choices=["resolve", "check", "followup", "elab", "report"])
    data = os.environ.get("MATHGRAPH_DATA", "./mathgraph-data")
    p.add_argument("--src", default=os.path.join(data, "hctz-timesplit"),
                   help="timesplit outputs (arms, lexical, dense, idx_ctrl); read only")
    p.add_argument("--mathlib", default=os.path.join(data, "mathlib4"),
                   help="mathlib4 checkout built at the index pin")
    p.add_argument("--work", default="./mathgraph-data/kaudit")
    p.add_argument("--results", default="results/kaudit.json")
    p.add_argument("--jobs", type=int, default=JOBS)
    p.add_argument("--halves", choices=["eval", "all"], default="eval")
    a = p.parse_args(argv)
    which = ("eval",) if a.halves == "eval" else ("eval", "fit")
    os.makedirs(a.work, exist_ok=True)
    units, taus = load_units(a.src)
    if a.stage == "resolve":
        print(json.dumps(resolve(units, name_modules(a.src), a.work, a.mathlib)))
    elif a.stage == "check":
        cmds, _ = plan(units, _facts(a.work), which)
        _save(a.work, "checks.json", run_batches(cmds, a.work, "check", a.mathlib, a.jobs,
                                                 timeout=3 * 3600))    # pre-registered bound
    elif a.stage == "followup":
        facts = _facts(a.work)
        plan(units, facts, which)
        cmds = plan_followup(units, facts, _load(a.work, "checks.json")["results"])
        _save(a.work, "followup.json", run_batches(cmds, a.work, "followup", a.mathlib, a.jobs))
    elif a.stage == "elab":
        rows = [r for r in _jsonl(os.path.join(a.src, "arms.jsonl")) if r["arm"] == "time"]
        cmds, ids = elab_cmds(rows)
        out = run_batches(cmds, a.work, "elab", a.mathlib, a.jobs, timeout=3 * 3600,
                          kdump=False)
        # An example adds no constant, so only errors are recorded. A variant
        # with no error on its line (1 strict, 2 auto) elaborated, provided its
        # batch completed.
        done = all(b["completed"] for b in out["batches"])
        res = {f"{i}{v[0]}": {"name": n, "variant": v,
                              "error": out["results"].get(i, {}).get("errors", {}).get(k)}
               for i, n in ids.items() for k, v in ((1, "strict"), (2, "auto"))}
        _save(a.work, "elab.json", {"completed": done, "batches": out["batches"],
                                    "results": res})
    else:
        facts = _facts(a.work)
        _, units = plan(units, facts, which)
        checks = _load(a.work, "checks.json")
        fol = _load(a.work, "followup.json")
        plan_followup(units, facts, checks["results"])
        certify(units, facts, checks["results"], fol["results"])
        el = _load(a.work, "elab.json")
        res = {"bead": "mathgraph-6vm", "protocol": "sandbox-handoffs/mathgraph-6vm.md",
               "pin": "b44f89d15d463ede557bdf673707a8610210becf",
               "lean": "leanprover/lean4:v4.33.0-rc1",
               "oracle": {"real": dict(REAL), "null": dict(NULL),
                          "max_heartbeats": HEARTBEATS},
               "thresholds": taus,
               "crashed": {"check": checks["crashed"], "followup": fol["crashed"]},
               "batches": {"check": checks["batches"],
                           "followup": fol["batches"],
                           "elab": el["batches"]},
               "gate": gate(units),
               "relabel": relabel(units),
               "breakdowns": breakdowns(units, facts, verbatim_dups(a.src)),
               "time_arm_elaboration": {
                   v: {"failed": _rate(sum(r["error"] is not None for r in el["results"].values()
                                           if r["variant"] == v),
                                       sum(r["variant"] == v for r in el["results"].values())),
                       "by_error": dict(Counter(error_kind(r["error"])
                                                for r in el["results"].values()
                                                if r["variant"] == v and r["error"]))}
                   for v in ("strict", "auto")},
               "certified_pairs": sorted({(u["H"], u["T"]) for u in units if u["certified"]}),
               "hand_check": hand_check_sample(units, facts)}
        res["time_arm_elaboration"]["completed"] = el["completed"]
        with open(a.results, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(json.dumps({"gate": res["gate"]["verdict"]}, indent=2))


if __name__ == "__main__":
    main()
