"""Time-split negative arm (mathgraph-269).

Theorems added to mathlib after the index pin are absent from every index built
at the pin, so their docstrings are mechanically labelled negatives: the only
correct answer is to abstain. The question is whether they are *harder*
negatives -- near misses -- than the ones the repo can already make.

The absent set is scanner-vs-scanner: names leanscan finds at NOV and finds
neither by scanning PIN nor in the elaborated PIN environment, restricted to
declarations whose own line is an added line of `git diff PIN NOV -- Mathlib`.
A scanner phantom present at both commits (mathgraph-dem.2) cancels in the set
difference, and a phantom created by an unchanged line is excluded by the diff.

Protocol, fixed before any retrieval number was looked at:

* Arms. Every query is a theorem docstring. `time`: the absent set. `holdout`:
  `index.build(holdout_frac)` random holdouts. `deletion`: PIN theorems whose
  name, statement and docstring are unchanged at NOV, removed from the index
  with their to_additive twins. `positive`: `pmi_holdout_frac` probes, kept to
  source theorems with no to_additive twin and a docstring no other row shares.
  All four run against one control index (PIN minus the holdouts and
  deletions) -- lexically through `Aligner(**LEX)`, densely through
  bge-small-en-v1.5 over the same rows of the cached corpus embedding. The
  positives' own rows are re-embedded without their docstrings, the dense
  analogue of withholding them from PMI.
* Scores. Lexical answers on `coverage`, dense on top-1 cosine. GRAPH_THRESHOLDS
  (coverage and margin) are also reported, lexical only, on whole arms.
* The 10%-coverage threshold. Every arm is split in half (seed 0). On the fit
  halves, each arm is subsampled to the smallest one's size, pooled, and the
  threshold is the score answering 10% of the pool. Rates are measured on the
  eval halves.
* Kill test (the bead's), at that threshold on the eval halves: the time arm
  survives against a control if its false-match rate exceeds the control's by
  more than the half-width of its own Wilson 95% interval. It must survive
  against both controls for both systems, otherwise it is killed.
"""

from __future__ import annotations

import csv
import json
import math
import os
import random
import re
import subprocess
from collections import Counter

from .leanscan import DECL_RE, scan_tree
from .names import explicit_additive_name, parse_to_additive_attr, to_additive_name

PIN = "b44f89d15d463ede557bdf673707a8610210becf"       # the index pin, 2026-07-26
NOV = "d9a3e61fb84eff4c6bded19e8fbf7138f8890816"       # mathlib's master-2026-11-15 tag
PIN_DATE = "2026-07-26"
ARMS = ("positive", "time", "holdout", "deletion")
COVERAGE = 0.10
MODEL = "BAAI/bge-small-en-v1.5"

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_SINCE = re.compile(r'since\s*:=\s*"(\d{4}-\d{2}-\d{2})"')
_DEP_TARGET = re.compile(r"deprecated\s+([A-Za-z_][^\s(\]]*)")
_ALIAS_TARGET = re.compile(r":=\s*([A-Za-z_][^\s]*)")
_VERSO_ROLE = re.compile(r"\{[A-Za-z]+\}(?=`)")
_TEX = re.compile(r"\$([^$]+)\$")


# -- the absent set ---------------------------------------------------------


def added_lines(repo: str, a: str = PIN, b: str = NOV) -> dict[str, set[int]]:
    """Path -> line numbers (in `b`) that `git diff a b` marks as added."""
    out = subprocess.run(["git", "-C", repo, "diff", "--no-renames", "-U0", a, b,
                          "--", "Mathlib"], capture_output=True, text=True,
                         check=True).stdout
    added: dict[str, set[int]] = {}
    path = None
    for ln in out.splitlines():
        if ln.startswith("+++ "):
            path = ln[6:] if ln.startswith("+++ b/") else None
        elif path and (m := _HUNK.match(ln)):
            start, n = int(m.group(1)), int(m.group(2) or 1)
            added.setdefault(path, set()).update(range(start, start + n))
    return added


def truncated(head: str) -> bool:
    """leanscan's identifier class stops at characters such as `ℝ` or `ᵢ` and
    keeps a universe binder's dot, so `compₘ` scans as `comp` and `univ.{u}` as
    `univ.` (mathgraph-dem.2). Whatever follows a whole name is a delimiter."""
    m = DECL_RE.match(head)
    if not m:
        return False
    nxt = head[m.end():m.end() + 1]
    return m.group("name").endswith(".") or not (
        nxt == "" or nxt.isspace() or nxt in ":({[⦃")


