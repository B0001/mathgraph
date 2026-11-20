"""Leave-family-out test of the co-arrival hypothesis (mathgraph-sd8).

The time-split arm (mathgraph-269) failed its kill test in the unexpected
direction: theorems added after the pin are *easier* negatives than random
holdouts (bge-small false-match rate 2.2% against 14.0% at the 10%-coverage
threshold). The co-arrival hypothesis says novelty is not the cause. A holdout
leaves its family indexed (name-stem siblings, its to_additive twin, its
aliases), while a new theorem tends to arrive together with its family, so
nothing that close to it is indexed.

The test moves families in and out of the index one query at a time, without
rebuilding anything:

* holdout and deletion, family removed: every indexed member of the query's
  family is masked out of that query's ranking;
* holdout and deletion, matched control: the same number of random rows from
  the query's own module, outside its family, are masked instead;
* time, siblings added: the 13,008 declarations new at NOV join the index,
  except the query itself and the names its to_additive and alias links reach.

The family rule is name-only (never an embedding, which would be circular:
206 of 221 bge false matches sit inside a cos >= 0.9 family). It was frozen,
with the analysis and the kill test, in sandbox-handoffs/mathgraph-sd8-prereg.md
before any score under these conditions was computed.
"""

from __future__ import annotations

import json
import math
import os
import pickle
import random
import re
from collections import Counter, defaultdict
from functools import lru_cache

from .leanscan import _IDENT
from .names import _CAMEL, split_name
from .timesplit import (_ALIAS_TARGET, _DEP_TARGET, ARMS, _jsonl, _rate, halves, path_of,
                        score_system, twin)

# -- the family rule (frozen by the pre-registration) -------------------------

# Variant markers: the additive/multiplicative and left/right versions of a
# fact, and the Within/NE/On restrictions of a filter or a set
# (`continuousWithinAt`, `nhdsNE`, `continuousOn`). Case matters: `NE` is the
# marker, while `ne` in `mul_ne_zero` is part of the statement.
_DROP = frozenset("add Add mul Mul left Left right Right Within NE On".split())


def stem(name: str) -> str:
    """A declaration's family stem: the last name component with its primes
    removed, cut before an `_of_` hypothesis tail, and with the variant
    markers dropped. Empty when nothing is left, and an empty stem has no
    family."""
    parts = name.rsplit(".", 1)[-1].replace("'", "").split("_")
    if "of" in parts[1:]:
        parts = parts[:parts.index("of", 1)]
    return "_".join(t for p in parts for t in _CAMEL.split(p)
                     if t and t not in _DROP).lower()


