"""Build the searchable mathlib index.

Three artefacts come out of this:

1. the declaration table (source declarations plus the ones `to_additive`
   generates, flagged by provenance so a match can always be traced);
2. an inverted index over name tokens with IDF weights;
3. a translation table from English words to mathlib name tokens, learned by
   pointwise mutual information over the ~67k declarations that carry a
   docstring.

(3) is the part that makes informal input work at all. Nobody writes "add" in
a paper; they write "sum", "addition", "additive". The docstrings are a
parallel corpus between those two vocabularies and it is already sitting in
the repository.
"""

from __future__ import annotations

import gzip
import json
import math
import os
import pickle
import random
import re
from collections import Counter, defaultdict

from .names import split_name, to_additive_name, parse_to_additive_attr

STOP = set("""a an the of to in for on with and or is are be by that this it its as at from
we if then such let there exists all any some not no non into over under between each
which where when whose given only also more most other another same both either
theorem lemma proposition corollary definition proof shows show gives give see cf
version case cases form type term expression statement result note true false
i e g eg ie etc via using used use uses can may must should would could will
one two three main special general simple standard usual natural basic
""".split())

_WORD = re.compile(r"[A-Za-z][A-Za-z\-]+")

_IRREGULAR = {
    "series": "series", "bases": "basis", "basis": "basis",
    "indices": "index", "index": "index", "vertices": "vertex",
    "matrices": "matrix", "radii": "radius", "foci": "focus",
    "lemmas": "lemma", "formulae": "formula", "maxima": "max",
    "minima": "min", "polyhedra": "polyhedron", "simplices": "simplex",
    "ideals": "ideal", "analysis": "analysis", "hypothesis": "hypothesis",
}


def stem(w: str) -> str:
    """Light suffix stripper. Conservative on purpose -- an over-eager stemmer
    collapses `continuous` to `continuou` and destroys the direct-match path
    to the mathlib token of the same name."""
    w = w.lower().strip("-")
    if w in _IRREGULAR:
        return _IRREGULAR[w]
    if len(w) <= 3:
        return w
    for suf, keep in (
        ("ications", "ic"), ("ication", "ic"),
        ("izations", "ize"), ("ization", "ize"),
        ("ations", "ate"), ("ation", "ate"),
        ("iveness", "ive"), ("ness", ""),
        ("ilities", "ile"), ("ility", "ile"),
        ("ities", "ity"),
        ("ically", "ic"), ("ally", "al"), ("ly", ""),
        ("ies", "y"),
        ("ings", "ing"), ("ing", ""),
        ("edly", ""), ("ed", ""),
        ("s", ""),
    ):
        if not w.endswith(suf):
            continue
        if suf == "s":
            if w[-2:] in ("ss", "us", "is", "os", "as"):
                continue
            # English plural: only `-es` after a sibilant actually drops both
            if w[-3:] in ("ses", "xes", "zes") or w[-4:] in ("ches", "shes"):
                return w[:-2]
            return w[:-1]
        base = w[: -len(suf)] + keep
        if len(base) >= 4:
            return base
    return w


def doc_words(text: str) -> list[str]:
    text = re.sub(r"`[^`]*`", " ", text)          # drop inline Lean code
    text = re.sub(r"\$[^$]*\$", " ", text)        # drop inline math
    out = []
    for m in _WORD.finditer(text):
        w = m.group(0).lower()
        if w in STOP or len(w) < 3:
            continue
        out.append(stem(w))
    return out


# ---------------------------------------------------------------------------


def expand_to_additive(rows: list[dict]) -> list[dict]:
    """Add the declarations `@[to_additive]` generates at elaboration time."""
    have = {r["name"] for r in rows}
    extra = []
    for r in rows:
        has, explicit = parse_to_additive_attr(r.get("attrs", ""))
        if not has:
            continue
        if explicit:
            new = explicit if "." in explicit else (
                f"{r['namespace']}.{explicit}" if r["namespace"] else explicit)
            prov = "to_additive:explicit"
        else:
            new = to_additive_name(r["name"])
            prov = "to_additive:inferred"
        if not new or new in have:
            continue
        have.add(new)
        d = dict(r)
        d["name"] = new
        d["provenance"] = prov
        d["head"] = ""
        extra.append(d)
    return rows + extra