def statement(head: str) -> str:
    """The scanned head minus its keyword, name and body, whitespace-collapsed."""
    m = DECL_RE.match(head)
    s = head[m.end():] if m else head
    return " ".join(s.split(":=", 1)[0].split())


def clean_doc(doc: str) -> str:
    """Docstring as a query. Verso docstrings (on in 1,356 NOV files, none at
    PIN) prefix code spans with a role, {name}`Foo`; drop the role so it does
    not reach the query as the English word "name"."""
    return _VERSO_ROLE.sub("", doc or "").strip()


def path_of(module: str) -> str:
    return module.replace(".", "/") + ".lean"


def deprecated_targets(rows, added: dict[str, set[int]], tree: str) -> set[str]:
    """Every name a window deprecation could resolve to. A renamed theorem gets
    a new name and a deprecated alias from the old one, so its new name is not
    a new theorem. Lean resolves the target against each enclosing namespace,
    so every one of those readings is returned; over-removal only costs
    negatives."""
    out = set()
    for r in rows:
        if "deprecated" not in r["attrs"]:
            continue
        since = _SINCE.search(r["attrs"])
        if not (r["line"] in added.get(path_of(r["module"]), ())
                or (since and since.group(1) >= PIN_DATE)):
            continue
        text = r["head"]
        if r["kind"] == "alias" and not _ALIAS_TARGET.search(text):
            # leanscan stops a head at the line holding `:=`, and 510 NOV
            # aliases put their target on the next line
            with open(os.path.join(tree, path_of(r["module"])), encoding="utf-8") as fh:
                text = " ".join(fh.read().splitlines()[r["line"] - 1:r["line"] + 2])
        m = (_ALIAS_TARGET.search(text) if r["kind"] == "alias"
             else _DEP_TARGET.search(r["attrs"]))
        if not m:
            continue
        t = m.group(1).rstrip(",")
        if t.startswith("_root_."):
            out.add(t[len("_root_."):])
            continue
        parts = r["namespace"].split(".") if r["namespace"] else []
        out.update(".".join(parts[:i] + [t]) for i in range(len(parts) + 1))
    return out


def absent_set(nov_rows: list[dict], pin_rows: list[dict], elab_names: set[str],
               added: dict[str, set[int]], nov_tree: str) -> tuple[list[dict], dict]:
    """The time-split negatives, and how many each filter kept (in order)."""
    pin_names = {r["name"] for r in pin_rows}
    pin_stmts = {statement(r["head"]) for r in pin_rows}
    dep = deprecated_targets(nov_rows, added, nov_tree)
    steps = [
        ("theorem", lambda r: r["kind"] == "theorem"),
        ("not in leanscan(PIN) or elab(PIN)",
         lambda r: r["name"] not in pin_names and r["name"] not in elab_names),
        ("declaration line added in the diff",
         lambda r: r["line"] in added.get(path_of(r["module"]), ())),
        ("no _root_", lambda r: "_root_" not in r["name"]),
        ("not truncated", lambda r: not truncated(r["head"])),
        ("not a window deprecation target", lambda r: r["name"] not in dep),
        ("statement differs from every PIN statement",
         lambda r: statement(r["head"]) not in pin_stmts),
        ("has a docstring", lambda r: bool(clean_doc(r["doc"]))),
    ]
    kept, counts = nov_rows, {"leanscan(NOV)": len(nov_rows)}
    for label, keep in steps:
        kept = [r for r in kept if keep(r)]
        counts[label] = len(kept)
    seen = Counter(r["name"] for r in kept)
    kept = [r for r in kept if seen[r["name"]] == 1]  # a name scanned twice is ambiguous
    counts["unique name"] = len(kept)
    return kept, counts


def unchanged(pin_rows: list[dict], nov_rows: list[dict]) -> list[dict]:
    """PIN docstring theorems whose name, statement and docstring are the same
    at NOV, with the scanner artefacts the time arm drops dropped here too."""
    nov = {}
    for r in nov_rows:
        nov.setdefault(r["name"], []).append(r)
    once = Counter(r["name"] for r in pin_rows)
    out = []
    for r in pin_rows:
        later = nov.get(r["name"], [])
        if (r["kind"] == "theorem" and clean_doc(r["doc"]) and once[r["name"]] == 1
                and "_root_" not in r["name"] and not truncated(r["head"])
                and len(later) == 1 and "deprecated" not in later[0]["attrs"]
                and statement(later[0]["head"]) == statement(r["head"])
                and clean_doc(later[0]["doc"]) == clean_doc(r["doc"])):
            out.append(r)
    return out