@lru_cache(maxsize=4096)
def _lines(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def link_target(r: dict, tree: str | None = None) -> str | None:
    """What an `alias` or an `@[deprecated X]` declaration points at, as
    written. An alias can put its target on the next line, which the scanned
    head leaves out; then it is read from source when a tree is given."""
    if r["kind"] == "alias":
        m = _ALIAS_TARGET.search(r["head"])
        if not m and tree:
            ln = _lines(os.path.join(tree, path_of(r["module"])))
            m = _ALIAS_TARGET.search(" ".join(ln[r["line"] - 1:r["line"] + 2]))
    elif "deprecated" in r.get("attrs", ""):
        m = _DEP_TARGET.search(r["attrs"])
    else:
        return None
    return m.group(1).rstrip(",") if m else None


def resolve(target: str, namespace: str, known) -> str | None:
    """The declaration a name written inside `namespace` refers to: the
    innermost reading that exists, as Lean resolves it."""
    if target.startswith("_root_."):
        target = target[len("_root_."):]
        return target if target in known else None
    parts = namespace.split(".") if namespace else []
    for i in range(len(parts), -1, -1):
        cand = ".".join(parts[:i] + [target])
        if cand in known:
            return cand
    return None


class Families:
    """The encoder-independent family of a declaration:

    * same module AND same `stem`; or
    * its to_additive twin, either direction, from the scanned attributes; or
    * an alias of it, or a declaration deprecated in its favour, either
      direction.

    `universe` holds the rows that can be indexed (name, module); `sources`
    holds (scan rows, source tree) pairs whose attributes and aliases supply
    the links."""

    def __init__(self, universe: list[dict], sources: list[tuple[list[dict], str | None]]):
        self.stems: dict[tuple[str, str], set[str]] = defaultdict(set)
        for r in universe:
            if s := stem(r["name"]):
                self.stems[(r["module"], s)].add(r["name"])
        known = {r["name"] for r in universe} | {r["name"] for rows, _ in sources for r in rows}
        self.links: dict[str, set[str]] = defaultdict(set)
        for rows, tree in sources:
            for r in rows:
                t = link_target(r, tree)
                for other in (twin(r), t and resolve(t, r.get("namespace", ""), known)):
                    if other and other != r["name"]:
                        self.links[r["name"]].add(other)
                        self.links[other].add(r["name"])

    def linked(self, name: str) -> set[str]:
        """The to_additive and alias half of the family only."""
        return set(self.links.get(name, ()))

    def of(self, name: str, module: str) -> set[str]:
        s = stem(name)
        out = set(self.stems.get((module, s), ())) if s else set()
        return (out | self.linked(name)) - {name}


# -- the experiment -----------------------------------------------------------

MODELS = {"bge-small": "BAAI/bge-small-en-v1.5", "bge-base": "BAAI/bge-base-en-v1.5"}
NEG = ("holdout", "deletion")
DRAWS = 20          # matched-random draws per query, averaged
BOOT = 10_000       # bootstrap resamples
SEED = 0
TOPK = 50           # lexical candidates post-filtered before a full rescore
_MOD_SKIP = ("mathlib", "basic", "defs", "lemmas")      # as index.build


def post_pin(sc: dict) -> list[dict]:
    """The NOV-scan rows whose names leanscan(PIN) lacks, in scan order: the
    row set of r2's E_new.npy (13,008 rows)."""
    pin = {r["name"] for r in sc["pin"]}
    return [r for r in sc["nov"] if r["name"] not in pin]


def _scans(snap: str) -> dict:
    with open(os.path.join(snap, "scans.pkl"), "rb") as fh:
        return pickle.load(fh)


def plan(snap: str, data: str, nov: str, out: str) -> dict:
    """Each negative query's indexed family, its matched random draws and, for
    the time arm, the post-pin names its siblings-added index leaves out. One
    plan serves every system, so they all move the same rows."""
    from .index import load
    os.makedirs(out, exist_ok=True)
    arms = _jsonl(os.path.join(snap, "arms.jsonl"))
    rows = load(os.path.join(snap, "idx_ctrl"))["rows"]
    sc = _scans(snap)
    new = post_pin(sc)
    fam = Families([{"name": r["name"], "module": r["module"]} for r in rows] + new,
                   [(sc["pin"], os.path.join(data, "mathlib4")), (sc["nov"], nov)])
    indexed, new_names = {r["name"] for r in rows}, {r["name"] for r in new}
    by_module: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        by_module[r["module"]].add(r["name"])
    recs = []
    for a in arms:
        if a["arm"] == "positive":
            continue
        f = fam.of(a["name"], a["module"])
        rec = {"arm": a["arm"], "name": a["name"], "module": a["module"], "fam": sorted(f & indexed)}
        if a["arm"] in NEG:
            pool = sorted(by_module[a["module"]] - f - {a["name"]})
            k = len(rec["fam"])
            rng = random.Random(f"sd8:{a['arm']}:{a['name']}")
            rec["draws"] = [rng.sample(pool, min(k, len(pool))) for _ in range(DRAWS)] if k else []
            rec["short"] = max(0, k - len(pool))
        else:
            rec["excl"] = sorted(({a["name"]} | fam.linked(a["name"])) & new_names)
            rec["newfam"] = sorted(f & new_names)
        recs.append(rec)
    _jsonl(os.path.join(out, "plan.jsonl"), recs)
    return {"post_pin_rows": len(new), "queries": dict(Counter(r["arm"] for r in recs))}


def _top(s, names) -> dict:
    j = int(s.argmax())
    return {"score": float(s[j]), "top1": names[j]}


def _masked(s, pos, names) -> dict:
    """Top-1 with the rows at `pos` set to -inf, restored afterwards."""
    if not len(pos):
        return _top(s, names)
    saved = s[pos].copy()
    s[pos] = -math.inf
    out = _top(s, names)
    s[pos] = saved
    return out


def run_dense(snap: str, data: str, out: str, system: str, r2: str | None = None) -> dict:
    """Every condition for one encoder, as timesplit.run_dense scores the base:
    cached corpus rows restricted to idx_ctrl, positives re-embedded without
    docstrings, prefixed queries, top-1 cosine. Needs sentence-transformers."""
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from .bench_pretrained import QUERY_PREFIX, doc_text
    from .index import load
    model_name = MODELS[system]
    art = os.path.join(data, "artifacts")
    full = load(os.path.join(art, "idx_full"))["rows"]
    M = np.load(os.path.join(art, f"emb_{model_name.replace('/', '__')}.npy"), mmap_mode="r")
    assert M.shape[0] == len(full)
    model = SentenceTransformer(model_name, device="cpu")    # as the cached corpus was
    enc = lambda xs: model.encode(xs, batch_size=128, normalize_embeddings=True,
                                  convert_to_numpy=True).astype(np.float32)
    chk = random.Random(0).sample(range(len(full)), 64)
    meta = {"model": model_name,
            "row_check_min_cos": float((enc([doc_text(full[i]) for i in chk]) * M[chk]).sum(1).min())}

    ctrl = {r["name"] for r in load(os.path.join(snap, "idx_ctrl"))["rows"]}
    keep = [i for i, r in enumerate(full) if r["name"] in ctrl]
    names = [full[i]["name"] for i in keep]
    C = np.array(M[keep])
    arms = _jsonl(os.path.join(snap, "arms.jsonl"))
    pos = {a["name"] for a in arms if a["arm"] == "positive"}
    rp = [j for j, n in enumerate(names) if n in pos]
    C[rp] = enc([". ".join(x for x in (full[keep[j]]["name"], full[keep[j]].get("head") or "") if x)
                 for j in rp])
    meta.update(ctrl_rows=len(keep), ctrl_names_missing=len(ctrl - set(names)),
                positive_rows_reembedded=len(rp))

    new = post_pin(_scans(snap))
    cache = os.path.join(out, f"emb_new_{system}.npy")
    if os.path.exists(cache):
        E = np.load(cache)
    else:
        E = enc([doc_text(r) for r in new])
        np.save(cache, E)
    assert E.shape[0] == len(new)
    if r2 and system == "bge-small":
        meta["r2_E_new_min_cos"] = float((E * np.load(r2)).sum(1).min())
    new_names = [r["name"] for r in new]

    prefix = next((p for k, p in QUERY_PREFIX.items() if model_name.startswith(k)), "")
    Q = enc([prefix + a["query"] for a in arms])
    pos_of, npos_of = defaultdict(list), defaultdict(list)
    for j, n in enumerate(names):
        pos_of[n].append(j)
    for j, n in enumerate(new_names):
        npos_of[n].append(j)
    at = lambda idx, ns: np.array([j for n in ns for j in idx.get(n, ())], dtype=np.int64)
    pl = {(p["arm"], p["name"]): p for p in _jsonl(os.path.join(out, "plan.jsonl"))}

    recs = []
    for s0 in range(0, len(arms), 256):
        batch = arms[s0:s0 + 256]
        S = Q[s0:s0 + 256] @ C.T
        Sn = Q[s0:s0 + 256] @ E.T
        for i, a in enumerate(batch):
            rec = {"arm": a["arm"], "name": a["name"], **_top(S[i], names)}
            p = pl.get((a["arm"], a["name"]))
            if p:
                rec["fam"] = _masked(S[i], at(pos_of, p["fam"]), names)
                if a["arm"] in NEG:
                    rec["rand"] = [_masked(S[i], at(pos_of, d), names)["score"]
                                   for d in p["draws"]] or [rec["score"]]
                else:
                    b = _masked(Sn[i], at(npos_of, p["excl"]), new_names)
                    rec["sib_new"] = b["score"] > rec["score"]
                    rec["sib"] = b if rec["sib_new"] else {"score": rec["score"], "top1": rec["top1"]}
            recs.append(rec)
    _jsonl(os.path.join(out, f"dense_{system}.jsonl"), recs)
    with open(os.path.join(out, f"dense_{system}_meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    return meta


class Appended:
    """Rows scored by an Aligner as if appended to its index, with every
    statistic held at the index's own values: IDF, PMI table, df cut-offs,
    field gates, length pivot and mean, and the query's mass. Old rows keep
    their scores exactly, so a change is due to the appended rows alone."""

    def __init__(self, al, rows: list[dict], len_pivot: float):
        import numpy as np
        from .index import type_tokens
        self.al, self.n = al, len(rows)
        post: tuple[dict, dict, dict] = ({}, {}, {})
        lens = []
        for j, r in enumerate(rows):
            toks = set(split_name(r["name"]))
            mods = {t for t in split_name(r["module"]) if t not in _MOD_SKIP} - toks
            typs = set(type_tokens(r.get("head") or "")) - toks
            for p, ts in zip(post, (toks, mods, typs)):
                for t in ts:
                    p.setdefault(t, []).append(j)
            lens.append(sum(al.idf.get(t, 0.0) for t in toks) or 1.0)
        self.post = [{t: np.asarray(v) for t, v in p.items()} for p in post]
        mean = float(np.asarray([sum(al.idf.get(t, 0.0) for t in set(r["tokens"])) or 1.0
                                 for r in al.rows], dtype=np.float32).mean())
        self.lennorm = ((1.0 - len_pivot)
                        + len_pivot * np.asarray(lens, dtype=np.float32) / mean)

    def score(self, qw: dict):
        """(normalised, raw) score of every appended row, as Aligner._score
        would compute them."""
        import numpy as np
        al = self.al
        raw = np.zeros(self.n, dtype=np.float32)
        for tok, w in qw.items():
            c = w * al.idf[tok]
            arr = al.post.get(tok)
            if arr is not None and arr.size and tok in self.post[0]:
                raw[self.post[0][tok]] += c
            for k, (wt, idx) in enumerate(((al.mod_weight, al.modpost), (al.typ_weight, al.typpost)), 1):
                arr = idx.get(tok)
                if wt and arr is not None and 0 < arr.size <= al.max_df * 6 and tok in self.post[k]:
                    raw[self.post[k][tok]] += c * wt
        return raw / self.lennorm, raw


def appended_check(al, len_pivot: float, queries: list[str], n_rows: int = 300,
                   n_q: int = 30, seed: int = SEED) -> float:
    """Largest gap between Appended's scores and the Aligner's own, on index
    rows scored both ways (rows the query does not reach score 0 in both)."""
    rng = random.Random(seed)
    src = [j for j, r in enumerate(al.rows) if r.get("provenance", "source") == "source"]
    pick = rng.sample(src, n_rows)
    app = Appended(al, [al.rows[j] for j in pick], len_pivot)
    worst = 0.0
    for q in rng.sample(queries, n_q):
        qw = al.query_weights(q)
        res = al._score(qw, al.N)
        if len(res) == 3:
            continue
        got = {int(j): (float(nm), float(rw)) for j, nm, rw in zip(res[0], res[1], res[3])}
        an, ar = app.score(qw)
        for k, j in enumerate(pick):
            nm, rw = got.get(j, (0.0, 0.0))
            worst = max(worst, abs(nm - float(an[k])), abs(rw - float(ar[k])))
    return worst


def run_lexical(snap: str, out: str) -> dict:
    """Every condition through the lexical Aligner on idx_ctrl. A mask
    post-filters the candidates align(q, topk=50) ranks; the score is the
    coverage of the first unmasked one."""
    import numpy as np
    from .align import Aligner
    from .cli import LEX
    from .index import load
    al = Aligner(load(os.path.join(snap, "idx_ctrl")), tau_cov=0.0, delta_margin=0.0, **LEX)
    names = [r["name"] for r in al.rows]
    pos_of = defaultdict(list)
    for j, n in enumerate(names):
        pos_of[n].append(j)
    new = post_pin(_scans(snap))
    new_pos = defaultdict(list)
    for j, r in enumerate(new):
        new_pos[r["name"]].append(j)
    app = Appended(al, new, LEX["len_pivot"])
    arms = [a for a in _jsonl(os.path.join(snap, "arms.jsonl")) if a["arm"] != "positive"]
    meta = {"appended_check_max_abs_diff": appended_check(al, LEX["len_pivot"],
                                                          [a["query"] for a in arms])}
    pl = {(p["arm"], p["name"]): p for p in _jsonl(os.path.join(out, "plan.jsonl"))}
    rescored = 0

    def first(res, qw, masked: set) -> dict:
        nonlocal rescored
        for full in (False, True):
            ids, norm, mass, raw = res
            for i, j in enumerate(ids):
                if int(j) not in masked:
                    return {"score": float(raw[i] / mass), "top1": names[int(j)], "norm": float(norm[i])}
            if full or len(ids) < TOPK:
                break
            rescored += 1
            res = al._score(qw, al.N)
        return {"score": 0.0, "top1": None, "norm": 0.0}

    rows_at = lambda ns: {j for n in ns for j in pos_of.get(n, ())}
    recs = []
    for a in arms:
        p = pl[(a["arm"], a["name"])]
        qw = al.query_weights(a["query"])
        res = al._score(qw, TOPK)
        rec = {"arm": a["arm"], "name": a["name"]}
        if len(res) == 3 or not res[0].size:
            none = {"score": 0.0, "top1": None}
            rec.update(none, fam=none)
            if a["arm"] in NEG:
                rec["rand"] = [0.0]
            else:
                rec.update(sib=none, sib_new=False)
            recs.append(rec)
            continue
        base = first(res, qw, set())
        rec.update(score=base["score"], top1=base["top1"])
        rec["fam"] = {k: v for k, v in first(res, qw, rows_at(p["fam"])).items() if k != "norm"}
        if a["arm"] in NEG:
            rec["rand"] = [first(res, qw, rows_at(d))["score"] for d in p["draws"]] or [base["score"]]
        else:
            nm, rw = app.score(qw)
            ex = [j for n in p["excl"] for j in new_pos.get(n, ())]
            nm[ex] = -math.inf
            j = int(nm.argmax())
            rec["sib_new"] = bool(nm[j] > base["norm"])
            rec["sib"] = ({"score": float(rw[j] / res[2]), "top1": new[j]["name"]} if rec["sib_new"]
                          else {"score": base["score"], "top1": base["top1"]})
        recs.append(rec)
    meta["rescored_with_every_row"] = rescored
    _jsonl(os.path.join(out, "lexical.jsonl"), recs)
    with open(os.path.join(out, "lexical_meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    return meta


# -- secondary covariate: constant-identifier Jaccard to the nearest sibling --

_BLOCK = re.compile(r"/-.*?-/", re.S)
_LINE = re.compile(r"--[^\n]*")
_ID = re.compile(_IDENT)


def decl_texts(rows: list[dict], tree: str, modules: set[str] | None = None):
    """(row, full source text) for each scanned declaration: from its line to
    the line before the next scanned declaration of the same file."""
    by_mod: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if modules is None or r["module"] in modules:
            by_mod[r["module"]].append(r)
    for mod, rs in by_mod.items():
        try:
            lines = _lines(os.path.join(tree, path_of(mod)))
        except (OSError, UnicodeDecodeError):
            continue
        rs.sort(key=lambda r: r["line"])
        for r, nxt in zip(rs, rs[1:] + [None]):
            yield r, "\n".join(lines[r["line"] - 1:(nxt["line"] - 1) if nxt else len(lines)])


def constants(text: str, known: set[str]) -> frozenset[str]:
    """Identifiers in `text`, comments and docstrings removed, that name a
    scanned declaration exactly or as a trailing suffix (`open` namespaces;
    `hf.continuous` counts as `continuous`). Single characters never count."""
    out = set()
    for m in _ID.finditer(_LINE.sub(" ", _BLOCK.sub(" ", text))):
        parts = m.group(0).rstrip(".").split(".")
        for i in range(len(parts)):
            t = ".".join(parts[i:])
            if len(t) > 1 and t in known:
                out.add(t)
                break
    return frozenset(out)


def covariate(snap: str, data: str, nov: str, out: str) -> dict:
    """J(q) per query and condition: the IDF-weighted Jaccard between q's
    constant identifiers and those of its nearest indexed same-module sibling
    (0 when there is none). IDF is over every PIN-scan declaration."""
    from .index import load
    arms = [a for a in _jsonl(os.path.join(snap, "arms.jsonl")) if a["arm"] != "positive"]
    pl = {(p["arm"], p["name"]): p for p in _jsonl(os.path.join(out, "plan.jsonl"))}
    sc = _scans(snap)
    new = post_pin(sc)
    indexed = {r["name"] for r in load(os.path.join(snap, "idx_ctrl"))["rows"]}
    known = {".".join(p[i:]) for r in sc["pin"] + sc["nov"]
             for p in [r["name"].split(".")] for i in range(len(p))}
    mods = {a["module"] for a in arms}
    pin_tok, df, n = {}, Counter(), 0
    for r, text in decl_texts(sc["pin"], os.path.join(data, "mathlib4")):
        toks = constants(text, known)
        df.update(toks)
        n += 1
        if r["module"] in mods:
            pin_tok[r["name"]] = toks
    idf, top = {t: math.log(1.0 + n / (1 + c)) for t, c in df.items()}, math.log(1.0 + n)
    new_names = {r["name"] for r in new}
    tmods = {a["module"] for a in arms if a["arm"] == "time"}
    nov_tok = {r["name"]: constants(text, known)
               for r, text in decl_texts(sc["nov"], nov, tmods) if r["name"] in new_names}
    pin_sib, new_sib = defaultdict(list), defaultdict(list)
    for r in sc["pin"]:
        if r["module"] in mods and r["name"] in indexed and r["name"] in pin_tok:
            pin_sib[r["module"]].append(r["name"])
    for r in new:
        if r["module"] in tmods and r["name"] in nov_tok:
            new_sib[r["module"]].append(r["name"])
    original = {t: r["name"] for r in sc["pin"] if (t := twin(r))}   # generated twin -> source

    def jac(a, b):
        u = sum(idf.get(t, top) for t in a | b)
        return sum(idf.get(t, top) for t in a & b) / u if u else 0.0

    recs = []
    for a in arms:
        p, q = pl[(a["arm"], a["name"])], a["name"]
        mine = (nov_tok.get(q) if a["arm"] == "time"
                else pin_tok.get(q, pin_tok.get(original.get(q, ""), frozenset())))
        mine = mine or frozenset()
        fam = set(p["fam"])
        near = lambda xs, tok: max((jac(mine, tok[x]) for x in xs if x != q), default=0.0)
        rec = {"arm": a["arm"], "name": q, "ok": bool(mine),
               "J": {"base": near(pin_sib[a["module"]], pin_tok),
                     "fam": near([x for x in pin_sib[a["module"]] if x not in fam], pin_tok)}}
        if a["arm"] == "time":
            excl = set(p["excl"])
            rec["J"]["sib"] = max(rec["J"]["base"],
                                  near([x for x in new_sib[a["module"]] if x not in excl], nov_tok))
        recs.append(rec)
    _jsonl(os.path.join(out, "covariate.jsonl"), recs)
    return {"pin_declarations": n, "constants": len(df), "queries": len(recs)}


# -- report ---------------------------------------------------------------------

_r4 = lambda x: round(float(x), 4)


def _pct(x) -> list[float]:
    import numpy as np
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    return [_r4(np.percentile(x, 2.5)), _r4(np.percentile(x, 97.5))] if x.size else [None, None]


def _fm(x, rng) -> dict:
    """A false-match rate from per-query values: Wilson for 0/1 values, a
    percentile bootstrap for the matched-random condition's fractions."""
    import numpy as np
    if np.all(x == np.round(x)):
        return _rate(int(x.sum()), len(x))
    means = x[rng.integers(0, len(x), (BOOT, len(x)))].mean(1)
    return {"expected_k": _r4(x.sum()), "n": len(x), "rate": _r4(x.mean()), "bootstrap95": _pct(means)}


def kill_stats(v: dict, seed: int = SEED) -> dict:
    """The pre-registered statistics, from per-query eval-half values."""
    import numpy as np
    rng = np.random.default_rng(seed)
    tb, ts = v["time"]["base"], v["time"]["sib"]
    it = rng.integers(0, len(tb), (BOOT, len(tb)))
    out = {}
    for arm in NEG:
        hb, hf, hr = v[arm]["base"], v[arm]["fam"], v[arm]["rand"]
        ih = rng.integers(0, len(hb), (BOOT, len(hb)))
        gap, g = hb.mean() - tb.mean(), hb[ih].mean(1) - tb[it].mean(1)
        with np.errstate(divide="ignore", invalid="ignore"):
            c = np.where(g > 0, (hb[ih].mean(1) - hf[ih].mean(1)) / g, np.nan)
        d = hr[ih].mean(1) - hf[ih].mean(1)
        out[arm] = {"gap": _r4(gap), "gap_bootstrap95": _pct(g),
                    "gap_excludes_0": bool(np.percentile(g, 2.5) > 0),
                    "closure": _r4((hb.mean() - hf.mean()) / gap) if gap > 0 else None,
                    "closure_bootstrap95": _pct(c),
                    "random_minus_family": _r4(hr.mean() - hf.mean()),
                    "random_minus_family_bootstrap95": _pct(d),
                    "p_family_not_better": _r4((1 + (d <= 0).sum()) / (BOOT + 1))}
    out["time"] = {"rise": _r4(ts.mean() - tb.mean()),
                   "rise_bootstrap95": _pct(ts[it].mean(1) - tb[it].mean(1))}
    return out


def verdict(res: dict) -> dict:
    """C1 and C2 on the holdout arm, C3 on the time arm, per gated encoder;
    strict (every encoder must pass) and literal (one passing encoder is
    enough) readings of "for bge-small AND bge-base"."""
    per = {}
    for s in ("bge-small", "bge-base"):
        if s not in res:
            continue
        h, t = res[s]["kill_test"]["holdout"], res[s]["kill_test"]["time"]
        per[s] = {"C1_applicable": h["gap_excludes_0"],
                  "C1_pass": h["closure"] is not None and h["closure"] >= 0.5,
                  "C2_pass": h["p_family_not_better"] < 0.05,
                  "C3_pass": t["rise"] >= 0.04}
    c1 = [p["C1_pass"] for p in per.values() if p["C1_applicable"]]
    c2 = [p["C2_pass"] for p in per.values()]
    c3 = [p["C3_pass"] for p in per.values()]
    return {"per_encoder": per,
            "strict": {"killed": not (c1 and all(c1)) or not all(c2),
                       "time_half_falsified": not all(c3)},
            "literal": {"killed": not any(c1) or not any(c2),
                        "time_half_falsified": not any(c3)},
            "primary": "strict"}


def report(snap: str, out: str, results: str) -> dict:
    import numpy as np
    arms = _jsonl(os.path.join(snap, "arms.jsonl"))
    pl = {(p["arm"], p["name"]): p for p in _jsonl(os.path.join(out, "plan.jsonl"))}
    ev = {a: sorted(halves([x["name"] for x in arms if x["arm"] == a], SEED)[1]) for a in ARMS}
    published = {"lexical": os.path.join(snap, "lexical.jsonl"),
                 "bge-small": os.path.join(snap, "dense.jsonl")}
    sizes = {}
    for arm in ("holdout", "deletion", "time"):
        ks = sorted(len(p["fam"]) for p in pl.values() if p["arm"] == arm)
        sizes[arm] = {"n": len(ks), "share_nonempty": _r4(sum(k > 0 for k in ks) / len(ks)),
                      "median": ks[len(ks) // 2], "p90": ks[int(0.9 * len(ks))], "max": ks[-1]}
        if arm in NEG:
            sizes[arm]["matched_random_shortfall_queries"] = sum(
                p["short"] > 0 for p in pl.values() if p["arm"] == arm)
        else:
            sizes[arm]["share_with_post_pin_family"] = _r4(sum(
                bool(p["newfam"]) for p in pl.values() if p["arm"] == arm) / len(ks))
    res = {"bead": "mathgraph-sd8", "protocol": "sandbox-handoffs/mathgraph-sd8-prereg.md",
           "draws": DRAWS, "bootstrap": BOOT, "seed": SEED, "family_sizes": sizes}
    cov = os.path.join(out, "covariate.jsonl")
    cov = {(r["arm"], r["name"]): r for r in _jsonl(cov)} if os.path.exists(cov) else None
    for system in ("bge-small", "bge-base", "lexical"):
        path = os.path.join(out, "lexical.jsonl" if system == "lexical" else f"dense_{system}.jsonl")
        if not os.path.exists(path):
            continue
        recs = _jsonl(path)
        by = {(r["arm"], r["name"]): r for r in recs}
        ref = ([r for r in _jsonl(published[system]) if r["corpus"] == "ctrl"]
               if system in published else None)
        fit = score_system(ref or recs, SEED)
        ans = fit.pop("answered")
        meta_path = path.replace(".jsonl", "_meta.json")
        s = {"threshold": fit["threshold"],
             "threshold_from": "published hctz records" if ref else "this run's base records",
             "run": json.load(open(meta_path)) if os.path.exists(meta_path) else {}}
        if ref:
            rr = [r for r in ref if r["arm"] != "positive"]
            agree = sum(by[(r["arm"], r["name"])]["top1"] == r["top1"] for r in rr)
            counts = {a: [sum(ans(by[(a, q)]) for q in ev[a]),
                          sum(ans(r) for r in rr if r["arm"] == a and r["name"] in set(ev[a]))]
                      for a in ("holdout", "deletion", "time")}
            s["reproduction_gate"] = {
                "top1_agreement": _r4(agree / len(rr)),
                "max_abs_score_diff": float(max(abs(by[(r["arm"], r["name"])]["score"] - r["score"])
                                                for r in rr)),
                "eval_false_matches_this_run_vs_published": counts,
                "passes": agree / len(rr) >= 0.99 and all(a == b for a, b in counts.values())}
        v = {}
        for arm in ("holdout", "deletion", "time"):
            rs = [by[(arm, q)] for q in ev[arm]]
            v[arm] = {"base": np.array([ans(r) for r in rs], dtype=float),
                      "fam": np.array([ans(r["fam"]) for r in rs], dtype=float)}
            if arm in NEG:
                v[arm]["rand"] = np.array([np.mean([ans({"score": x}) for x in r["rand"]]) for r in rs])
            else:
                v[arm]["sib"] = np.array([ans(r["sib"]) for r in rs], dtype=float)
        rng = np.random.default_rng(SEED)
        s["false_match"] = {arm: {c: _fm(x, rng) for c, x in d.items()} for arm, d in v.items()}
        s["kill_test"] = kill_stats(v)
        diag = {}
        for arm in ("holdout", "deletion", "time"):
            rs = [by[(arm, q)] for q in ev[arm]]
            fam = lambda r: set(pl[(arm, r["name"])]["fam"])
            hit = [r for r in rs if ans(r)]
            diag[arm] = {"base_answered": len(hit),
                         "base_answered_top1_in_family": sum(r["top1"] in fam(r) for r in hit)}
            if arm == "time":
                sh = [r for r in rs if ans(r["sib"])]
                nf = lambda r: set(pl[(arm, r["name"])]["newfam"])
                diag[arm].update(siblings_added_answered=len(sh),
                                 siblings_added_top1_post_pin=sum(r["sib_new"] for r in sh),
                                 siblings_added_top1_in_post_pin_family=sum(
                                     r["sib_new"] and r["sib"]["top1"] in nf(r) for r in sh))
        s["diagnostics"] = diag
        if cov:
            s["secondary"] = _secondary(cov, by, ev, ans)
        res[system] = s
    res["verdict"] = verdict(res)
    with open(results, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return res


def _secondary(cov: dict, by: dict, ev: dict, ans) -> dict:
    """False-match rate by quintile of J, pooled over the three base arms; the
    holdout-minus-time gap stratified by those bins (CMH weights)."""
    import numpy as np
    arms3 = ("holdout", "deletion", "time")
    coverage = {a: _r4(np.mean([cov[(a, q)]["ok"] for q in ev[a]])) for a in arms3}
    out = {"coverage": coverage, "coverage_gate_passes": all(c >= 0.9 for c in coverage.values())}
    if not out["coverage_gate_passes"]:
        return out
    ok = {a: [q for q in ev[a] if cov[(a, q)]["ok"]] for a in arms3}
    pooled = [cov[(a, q)]["J"]["base"] for a in arms3 for q in ok[a]]
    edges = sorted(set(_r4(e) for e in np.quantile(pooled, [0.2, 0.4, 0.6, 0.8])))
    out["bin_edges"] = edges
    bin_of = lambda j: int(np.digitize(j, edges, right=True))
    conds = {"holdout": ("base", "fam"), "deletion": ("base", "fam"), "time": ("base", "fam", "sib")}
    table = {}
    for a, cs in conds.items():
        for c in cs:
            cells = defaultdict(lambda: [0, 0])
            for q in ok[a]:
                r = by[(a, q)]
                b = bin_of(cov[(a, q)]["J"][c])
                cells[b][0] += bool(ans(r if c == "base" else r[c]))
                cells[b][1] += 1
            table[f"{a}/{c}"] = {str(b): _rate(*cells[b]) for b in range(len(edges) + 1)}
    out["false_match_by_bin"] = table
    num = den = 0.0
    for b in range(len(edges) + 1):
        h, t = table["holdout/base"][str(b)], table["time/base"][str(b)]
        if h["n"] and t["n"]:
            w = h["n"] * t["n"] / (h["n"] + t["n"])
            num += w * (h["rate"] - t["rate"])
            den += w
    unstrat = (np.mean([bool(ans(by[("holdout", q)])) for q in ok["holdout"]])
               - np.mean([bool(ans(by[("time", q)])) for q in ok["time"]]))
    out["holdout_minus_time"] = {"unstratified": _r4(unstrat),
                                 "stratified_by_J": _r4(num / den) if den else None}
    return out


def main(argv=None) -> None:
    import argparse
    p = argparse.ArgumentParser(prog="python -m mathgraph.lfo")
    p.add_argument("stage", choices=["plan", "dense", "lexical", "covariate", "report"])
    p.add_argument("--data", default=os.environ.get("MATHGRAPH_DATA", "./mathgraph-data"))
    p.add_argument("--snap", help="the hctz time-split outputs (default: <data>/hctz-timesplit)")
    p.add_argument("--nov", help="mathlib4 checkout at NOV (plan, covariate)")
    p.add_argument("--system", choices=sorted(MODELS), default="bge-small")
    p.add_argument("--r2", help="r2's E_new.npy, checked against the bge-small post-pin embedding")
    p.add_argument("--out", default="./mathgraph-data/lfo")
    p.add_argument("--results", default="results/lfo.json")
    a = p.parse_args(argv)
    snap = a.snap or os.path.join(a.data, "hctz-timesplit")
    if a.stage == "plan":
        r = plan(snap, a.data, a.nov, a.out)
    elif a.stage == "dense":
        r = run_dense(snap, a.data, a.out, a.system, a.r2)
    elif a.stage == "lexical":
        r = run_lexical(snap, a.out)
    elif a.stage == "covariate":
        r = covariate(snap, a.data, a.nov, a.out)
    else:
        r = report(snap, a.out, a.results)["verdict"]
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