def build(raw_path: str, out_dir: str, holdout_frac: float = 0.0,
          pmi_holdout_frac: float = 0.0, seed: int = 0) -> dict:
    """holdout_frac: declarations removed from the index entirely. Queries
    derived from them must be abstained on -- they are the negative controls.

    pmi_holdout_frac: declarations kept in the index but whose docstrings are
    withheld from the translation table. Queries derived from them are the
    positive controls, uncontaminated by having trained on their own answer.
    """
    os.makedirs(out_dir, exist_ok=True)
    rows = [json.loads(l) for l in open(raw_path, encoding="utf-8")]
    rows = expand_to_additive(rows)

    for r in rows:
        r["tokens"] = split_name(r["name"])
        # module path tokens carry real signal (`Mathlib.Geometry.Manifold.*`)
        # but are shared by thousands of declarations, so they enter the index
        # as a separate, discounted field rather than as name tokens
        r["mod_tokens"] = [t for t in split_name(r["module"])
                           if t not in ("mathlib", "basic", "defs", "lemmas")]

    rng = random.Random(seed)
    holdout: list[dict] = []
    if holdout_frac > 0:
        docd = [r for r in rows if r.get("doc")]
        rng.shuffle(docd)
        k = int(len(docd) * holdout_frac)
        hset = {id(r) for r in docd[:k]}
        holdout = docd[:k]
        rows = [r for r in rows if id(r) not in hset]

    pmi_holdout: list[dict] = []
    if pmi_holdout_frac > 0:
        docd = [r for r in rows if r.get("doc")]
        rng.shuffle(docd)
        k = int(len(docd) * pmi_holdout_frac)
        pmi_holdout = docd[:k]
    pmi_blocked = {id(r) for r in pmi_holdout}

    # --- vocabulary / postings -------------------------------------------
    df: Counter = Counter()
    for r in rows:
        df.update(set(r["tokens"]) | set(r["mod_tokens"]))
    N = len(rows)
    idf = {t: math.log(1.0 + N / (1 + c)) for t, c in df.items()}

    postings: dict[str, list[int]] = defaultdict(list)
    mod_postings: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        toks = set(r["tokens"])
        for t in toks:
            postings[t].append(i)
        for t in set(r["mod_tokens"]) - toks:
            mod_postings[t].append(i)

    # --- English -> token translation, PMI over docstrings ----------------
    pair: Counter = Counter()
    wcount: Counter = Counter()
    tcount: Counter = Counter()
    total = 0
    for r in rows:
        if not r.get("doc") or id(r) in pmi_blocked:
            continue
        ws = set(doc_words(r["doc"]))
        ts = set(r["tokens"])
        if not ws or not ts:
            continue
        for w in ws:
            wcount[w] += 1
        for t in ts:
            tcount[t] += 1
        for w in ws:
            for t in ts:
                pair[(w, t)] += 1
                total += 1

    trans: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (w, t), c in pair.items():
        if c < 5:
            continue
        pw = wcount[w]
        pt = tcount[t]
        if pw < 4 or pt < 4:
            continue
        pmi = math.log((c * total) / (pw * pt) + 1e-12)
        if pmi <= 0:
            continue
        # shrink toward zero for pairs seen only a handful of times; raw PMI
        # otherwise ranks one-off coincidences above the real translation
        trans[w].append((t, pmi * (c / (c + 25.0))))
    for w in trans:
        trans[w].sort(key=lambda x: -x[1])
        del trans[w][12:]
        mx = trans[w][0][1] or 1.0
        trans[w] = [(t, s / mx) for t, s in trans[w]]

    art = {
        "rows": rows,
        "idf": idf,
        "postings": dict(postings),
        "mod_postings": dict(mod_postings),
        "trans": dict(trans),
        "meta": {
            "n_decls": len(rows),
            "n_holdout": len(holdout),
            "n_pmi_holdout": len(pmi_holdout),
            "n_tokens": len(idf),
            "n_trans_words": len(trans),
            "provenance": dict(Counter(r.get("provenance", "source") for r in rows)),
        },
    }
    with gzip.open(os.path.join(out_dir, "index.pkl.gz"), "wb") as fh:
        pickle.dump(art, fh, protocol=4)
    for fname, bucket in (("holdout.jsonl", holdout), ("devpos.jsonl", pmi_holdout)):
        if not bucket:
            continue
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as fh:
            for r in bucket:
                fh.write(json.dumps({k: v for k, v in r.items() if k != "tokens"},
                                    ensure_ascii=False) + "\n")
    return art["meta"]


def load(out_dir: str) -> dict:
    with gzip.open(os.path.join(out_dir, "index.pkl.gz"), "rb") as fh:
        return pickle.load(fh)


if __name__ == "__main__":
    import sys
    raw, out = sys.argv[1], sys.argv[2]
    frac = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    pfrac = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    print(json.dumps(build(raw, out, frac, pfrac), indent=2))