def twin(r: dict) -> str | None:
    """The name `@[to_additive]` gives this row's twin, as index.build reads it."""
    has, explicit = parse_to_additive_attr(r.get("attrs", ""))
    if not has:
        return None
    return explicit_additive_name(r["name"], explicit) if explicit else to_additive_name(r["name"])


def scan(tree: str) -> list[dict]:
    return [d.to_json() for d in scan_tree(os.path.join(tree, "Mathlib"))]


# -- arms -------------------------------------------------------------------


def _jsonl(path, rows=None):
    if rows is None:
        with open(path, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh]
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def build_arms(data: str, nov_tree: str, out: str, frac: float = 0.06,
               seed: int = 0) -> dict:
    from .index import build, find_ground_truth, load
    art = os.path.join(data, "artifacts")
    os.makedirs(out, exist_ok=True)
    truth = find_ground_truth(art)
    pin, nov = scan(os.path.join(data, "mathlib4")), scan(nov_tree)
    time_rows, funnel = absent_set(nov, pin, truth.names, added_lines(nov_tree), nov_tree)

    pool = unchanged(pin, nov)
    gold = random.Random(seed).sample(pool, len(time_rows))
    drop = {g["name"] for g in gold} | {t for g in gold if (t := twin(g))}
    raw = os.path.join(out, "ctrl_raw.jsonl")
    _jsonl(raw, [r for r in pin if r["name"] not in drop])
    ctrl = os.path.join(out, "idx_ctrl")
    meta = build(raw, ctrl, holdout_frac=frac, pmi_holdout_frac=frac, seed=seed,
                 truth=truth)
    os.unlink(raw)
    rows = load(ctrl)["rows"]
    present = {r["name"] for r in rows}
    docs = Counter(clean_doc(r["doc"]) for r in rows if r.get("doc"))

    def q(arm, r):
        return {"arm": arm, "name": r["name"], "module": r["module"],
                "line": r["line"], "query": clean_doc(r["doc"]), "head": r["head"]}

    theorems = lambda rs: [r for r in rs if r["kind"] == "theorem" and clean_doc(r["doc"])]
    arms = ([q("time", r) for r in time_rows]
            + [q("holdout", r) for r in theorems(_jsonl(os.path.join(ctrl, "holdout.jsonl")))]
            + [q("deletion", r) for r in gold]
            + [q("positive", r) for r in theorems(_jsonl(os.path.join(ctrl, "devpos.jsonl")))
               if r.get("provenance", "source") == "source"
               and "to_additive" not in r.get("attrs", "")
               and docs[clean_doc(r["doc"])] == 1])
    # a negative whose name is still indexed is not a negative: a deletion
    # gold re-created as some other row's to_additive twin, or a holdout that
    # shares its name with a row that stayed
    leaked = Counter(a["arm"] for a in arms if a["arm"] != "positive" and a["name"] in present)
    arms = [a for a in arms if a["arm"] == "positive" or a["name"] not in present]
    _jsonl(os.path.join(out, "arms.jsonl"), arms)
    info = {"pin": PIN, "nov": NOV, "funnel": funnel, "unchanged_pool": len(pool),
            "holdout_frac": frac, "pmi_holdout_frac": frac, "seed": seed,
            "ctrl_index": {k: meta[k] for k in ("n_decls", "n_holdout", "n_pmi_holdout")},
            "dropped_still_indexed": dict(leaked),
            "arm_sizes": dict(Counter(a["arm"] for a in arms))}
    with open(os.path.join(out, "arms_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=2)
    return info


# -- retrieval --------------------------------------------------------------


def run_lexical(data: str, out: str) -> None:
    """coverage, margin and top-1 for every query; the time arm also against the
    shipped idx_mathlib, which is what the bead names."""
    from .align import Aligner
    from .cli import LEX
    from .index import load
    from .structmatch import StructReranker
    arms = _jsonl(os.path.join(out, "arms.jsonl"))
    recs = []
    for corpus, path in (("ctrl", os.path.join(out, "idx_ctrl")),
                         ("idx_mathlib", os.path.join(data, "artifacts", "idx_mathlib"))):
        al = Aligner(load(path), tau_cov=0.0, delta_margin=0.0, **LEX)
        rr = StructReranker(al, lam=0.9, depth=10000) if corpus == "ctrl" else None
        for a in arms:
            if corpus != "ctrl" and a["arm"] != "time":
                continue
            r = al.align(a["query"], topk=5)
            rec = {"corpus": corpus, "arm": a["arm"], "name": a["name"],
                   "score": r.coverage, "margin": r.margin,
                   "top1": r.best.name if r.best else None}
            if rr is not None:
                names, _ = rr.rank(a["query"], "", _TEX.findall(a["query"]), topk=1)
                rec["top1_struct"] = names[0] if names else None
            recs.append(rec)
    _jsonl(os.path.join(out, "lexical.jsonl"), recs)


def run_dense(data: str, out: str, model_name: str = MODEL) -> None:
    """Top-1 cosine against the cached corpus embedding, restricted to the rows
    the control index (or idx_mathlib) holds. Needs sentence-transformers."""
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from .bench_pretrained import QUERY_PREFIX, doc_text
    from .index import load
    art = os.path.join(data, "artifacts")
    full = load(os.path.join(art, "idx_full"))["rows"]
    M = np.load(os.path.join(art, f"emb_{model_name.replace('/', '__')}.npy"))
    assert M.shape[0] == len(full)
    names = np.array([r["name"] for r in full], dtype=object)
    model = SentenceTransformer(model_name, device="cpu")   # as the cached corpus was
    enc = lambda xs: model.encode(xs, batch_size=128, normalize_embeddings=True,
                                  convert_to_numpy=True).astype(np.float32)
    # the cache is only usable if row i still is idx_full row i
    chk = random.Random(0).sample(range(len(full)), 64)
    row_cos = (enc([doc_text(full[i]) for i in chk]) * M[chk]).sum(1)

    arms = _jsonl(os.path.join(out, "arms.jsonl"))
    prefix = next((p for k, p in QUERY_PREFIX.items() if model_name.startswith(k)), "")
    Q = enc([prefix + a["query"] for a in arms])
    ctrl = {r["name"] for r in load(os.path.join(out, "idx_ctrl"))["rows"]}
    mathlib = {r["name"] for r in load(os.path.join(art, "idx_mathlib"))["rows"]}

    def top2(mask, sel):
        sub, nm = M[mask], names[mask]
        res = []
        for s in range(0, len(sel), 256):
            S = Q[sel[s:s + 256]] @ sub.T
            r = np.arange(len(S))
            i = S.argmax(1)
            s1 = S[r, i].copy()
            S[r, i] = -np.inf
            res += [(float(a), float(a - b), nm[k]) for a, b, k in zip(s1, S.max(1), i)]
        return res

    recs = []
    time_sel = [k for k, a in enumerate(arms) if a["arm"] == "time"]
    for k, (s, mg, t) in zip(time_sel, top2(np.array([n in mathlib for n in names]), time_sel)):
        recs.append({"corpus": "idx_mathlib", "arm": "time", "name": arms[k]["name"],
                     "score": s, "margin": mg, "top1": t})
    # a positive's corpus text contains its own docstring; drop it
    pos = {a["name"] for a in arms if a["arm"] == "positive"}
    rows = [i for i, r in enumerate(full) if r["name"] in pos]
    M[rows] = enc([". ".join(x for x in (full[i]["name"], full[i].get("head") or "") if x)
                   for i in rows])
    every = list(range(len(arms)))
    for a, (s, mg, t) in zip(arms, top2(np.array([n in ctrl for n in names]), every)):
        recs.append({"corpus": "ctrl", "arm": a["arm"], "name": a["name"],
                     "score": s, "margin": mg, "top1": t})
    _jsonl(os.path.join(out, "dense.jsonl"), recs)
    with open(os.path.join(out, "dense_meta.json"), "w") as fh:
        json.dump({"model": model_name, "row_check_min_cos": float(row_cos.min()),
                   "positive_rows_reembedded": len(rows)}, fh, indent=2)


# -- report -----------------------------------------------------------------


def _rate(k: int, n: int) -> dict:
    from .bench_pretrained import wilson
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None,
            "wilson95": [round(lo, 4), round(hi, 4)], "half_width": round((hi - lo) / 2, 4)}


def fit_threshold(scores: list[float], coverage: float = COVERAGE) -> tuple[float, bool]:
    """precision_at_coverage's cut, unrounded: answer the top ceil(c*N), and if a
    tie straddles the cut, answer strictly above it."""
    s = sorted(scores, reverse=True)
    m = max(1, math.ceil(coverage * len(s)))
    tau = s[m - 1]
    return tau, sum(x >= tau for x in s) > m


def halves(names: list[str], seed: int = 0) -> tuple[set, set]:
    order = sorted(set(names))
    random.Random(seed).shuffle(order)
    return set(order[:len(order) // 2]), set(order[len(order) // 2:])


def score_system(recs: list[dict], seed: int = 0) -> dict:
    """10%-coverage threshold fitted on half of each arm, rates on the other."""
    by = {a: [r for r in recs if r["arm"] == a] for a in ARMS}
    split = {a: halves([r["name"] for r in by[a]], seed) for a in ARMS}
    fit = {a: [r for r in by[a] if r["name"] in split[a][0]] for a in ARMS}
    ev = {a: [r for r in by[a] if r["name"] in split[a][1]] for a in ARMS}
    n = min(len(v) for v in fit.values())
    rng = random.Random(seed)
    pool = [r["score"] for a in ARMS for r in rng.sample(fit[a], n)]
    tau, strict = fit_threshold(pool)
    ans = (lambda r: r["score"] > tau) if strict else (lambda r: r["score"] >= tau)
    out = {"threshold": {"tau": tau, "strict": strict, "fit_per_arm": n,
                         "coverage": COVERAGE}}
    for a in ARMS:
        hit = [r for r in ev[a] if ans(r)]
        if a == "positive":
            out[a] = {"answered": _rate(len(hit), len(ev[a])),
                      "precision": _rate(sum(r["top1"] == r["name"] for r in hit), len(hit))}
        else:
            out[a] = {"false_match": _rate(len(hit), len(ev[a]))}
    t = out["time"]["false_match"]
    out["kill_test"] = {c: {"difference": round(t["rate"] - out[c]["false_match"]["rate"], 4),
                            "needs_more_than": t["half_width"],
                            "survives": t["rate"] - out[c]["false_match"]["rate"] > t["half_width"]}
                        for c in ("holdout", "deletion")}
    out["survives"] = all(v["survives"] for v in out["kill_test"].values())
    out["answered"] = ans
    return out


def report(out: str, results: str, audit: str, n_audit: int = 60, seed: int = 0) -> dict:
    from .cli import GRAPH_THRESHOLDS as G
    meta = json.load(open(os.path.join(out, "arms_meta.json")))
    dmeta = json.load(open(os.path.join(out, "dense_meta.json")))
    lex = _jsonl(os.path.join(out, "lexical.jsonl"))
    den = _jsonl(os.path.join(out, "dense.jsonl"))
    res = {"bead": "mathgraph-269", "protocol": "mathgraph/timesplit.py docstring",
           **meta, "dense": dmeta,
           "mathlib_excerpts": "The audit sheet quotes declaration names, heads and "
           "docstrings from mathlib4 at PIN and NOV, (c) the mathlib contributors, "
           "Apache-2.0 (mathlib4/LICENSE; mathlib ships no NOTICE file). Keep the "
           "attribution, and ship the licence text with any release of the data."}
    systems = {"lexical": [r for r in lex if r["corpus"] == "ctrl"],
               "bge-small": [r for r in den if r["corpus"] == "ctrl"]}
    from .index import load
    arms = _jsonl(os.path.join(out, "arms.jsonl"))
    rows = load(os.path.join(out, "idx_ctrl"))["rows"]
    # Post hoc, so kept out of the kill test: a negative whose docstring sits
    # verbatim on a row that stayed indexed (a sibling's copied docstring) is a
    # near-certain false match for anything that reads docstrings.
    docs = Counter(clean_doc(r["doc"]) for r in rows if r.get("doc"))
    dup = {(a["arm"], a["name"]) for a in arms if a["arm"] != "positive" and docs[a["query"]]}
    res["verbatim_duplicate_docstring"] = dict(Counter(k for k, _ in dup))
    fm = {}
    for name, recs in systems.items():
        s = score_system(recs, seed)
        ans = s.pop("answered")
        shipped = [r for r in (lex if name == "lexical" else den) if r["corpus"] == "idx_mathlib"]
        s["time_vs_shipped_idx_mathlib"] = {"false_match": _rate(sum(map(ans, shipped)), len(shipped))}
        ex = {}
        for a in ARMS[1:]:
            ev = halves([r["name"] for r in recs if r["arm"] == a], seed)[1]
            rs = [r for r in recs if r["arm"] == a and r["name"] in ev and (a, r["name"]) not in dup]
            ex[a] = {"false_match": _rate(sum(map(ans, rs)), len(rs))}
        s["exploratory_without_verbatim_duplicates"] = ex
        fm[name] = {r["name"]: r for r in recs if r["arm"] == "time" and ans(r)}
        res[name] = s
    g = lambda r: r["score"] >= G["tau_cov"] and r["margin"] >= G["delta_margin"]
    graph = {}
    for a in ARMS:
        rs = [r for r in systems["lexical"] if r["arm"] == a]
        hit = [r for r in rs if g(r)]
        graph[a] = ({"answered": _rate(len(hit), len(rs)),
                     "precision": _rate(sum(r["top1"] == r["name"] for r in hit), len(hit))}
                    if a == "positive" else {"false_match": _rate(len(hit), len(rs))})
    rs = [r for r in lex if r["corpus"] == "idx_mathlib"]
    graph["time_vs_shipped_idx_mathlib"] = {"false_match": _rate(sum(map(g, rs)), len(rs))}
    res["lexical_at_GRAPH_THRESHOLDS"] = {"thresholds": G, "whole_arms": graph}
    res["kill_test_survives"] = all(res[s]["survives"] for s in systems)
    res["struct_rerank_changed_top1"] = sum(
        r["top1"] != r.get("top1_struct") for r in systems["lexical"])
    res["audit"] = write_audit(arms, {r["name"]: r for r in rows}, fm, audit, n_audit, seed)
    with open(results, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return res


def write_audit(arms: list[dict], pin: dict, fm: dict, path: str, n: int, seed: int) -> dict:
    """A sample of time-arm false matches (query, system) for two raters, at the
    10%-coverage thresholds of each system. The label asks whether the matched
    PIN declaration is equivalent to, or generalises, the new theorem."""
    arms = {a["name"]: a for a in arms if a["arm"] == "time"}
    pairs = sorted((q, s) for s, m in fm.items() for q in m)
    pick = sorted(random.Random(seed).sample(pairs, min(n, len(pairs))))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "system", "new_name", "new_module", "new_head", "new_doc",
                    "matched_name", "matched_module", "matched_head", "matched_doc",
                    "rater1", "rater2"])
        for i, (q, s) in enumerate(pick, 1):
            a, m = arms[q], pin.get(fm[s][q]["top1"], {})
            w.writerow([i, s, q, a["module"], a["head"], a["query"], fm[s][q]["top1"],
                        m.get("module", ""), m.get("head", ""), m.get("doc", ""), "", ""])
    return {"file": os.path.basename(path), "false_match_pairs": len(pairs),
            "distinct_queries": len({q for q, _ in pairs}), "sampled": len(pick),
            "labels": "pending: two raters, 'equivalent or generalising' vs 'genuinely new'"}


def main(argv=None) -> None:
    import argparse
    p = argparse.ArgumentParser(prog="python -m mathgraph.timesplit")
    p.add_argument("stage", choices=["arms", "lexical", "dense", "report"])
    p.add_argument("--data", default=os.environ.get("MATHGRAPH_DATA", "./mathgraph-data"))
    p.add_argument("--nov", help="mathlib4 checkout at NOV holding PIN's objects too")
    p.add_argument("--out", default="./mathgraph-data/timesplit")
    p.add_argument("--results", default="results/timesplit.json")
    p.add_argument("--audit", default="results/timesplit-audit.csv")
    a = p.parse_args(argv)
    if a.stage == "arms":
        print(json.dumps(build_arms(a.data, a.nov, a.out), indent=2))
    elif a.stage == "lexical":
        run_lexical(a.data, a.out)
    elif a.stage == "dense":
        run_dense(a.data, a.out)
    else:
        r = report(a.out, a.results, a.audit)
        print(json.dumps({k: r[k] for k in ("arm_sizes", "kill_test_survives")}, indent=2))


if __name__ == "__main__":
    main()
