"""Read the formulas instead of discarding them.

Papers put the mathematical relation in the symbols: `\\bbH[X] \\leq \\log |S|`
carries "entropy", "le", and "log" -- none of which survive flattening the
math to a placeholder. Every retrieval variant in this repository so far has
been reading the connective English around the formulas and throwing away the
content. This module is the first step in reversing that.

Two kinds of signal are extracted from a math segment:

  commands    \\log, \\leq, \\sum, \\dist, \\bbH ...  including author-defined
              macros, which is where papers hide their key operators
  structure   relation symbols and bracket operators (=, <, [ ] applications)

and a symbol -> declaration-token translation table is learned by PMI over
the harvested blueprint corpus -- the same trick as the English table, on the
vocabulary the English table cannot see. Author macros are per-paper, so the
table also falls back to splitting unknown commands into letter runs
(`\\bbH` -> `h`; `\\dist` -> `dist`) which mathlib names often contain.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict

CMD_RE = re.compile(r"\\([a-zA-Z]+)")
REL_MAP = {
    "=": "eq", "<": "lt", ">": "gt", "+": "add", "-": "sub", "*": "mul",
    "/": "div", "!": "factorial",
}
CMD_NORMALIZE = {
    "leq": "le", "geq": "ge", "le": "le", "ge": "ge", "neq": "ne", "ne": "ne",
    "cdot": "mul", "times": "mul", "frac": "div", "sum": "sum", "prod": "prod",
    "log": "log", "exp": "exp", "sqrt": "sqrt", "inf": "inf", "sup": "sup",
    "min": "min", "max": "max", "lim": "tendsto", "int": "integral",
    "subseteq": "subset", "subset": "subset", "in": "mem", "cup": "union",
    "cap": "inter", "setminus": "sdiff", "emptyset": "empty",
    "forall": "forall", "exists": "exists", "mapsto": "map", "to": "map",
    "circ": "comp", "otimes": "tensor", "oplus": "sum", "langle": "inner",
    "norm": "norm", "abs": "abs", "floor": "floor", "ceil": "ceil",
}
SKIP = {"left", "right", "big", "bigg", "Big", "Bigg", "quad", "qquad", "",
        "mathrm", "mathbf", "mathcal", "mathbb", "mathfrak", "mathsf",
        "text", "textrm", "operatorname", "limits", "nolimits", "displaystyle",
        "label", "notag", "nonumber", "begin", "end", "item", "cref", "ref",
        "eqref", "hspace", "vspace", "phantom", "dots", "ldots", "cdots",
        "vdots", "ddots", "prime", ",", ";", ":"}


def _letters(cmd: str) -> list[str]:
    """Fallback for unknown/author macros: strip font prefixes, lowercase."""
    for pre in ("bb", "bf", "cal", "frak", "sf", "rm", "var", "wide", "over"):
        if cmd.startswith(pre) and len(cmd) > len(pre) + 0:
            cmd = cmd[len(pre):] or cmd
            break
    cmd = cmd.lower()
    return [cmd] if 1 <= len(cmd) <= 12 else []


def symbols(math_segments: list[str]) -> list[str]:
    out: list[str] = []
    for seg in math_segments:
        for m in CMD_RE.finditer(seg):
            cmd = m.group(1)
            if cmd in SKIP:
                continue
            norm = CMD_NORMALIZE.get(cmd)
            if norm:
                out.append("m:" + norm)
            else:
                out.extend("m:" + w for w in _letters(cmd))
        stripped = CMD_RE.sub(" ", seg)
        for ch, name in REL_MAP.items():
            if ch in stripped:
                out.append("m:" + name)
        if "[" in seg and "]" in seg:
            out.append("m:apply")
    return out


# ---------------------------------------------------------------------------
# symbol -> declaration-token PMI, learned from blueprint pairs
# ---------------------------------------------------------------------------


def train_table(pairs_with_math: list[dict], rows_by_name: dict,
                min_pair=3, shrink=8.0) -> dict:
    pair_c: Counter = Counter()
    s_c: Counter = Counter()
    t_c: Counter = Counter()
    total = 0
    for p in pairs_with_math:
        syms = set(symbols(p.get("math", [])))
        row = None
        for t in p["targets"]:
            row = rows_by_name.get(t)
            if row is not None:
                break
        if row is None or not syms:
            continue
        toks = set(row["tokens"])
        for s in syms:
            s_c[s] += 1
        for t in toks:
            t_c[t] += 1
        for s in syms:
            for t in toks:
                pair_c[(s, t)] += 1
                total += 1
    table: dict[str, list] = defaultdict(list)
    for (s, t), c in pair_c.items():
        if c < min_pair or s_c[s] < min_pair or t_c[t] < min_pair:
            continue
        pmi = math.log((c * total) / (s_c[s] * t_c[t]) + 1e-12)
        if pmi <= 0:
            continue
        table[s].append((t, pmi * c / (c + shrink)))
    for s in table:
        table[s].sort(key=lambda x: -x[1])
        del table[s][10:]
        mx = table[s][0][1] or 1.0
        table[s] = [(t, w / mx) for t, w in table[s]]
    return dict(table)


def symbol_weights(math_segments: list[str], table: dict, aligner,
                   direct_scale=0.9, table_scale=0.8, k=6) -> dict[str, float]:
    """Extra query-token weights derived from the formulas.

    Direct route: `m:log` bumps the mathlib token `log` if it exists.
    Learned route: the PMI table maps symbols to tokens they co-occur with
    in other formalized papers.
    """
    w: dict[str, float] = {}

    def bump(tok, val):
        if tok in aligner.idf and len(aligner.post.get(tok, ())) <= aligner.max_df:
            if w.get(tok, 0.0) < val:
                w[tok] = val

    for s in set(symbols(math_segments)):
        bare = s[2:]
        bump(bare, direct_scale)
        for tok, sc in table.get(s, ())[:k]:
            bump(tok, table_scale * sc)
    return w


if __name__ == "__main__":
    segs = ["\\bbH[X] \\leq \\log |S|", "d[X;Y] = 0"]
    print(symbols(segs))
