"""Side-aware structural matching: one level up from flat skeletons.

The skeleton matcher knows that `\\leq` and `\\bbH[` occur in the same
formula. This module additionally knows *where*: `H[..]` on the left of the
relation, `log` on the right, `+` inside the entropy's argument. That is the
difference between `entropy_le_log_card` and a converse statement, and it is
extracted by bracket-depth scanning rather than a grammar -- both sides
tokenize differently but nest identically.

Features per formula (side-tagged and nesting-tagged):

    root:le              the top-level relation
    L:app:h  R:op:log    heads and operators, tagged by side of the relation
    in:h:add             an operator occurring inside an application's argument

Same discipline as the skeleton stage: IDF weights from the corpus, only
informative features score, per-query gating, hyperparameters chosen on the
blueprint corpus with PFR held out until the final transfer.
"""

from __future__ import annotations

import re
from collections import Counter

from .structmatch import _strip_font

# ---------------------------------------------------------------------------
# tokenizers -- each yields (kind, name, depth, pos)
# ---------------------------------------------------------------------------

LATEX_REL_TOK = [("\\leqslant", "le"), ("\\leq", "le"), ("\\le", "le"),
                 ("\\geqslant", "ge"), ("\\geq", "ge"), ("\\ge", "ge"),
                 ("\\neq", "ne"), ("\\ne", "ne"), ("\\subseteq", "subset"),
                 ("\\in", "mem"), ("<", "lt"), (">", "gt"), ("=", "eq")]
LATEX_OP_TOK = [("\\sum", "sum"), ("\\prod", "prod"), ("\\log", "log"),
                ("\\exp", "exp"), ("\\int", "integral"), ("\\frac", "div"),
                ("\\sqrt", "sqrt"), ("\\min", "min"), ("\\max", "max"),
                ("\\inf", "inf"), ("\\sup", "sup"), ("\\cdot", "mul"),
                ("\\times", "mul"), ("\\circ", "comp"), ("+", "add")]
LATEX_APP_RE = re.compile(r"(?:\\([a-zA-Z]+)|(?<![a-zA-Z\\])([A-Za-z]))\s*\[")

LEAN_REL_TOK = [("≤", "le"), ("≥", "ge"), ("≠", "ne"), ("⊆", "subset"),
                ("∈", "mem"), ("<", "lt"), (">", "gt"), ("=", "eq")]
LEAN_OP_TOK = [("∑", "sum"), ("∏", "prod"), ("log", "log"), ("exp", "exp"),
               ("∫", "integral"), ("/", "div"), ("min", "min"), ("max", "max"),
               ("⨅", "inf"), ("⨆", "sup"), ("*", "mul"), ("∘", "comp"),
               ("+", "add")]
LEAN_APP_RE = re.compile(r"([A-Za-z][A-Za-z0-9']{0,3})\s*\[")

OPEN, CLOSE = "([{⟨", ")]}⟩"


def _scan(text: str, rel_toks, op_toks, app_re, skip_latex_cmds=False):
    """Yield (kind, name, depth, pos, app_span) with bracket depth tracked."""
    events = []
    depth = [0] * (len(text) + 1)
    d = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in OPEN:
            d += 1
        elif ch in CLOSE:
            d = max(0, d - 1)
        depth[i] = d
        i += 1

    # applications first, recording their bracket spans for nesting features
    app_spans = []
    for m in app_re.finditer(text):
        head = _strip_font((m.group(1) or m.group(2)))
        if not head or head in ("left", "right", "big", "bigg", "in"):
            continue
        # find matching close bracket for the '[' at m.end()-1
        j = m.end()
        dd = 1
        while j < len(text) and dd > 0:
            if text[j] == "[":
                dd += 1
            elif text[j] == "]":
                dd -= 1
            j += 1
        events.append(("app", head, depth[m.start()], m.start()))
        app_spans.append((head, m.end(), j - 1))

    taken = [False] * len(text)
    for tok, name in rel_toks:
        for m in re.finditer(re.escape(tok), text):
            if any(taken[m.start():m.end()]):
                continue
            if skip_latex_cmds and tok.startswith("\\") is False and \
                    m.start() > 0 and text[m.start() - 1] == "\\":
                continue
            for k in range(m.start(), m.end()):
                taken[k] = True
            events.append(("rel", name, depth[m.start()], m.start()))
    for tok, name in op_toks:
        for m in re.finditer(re.escape(tok), text):
            if any(taken[m.start():m.end()]):
                continue
            if tok.isalpha():
                a, b = m.start(), m.end()
                if (a > 0 and (text[a-1].isalpha() or text[a-1] == "\\")) or \
                        (b < len(text) and text[b].isalpha()):
                    continue
            events.append(("op", name, depth[m.start()], m.start()))
    return events, app_spans


