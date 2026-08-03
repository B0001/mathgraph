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

The `to_additive` names in (1) are reconstructed by applying a naming
dictionary, and about 29% of the inferred ones name something mathlib never
generated. `GroundTruth` below is the optional cure: when an elaborated
environment is available (`mathgraph elaborate`), the reconstructions are
checked against it and the inventions are dropped. When one is not -- the
laptop path, with no Lean toolchain -- everything is kept and the provenance
says `:unvalidated` rather than implying a check that did not happen.
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

from .names import (split_name, to_additive_name, parse_to_additive_attr,
                    additive_tokens)

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


_LEAN_ID = re.compile(r"[A-Za-z][A-Za-z0-9_']*")
_UNIV = re.compile(r"u_?\d+")
# Lean syntax and binder noise, plus the sorts, which appear in nearly every
# type and so carry no discriminating signal.
_TYPE_SKIP = frozenset("""
inst Type Sort Prop theorem lemma def abbrev structure class instance axiom
example where fun let have match with deriving extends protected private
noncomputable partial unsafe mutual do then else if at using by exact intro
""".split())


def type_tokens(head: str, elaborated: bool = False) -> list[str]:
    """Identifiers appearing in a declaration's *type*.

    The name says `IsCompact.isClosed`; the type says
    `... [T2Space X] ... IsCompact s -> IsClosed s`. The Hausdorff hypothesis
    exists only in the second, so a name-token index cannot reach it from the
    word "Hausdorff" at all. This is the third indexed field that fixes that.

    Works on elaborated types (`mathgraph elaborate`) and, less well, on the
    regex-scraped declaration heads the source scanner produces.

    `elaborated` decides what `:=` means, and it means opposite things in the
    two. A scraped head runs `name : type := body`, where the body is an
    implementation rather than part of the statement, so everything from the
    first `:=` is cut -- 86% of scraped heads carry one. An elaborated type has
    no body at all: every `:=` in one belongs to a structure instance inside
    the type (`{ toConfig := toConfig, ... }`) or to a `have`/`let` binding, so
    cutting there throws away real type text. 5.5% of elaborated declarations
    contain one.
    """
    body = head if elaborated else head.split(":=", 1)[0]
    out: list[str] = []
    for m in _LEAN_ID.finditer(body):
        w = m.group(0)
        if len(w) == 1 or w in _TYPE_SKIP or _UNIV.fullmatch(w):
            continue
        out.extend(split_name(w))
    return out


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


class GroundTruth:
    """The declarations a real Lean environment actually contains.

    `@[to_additive]` runs at elaboration time, so an elaborated environment is
    not evidence about the generated names -- it *is* them. That makes it an
    exact filter on the reconstruction, but only over the modules it covers:
    a PFR or blueprint declaration is absent from a mathlib environment because
    mathlib does not contain it, not because it does not exist.

    So coverage is decided per module. Inside a covered module absence is
    conclusive and an unrecognised reconstruction is dropped; outside one
    nothing is claimed and the reconstruction is kept, marked `:unvalidated`.
    """

    def __init__(self, names: set[str], modules: set[str]):
        self.names = names
        self.modules = modules

    @classmethod
    def from_jsonl(cls, path: str) -> "GroundTruth":
        names, modules = set(), set()
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                names.add(d["name"])
                modules.add(d.get("module", ""))
        return cls(names, modules)

    def covers(self, row: dict) -> bool:
        return row.get("module", "") in self.modules

    def __contains__(self, name: str) -> bool:
        return name in self.names

    def __len__(self) -> int:
        return len(self.names)


def find_ground_truth(art_dir: str) -> "GroundTruth | None":
    """The elaborated dump `mathgraph elaborate` leaves behind, if there is one."""
    p = os.path.join(art_dir, "mathlib_elab.jsonl")
    return GroundTruth.from_jsonl(p) if os.path.exists(p) else None


