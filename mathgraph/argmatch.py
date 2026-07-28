"""Argument identity, without elaboration.

The tree stage knows `d[..]` is left of the relation and `H[..]` right. This
stage additionally knows the *arguments are the same variables*: in
`d[X;Y] \\leq \\bbH[X+Y]`, the two arguments of `d` reappear summed inside
`H`. That sharing pattern is invariant under renaming -- the paper may say
X,Y and a survey may say A,B -- so variables are canonicalised by order of
first appearance (alpha-invariance) and the whole formula collapses to a
pattern string:

    le( d[v0,v1] | h[v0+v1] )

emitted from LaTeX and from the Lean head by different tokenizers that agree
on the canonical form. A pattern feature is extremely sparse and nearly
conclusive when it fires -- the profile the verification layer wants, and the
opposite profile from the lexical stage. Notation quirks are normalised per
side: Lean's `d[X ; \\mu # Y ; \\mu]` carries measure annotations after `;`
that the paper's `d[X;Y]` omits, so `#` splits arguments and `;` truncates
them.
"""

from __future__ import annotations

import re
from collections import Counter

from .structmatch import _strip_font, _statement_of

VAR_RE = re.compile(r"\b([A-Za-z])(?:_\{?([0-9])\}?)?('?)")
LATEX_APP_RE = re.compile(r"(?:\\([a-zA-Z]+)|(?<![a-zA-Z\\])([A-Za-z]))\s*\[")
LEAN_APP_RE = re.compile(r"([A-Za-z][A-Za-z0-9']{0,3})\s*\[")
LATEX_RELS = [("\\leqslant", "le"), ("\\leq", "le"), ("\\le", "le"),
              ("\\geqslant", "ge"), ("\\geq", "ge"), ("\\ge", "ge"),
              ("\\neq", "ne"), ("=", "eq"), ("<", "lt"), (">", "gt")]
LEAN_RELS = [("≤", "le"), ("≥", "ge"), ("≠", "ne"), ("=", "eq"),
             ("<", "lt"), (">", "gt")]
NOISE_HEADS = {"left", "right", "big", "bigg", "in", "fin", "zmod", "set"}


def _bracket_span(text: str, start: int) -> int:
    d = 1
    j = start
    while j < len(text) and d:
        if text[j] == "[":
            d += 1
        elif text[j] == "]":
            d -= 1
        j += 1
    return j - 1


def _apps(text: str, app_re) -> list[tuple[str, str, int]]:
    out = []
    for m in app_re.finditer(text):
        head = _strip_font(m.group(1) or (m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)) or "")
        if not head or head in NOISE_HEADS:
            continue
        end = _bracket_span(text, m.end())
        out.append((head, text[m.end(): end], m.start()))
    return out


def _canon_arg(arg: str, varmap: dict[str, str], lean: bool) -> str:
    if lean:
        arg = arg.split(";")[0]           # drop measure annotation
    ops = []
    if "+" in arg:
        ops.append("+")
    if re.search(r"(?<![-^_{])-", arg):
        ops.append("-")
    vs = []
    for m in VAR_RE.finditer(arg):
        name = m.group(1) + (m.group(2) or "") + (m.group(3) or "")
        if len(m.group(1)) == 1 and m.group(1).isalpha():
            if name not in varmap:
                varmap[name] = f"v{len(varmap)}"
            if varmap[name] not in vs:
                vs.append(varmap[name])
    if not vs:
        return "?"
    joiner = ops[0] if ops else ","
    return joiner.join(vs)


def _split_args(argtext: str, lean: bool) -> list[str]:
    sep = "#" if (lean and "#" in argtext) else (";" if ";" in argtext else ",")
    parts = [p for p in argtext.split(sep) if p.strip()]
    return parts if parts else [argtext]


def patterns(text: str, lean: bool) -> Counter:
    rels = LEAN_RELS if lean else LATEX_RELS
    if lean:
        text = _statement_of(text)
    feats: Counter = Counter()
    # top-level relation split (depth 0)
    depth = 0
    rel_at = None
    taken = set()
    for tok, name in rels:
        for m in re.finditer(re.escape(tok), text):
            if m.start() in taken:
                continue
            d = 0
            for ch in text[: m.start()]:
                if ch in "([{⟨":
                    d += 1
                elif ch in ")]}⟩":
                    d -= 1
            if d == 0 and rel_at is None:
                rel_at = (name, m.start(), m.end())
            for k in range(m.start(), m.end()):
                taken.add(k)
    if rel_at is None:
        return feats
    rel, a, b = rel_at
    varmap: dict[str, str] = {}
    sides = []
    for seg in (text[:a], text[b:]):
        descs = []
        for head, argtext, _pos in _apps(seg, LEAN_APP_RE if lean else LATEX_APP_RE):
            args = [_canon_arg(x, varmap, lean) for x in _split_args(argtext, lean)]
            if all(x == "?" for x in args):
                continue
            descs.append(f"{head}[{','.join(args)}]")
        sides.append("+".join(sorted(descs)) if descs else "")
    if sides[0] or sides[1]:
        if rel in ("eq", "ne"):
            # symmetric relation: canonical side order
            a_, b_ = sorted(sides)
            feats[f"pat:{rel}({a_}|{b_})"] += 1
        else:
            feats[f"pat:{rel}({sides[0]}|{sides[1]})"] += 1
    # per-application canonical shapes, side-free (partial credit)
    for head, argtext, _pos in _apps(text, LEAN_APP_RE if lean else LATEX_APP_RE):
        args = [_canon_arg(x, dict(varmap), lean) for x in _split_args(argtext, lean)]
        if any(x != "?" for x in args):
            feats[f"shape:{head}[{','.join(args)}]"] += 1
    return feats


def latex_patterns(math_segments: list[str]) -> Counter:
    feats: Counter = Counter()
    for seg in math_segments:
        feats.update(patterns(seg, lean=False))
    return feats


HYP_RE = re.compile(r"[({\[]([^():]*?:[^()]*?)[)}\]]")


def _hypothesis_bodies(head: str) -> list[str]:
    """Formulas frequently live in hypothesis binders -- `(hdist : d[X # X]
    = 0)` -- which a conclusion-only reading misses entirely (measured on
    PFR: most gold formulas sit there). Take the body after the first colon
    of every bracketed group."""
    head = head.split(":=")[0]
    out = []
    depth = 0
    start = None
    for i, ch in enumerate(head):
        if ch == "(":
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start is not None:
                body = head[start:i]
                if ":" in body:
                    out.append(body.split(":", 1)[1])
                start = None
    return out


def lean_patterns(head: str) -> Counter:
    feats = patterns(head, lean=True)
    for body in _hypothesis_bodies(head):
        feats.update(patterns(body + " ", lean=True))
    return feats


def pattern_score(q: Counter, d: Counter, idf) -> float:
    if not q:
        return 0.0
    qmass = sum(idf(f) for f in q)
    if qmass <= 0:
        return 0.0
    return sum(idf(f) for f in q if f in d) / qmass
