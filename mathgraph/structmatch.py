"""Structural matching between formulas and Lean statement heads.

The observation this is built on: formalizations carry the paper's own
notation. The PFR blueprint writes `d[X;Y] \\leq \\bbH[X+Y]`; the Lean
statement head reads `d[X ; \\mu # Y ; \\mu] \\le H[X + Y]`. The relation
symbol, the bracket-application heads, and the top-level operator shape all
survive translation nearly verbatim -- and none of them survive being
flattened to `MATH`, which is what every earlier stage here did.

So both sides are reduced to a skeleton -- relations, application heads,
operators, and relation|operand bigrams -- and the overlap reranks the
lexical top-K. Reranking rather than first-stage retrieval, because the
measured bottleneck is ranking: the lexical stage reaches the gold
declaration 97% of the time and puts it at median rank ~250.
"""

from __future__ import annotations

import re
from collections import Counter

# ---------------------------------------------------------------------------
# LaTeX side
# ---------------------------------------------------------------------------

LATEX_REL = [
    (r"\\leq?\b|\\leqslant\b", "le"), (r"\\geq?\b|\\geqslant\b", "ge"),
    (r"\\neq?\b|\\ne\b", "ne"), (r"\\subseteq?\b", "subset"),
    (r"\\in\b", "mem"), (r"\\to\b|\\rightarrow\b|\\mapsto\b", "map"),
    (r"<", "lt"), (r">", "gt"), (r"=", "eq"),
]
LATEX_OP = [
    (r"\\sum\b", "sum"), (r"\\prod\b", "prod"), (r"\\log\b", "log"),
    (r"\\exp\b", "exp"), (r"\\int\b", "integral"), (r"\\frac\b", "div"),
    (r"\\sqrt\b", "sqrt"), (r"\\min\b", "min"), (r"\\max\b", "max"),
    (r"\\inf\b", "inf"), (r"\\sup\b", "sup"), (r"\\lim\b", "lim"),
    (r"\\otimes\b", "tensor"), (r"\\circ\b", "comp"), (r"\\cup\b", "union"),
    (r"\\cap\b", "inter"), (r"\+", "add"), (r"(?<![-^_{])-(?![-}>])", "sub"),
    (r"\\cdot\b|\\times\b", "mul"), (r"\|", "norm"), (r"\\forall\b", "forall"),
    (r"\\exists\b", "exists"),
]
# `\bbH[` / `H[` / `d[` / `\rho(` -- the application head is the operator name
LATEX_APP = re.compile(r"(?:\\([a-zA-Z]+)|([A-Za-z]))\s*(?:\^\{?[^\[{]*\}?)?\[")
FONT_PREFIX = ("bb", "mathbb", "mathcal", "cal", "mathrm", "rm", "mathbf",
               "bf", "mathfrak", "frak", "wide", "var")


def _strip_font(cmd: str) -> str:
    low = cmd.lower()
    for p in FONT_PREFIX:
        if low.startswith(p) and len(low) > len(p):
            return low[len(p):]
    return low


def latex_skeleton(math_segments: list[str]) -> Counter:
    feats: Counter = Counter()
    rels, apps = [], []
    for seg in math_segments:
        for pat, name in LATEX_REL:
            if re.search(pat, seg):
                feats["rel:" + name] += 1
                rels.append(name)
        for pat, name in LATEX_OP:
            if re.search(pat, seg):
                feats["op:" + name] += 1
        for m in LATEX_APP.finditer(seg):
            head = _strip_font(m.group(1) or m.group(2))
            if head and head not in ("left", "right", "big", "bigg"):
                feats["app:" + head] += 1
                apps.append(head)
    for r in set(rels):
        for a in set(apps):
            feats[f"bi:{r}|{a}"] += 1
    return feats


# ---------------------------------------------------------------------------
# Lean side
# ---------------------------------------------------------------------------

LEAN_REL = [("≤", "le"), ("≥", "ge"), ("≠", "ne"), ("⊆", "subset"),
            ("∈", "mem"), ("→", "map"), ("<", "lt"), (">", "gt"), ("=", "eq")]
LEAN_OP = [("∑", "sum"), ("∏", "prod"), ("log", "log"), ("exp", "exp"),
           ("∫", "integral"), ("/", "div"), ("min", "min"), ("max", "max"),
           ("⨅", "inf"), ("⨆", "sup"), ("∪", "union"), ("∩", "inter"),
           ("∘", "comp"), ("+", "add"), ("*", "mul"), ("‖", "norm"),
           ("|", "norm"), ("∀", "forall"), ("∃", "exists"), (" - ", "sub")]
LEAN_APP = re.compile(r"([A-Za-zₐ-ₜ'!?][A-Za-z0-9ₐ-ₜ'!?]*)\s*\[")