def _features(events, app_spans) -> Counter:
    feats: Counter = Counter()
    if not events:
        return feats
    rels = [e for e in events if e[0] == "rel"]
    root = None
    if rels:
        mind = min(e[2] for e in rels)
        top = [e for e in rels if e[2] == mind]
        root = top[0]
        feats["root:" + root[1]] += 1
    for kind, name, _d, pos in events:
        if kind == "rel":
            continue
        tag = kind + ":" + name
        if root is not None:
            side = "L" if pos < root[3] else "R"
            feats[f"{side}:{tag}"] += 1
        feats[tag] += 1
    # nesting: operators inside an application's argument
    for head, a, b in app_spans:
        for kind, name, _d, pos in events:
            if kind == "op" and a <= pos < b:
                feats[f"in:{head}:{name}"] += 1
    return feats


def latex_tree(math_segments: list[str]) -> Counter:
    feats: Counter = Counter()
    for seg in math_segments:
        events, spans = _scan(seg, LATEX_REL_TOK, LATEX_OP_TOK, LATEX_APP_RE)
        feats.update(_features(events, spans))
    return feats


def lean_tree(head: str) -> Counter:
    from .structmatch import _statement_of
    stmt = _statement_of(head)
    events, spans = _scan(stmt, LEAN_REL_TOK, LEAN_OP_TOK, LEAN_APP_RE)
    return _features(events, spans)


# ---------------------------------------------------------------------------


# only side-tagged application heads and nested operators score;
# side-tagged bare operators (`L:op:add`) proved as noisy off-PFR as
# their untagged versions did in the skeleton stage
SCORING_PREFIXES = ("L:app", "R:app", "in:")


def tree_score(q: Counter, d: Counter, idf) -> float:
    core = [f for f in q if f.startswith(SCORING_PREFIXES)]
    qmass = sum(idf(f) for f in core)
    if qmass <= 0:
        return 0.0
    hit = sum(idf(f) for f in core if f in d)
    q_root = {f for f in q if f.startswith("root:")}
    d_root = {f for f in d if f.startswith("root:")}
    pen = 0.4 * sum(idf(f) for f in q_root - d_root) if d_root else 0.0
    return max(0.0, (hit - pen) / qmass)


class TreeReranker:
    def __init__(self, aligner, lam: float = 0.9, depth: int = 10000):
        import math as _m
        self.al = aligner
        self.lam = lam
        self.depth = depth
        self._cache: dict[int, Counter] = {}
        df: Counter = Counter()
        for i in range(len(aligner.rows)):
            df.update(set(self.doc_tree(i)))
        N = len(aligner.rows)
        self._idf = {f: _m.log(1 + N / (1 + c)) for f, c in df.items()}
        self._default = _m.log(1 + N)
        self._norm = max(self._idf.values()) if self._idf else 1.0

    def idf(self, f):
        return self._idf.get(f, self._default) / self._norm

    def doc_tree(self, rid: int) -> Counter:
        t = self._cache.get(rid)
        if t is None:
            t = lean_tree(self.al.rows[rid].get("head", ""))
            self._cache[rid] = t
        return t

    def rank(self, text, title, math_segments, topk=5, gate=0.5):
        qw = self.al.query_weights(text, title=title)
        res = self.al._score(qw, self.depth)
        if len(res) == 3 or res[0].size == 0:
            return [], []
        ids, scores, _m_, _r = res
        smax = float(scores[0]) or 1.0
        qt = latex_tree(math_segments)
        sts = [tree_score(qt, self.doc_tree(int(i)), self.idf) for i in ids]
        lam = self.lam if (sts and max(sts) >= gate) else 0.0
        rescored = [(float(sc) / smax + lam * st, int(i), st)
                    for i, sc, st in zip(ids, scores, sts)]
        rescored.sort(key=lambda x: -x[0])
        return [self.al.rows[i]["name"] for _s, i, _t in rescored[:topk]], \
            rescored[:topk]