def expand_to_additive(rows: list[dict],
                       truth: "GroundTruth | None" = None,
                       ) -> tuple[list[dict], dict]:
    """Add the declarations `@[to_additive]` generates at elaboration time.

    Returns (rows_plus_twins, stats). Every generated row's provenance carries
    a third component saying whether the name was checked:

        to_additive:inferred:validated     reconstructed, and the elaborated
        to_additive:explicit:validated     environment confirms it exists
        to_additive:inferred:unvalidated   reconstructed, nothing checked it
        to_additive:explicit:unvalidated

    Names the environment contradicts are dropped rather than kept and marked.
    A marked invention is still retrievable, still verifiable, and still names
    nothing -- the mark only helps a caller who reads provenance, whereas
    dropping helps every caller including the `nonexistent` verdict.
    """
    have = {r["name"] for r in rows}
    extra: list[dict] = []
    stats: Counter = Counter()
    for r in rows:
        has, explicit = parse_to_additive_attr(r.get("attrs", ""))
        if not has:
            continue
        if explicit:
            new = explicit if "." in explicit else (
                f"{r['namespace']}.{explicit}" if r["namespace"] else explicit)
            kind = "explicit"
        else:
            new = to_additive_name(r["name"])
            kind = "inferred"
        if not new:
            stats[f"{kind}:untranslatable"] += 1
            continue
        if new in have:
            continue
        if truth is not None and truth.covers(r):
            if new not in truth:
                stats[f"{kind}:dropped"] += 1
                continue
            checked = "validated"
        else:
            checked = "unvalidated"
        stats[f"{kind}:{checked}"] += 1
        have.add(new)
        d = dict(r)
        d["name"] = new
        d["provenance"] = f"to_additive:{kind}:{checked}"
        # No source text exists for a generated twin, and inventing one would
        # make the provenance a lie. But the *type* is recoverable: it is the
        # original's with the multiplicative structures renamed, which is enough
        # for the third index field and leaves `head` honestly empty.
        d["head"] = ""
        d["typ_tokens"] = additive_tokens(type_tokens(r.get("head") or ""))
        extra.append(d)
    return rows + extra, dict(stats)


def build(raw_path: str, out_dir: str, holdout_frac: float = 0.0,
          pmi_holdout_frac: float = 0.0, seed: int = 0,
          truth: "GroundTruth | None" = None) -> dict:
    """holdout_frac: declarations removed from the index entirely. Queries
    derived from them must be abstained on -- they are the negative controls.

    pmi_holdout_frac: declarations kept in the index but whose docstrings are
    withheld from the translation table. Queries derived from them are the
    positive controls, uncontaminated by having trained on their own answer.

    truth: an elaborated environment to check the `to_additive` reconstruction
    against. Optional by design -- without a Lean toolchain there is none, and
    the index is then built with every reconstruction kept and marked
    `:unvalidated`.
    """
    os.makedirs(out_dir, exist_ok=True)
    rows = [json.loads(l) for l in open(raw_path, encoding="utf-8")]
    rows, ta_stats = expand_to_additive(rows, truth)

    for r in rows:
        r["tokens"] = split_name(r["name"])
        # module path tokens carry real signal (`Mathlib.Geometry.Manifold.*`)
        # but are shared by thousands of declarations, so they enter the index
        # as a separate, discounted field rather than as name tokens
        r["mod_tokens"] = [t for t in split_name(r["module"])
                           if t not in ("mathlib", "basic", "defs", "lemmas")]
        # to_additive twins arrive from expand_to_additive with theirs already
        # translated; everything else derives from its own type text
        if "typ_tokens" not in r:
            r["typ_tokens"] = type_tokens(
                r.get("head") or "",
                elaborated=r.get("provenance") == "elaborated")

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
        df.update(set(r["tokens"]) | set(r["mod_tokens"]) | set(r["typ_tokens"]))
    N = len(rows)
    idf = {t: math.log(1.0 + N / (1 + c)) for t, c in df.items()}

    postings: dict[str, list[int]] = defaultdict(list)
    mod_postings: dict[str, list[int]] = defaultdict(list)
    typ_postings: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        toks = set(r["tokens"])
        for t in toks:
            postings[t].append(i)
        for t in set(r["mod_tokens"]) - toks:
            mod_postings[t].append(i)
        # only what the name does not already say -- a token in both fields
        # would otherwise be counted twice for the same declaration
        for t in set(r["typ_tokens"]) - toks:
            typ_postings[t].append(i)

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
        "typ_postings": dict(typ_postings),
        "trans": dict(trans),
        "meta": {
            "n_decls": len(rows),
            "n_holdout": len(holdout),
            "n_pmi_holdout": len(pmi_holdout),
            "n_tokens": len(idf),
            "n_trans_words": len(trans),
            "provenance": dict(Counter(r.get("provenance", "source") for r in rows)),
            # what the reconstruction did, and whether anything checked it
            "to_additive": ta_stats,
            "ground_truth_decls": len(truth) if truth is not None else 0,
        },
    }
    with gzip.open(os.path.join(out_dir, "index.pkl.gz"), "wb") as fh:
        pickle.dump(art, fh, protocol=4)
    # The same meta, readable without deserialising 240k rows. `setup` needs
    # `ground_truth_decls` to decide whether an existing index was built
    # against the elaborated environment, and paying a 4s index load to answer
    # one integer is what made that check not worth doing.
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(art["meta"], fh, indent=2)
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