def _statement_of(head: str) -> str:
    """The proposition is what follows the last top-level colon before `:=`.
    Heuristic on the raw head text; binder colons inside (...) {...} [...]
    are skipped by depth tracking."""
    head = head.split(":=")[0]
    depth = 0
    last = -1
    for i, ch in enumerate(head):
        if ch in "([{⟨":
            depth += 1
        elif ch in ")]}⟩":
            depth -= 1
        elif ch == ":" and depth <= 0:
            last = i
    return head[last + 1:] if last >= 0 else head


def lean_skeleton(head: str) -> Counter:
    stmt = _statement_of(head)
    feats: Counter = Counter()
    rels, apps = [], []
    for sym, name in LEAN_REL:
        if sym in stmt:
            feats["rel:" + name] += 1
            rels.append(name)
    for sym, name in LEAN_OP:
        if sym in stmt:
            feats["op:" + name] += 1
    for m in LEAN_APP.finditer(stmt):
        ident = m.group(1).lower()
        # `Finset.sum s [ ...` style false positives are rare in heads; keep
        # short notation heads which is what papers use (H, d, I, rho)
        if 1 <= len(ident) <= 4:
            feats["app:" + ident] += 1
            apps.append(ident)
    for r in set(rels):
        for a in set(apps):
            feats[f"bi:{r}|{a}"] += 1
    return feats


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def match_score(q: Counter, d: Counter, idf) -> float:
    """IDF-weighted overlap, normalised by the query skeleton's own weighted
    mass. Hand-set feature-class weights were tried first and failed off-PFR:
    `rel:le` appears in a third of all statement heads and matched everything,
    while `app:h` is rare and nearly conclusive. Corpus statistics encode
    exactly that distinction, so the corpus sets the weights."""
    if not q:
        return 0.0
    # Only application-heads and relation|head bigrams score positively.
    # Bare relations and operators (`rel:le`, `op:add`) appear in a large
    # fraction of all statement heads; measured per project they carried the
    # noise while app:/bi: carried the signal. Relations still act through
    # the contradiction penalty below.
    core = [f for f in q if f.startswith(("app:", "bi:"))]
    qmass = sum(idf(f) for f in core)
    if qmass <= 0:
        return 0.0
    hit = sum(idf(f) for f in core if f in d)
    # relation contradiction is evidence against, not mere absence of evidence
    q_rels = {f for f in q if f.startswith("rel:")}
    d_rels = {f for f in d if f.startswith("rel:")}
    pen = 0.3 * sum(idf(f) for f in q_rels - d_rels) if d_rels else 0.0
    return max(0.0, (hit - pen) / qmass)


class StructReranker:
    def __init__(self, aligner, lam: float = 0.8, depth: int = 200):
        self.al = aligner
        self.lam = lam
        self.depth = depth
        self._cache: dict[int, Counter] = {}
        # document frequency of structural features over the whole corpus
        import math as _math
        df: Counter = Counter()
        for i in range(len(aligner.rows)):
            df.update(set(self.doc_skel(i)))
        N = len(aligner.rows)
        self._idf = {f: _math.log(1 + N / (1 + c)) for f, c in df.items()}
        self._idf_default = _math.log(1 + N)
        self._idf_norm = max(self._idf.values()) if self._idf else 1.0

    def idf(self, f: str) -> float:
        return self._idf.get(f, self._idf_default) / self._idf_norm

    def doc_skel(self, rid: int) -> Counter:
        sk = self._cache.get(rid)
        if sk is None:
            sk = lean_skeleton(self.al.rows[rid].get("head", ""))
            self._cache[rid] = sk
        return sk

    def rank(self, text: str, title: str, math_segments: list[str],
             topk: int = 5, gate: float = 0.45):
        qw = self.al.query_weights(text, title=title)
        res = self.al._score(qw, self.depth)
        if len(res) == 3 or res[0].size == 0:
            return [], []
        ids, scores, _m, _r = res
        smax = float(scores[0]) or 1.0
        qsk = latex_skeleton(math_segments)
        sts = [match_score(qsk, self.doc_skel(int(i)), self.idf) for i in ids]
        # Per-query gate. Structural match only means something when the
        # formalization preserved the paper's notation; measured per project,
        # reranking helps exactly where skeleton overlap with gold is high
        # (carleson, PFR) and hurts where it is low (ergodic-theory). Whether
        # notation survived is visible from the query's own candidate list:
        # if no candidate matches the skeleton well, the signal is absent --
        # switch it off rather than inject noise.
        lam = self.lam if (sts and max(sts) >= gate) else 0.0
        rescored = [(float(sc) / smax + lam * st, int(i), st)
                    for i, sc, st in zip(ids, scores, sts)]
        rescored.sort(key=lambda x: -x[0])
        top = rescored[:topk]
        return [self.al.rows[i]["name"] for _s, i, _t in top], top
