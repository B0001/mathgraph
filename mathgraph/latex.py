"""Pull the claim structure out of a LaTeX source.

A paper already contains a dependency graph; it is just written in a markup
language rather than stored as one. `\\label` and `\\ref` are the edges, and
theorem environments are the nodes. Recovering that costs almost nothing and
gives the alignment layer something to hang off.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

THEOREM_LIKE = {
    "theorem", "thm", "lemma", "lem", "proposition", "prop", "corollary",
    "cor", "definition", "defn", "def", "conjecture", "conj", "claim",
    "fact", "remark", "rem", "example", "ex", "observation", "obs",
    "assumption", "hypothesis", "axiom", "notation", "question", "problem",
}

NEWTHM_RE = re.compile(r"\\newtheorem\*?\{(?P<env>[^}]+)\}(?:\[[^\]]*\])?\{(?P<title>[^}]+)\}")
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
REF_RE = re.compile(r"\\(?:auto|c|C|eq|name|v)?ref\*?\{([^}]+)\}")
CITE_RE = re.compile(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]+)\}")
SECTION_RE = re.compile(r"\\(?:sub){0,2}section\*?\{([^}]*)\}")
# leanblueprint markup: an explicit, human-authored alignment already present
# in some sources. Treated as ground truth when available, never as a guess.
USES_RE = re.compile(r"\\uses\{([^}]*)\}")
LEAN_RE = re.compile(r"\\lean\{([^}]*)\}")
LEANOK_RE = re.compile(r"\\leanok\b")


@dataclass
class Block:
    id: str
    env: str
    kind: str                     # theorem | definition | proof | other
    title: str = ""
    label: str = ""
    text: str = ""
    refs: list = field(default_factory=list)
    cites: list = field(default_factory=list)
    section: str = ""
    line: int = 0
    proof_of: str = ""
    math: list = field(default_factory=list)   # raw math segments, verbatim
    uses: list = field(default_factory=list)
    declared_lean: list = field(default_factory=list)
    lean_ok: bool = False

    def to_json(self) -> dict:
        return asdict(self)


def _strip_comments(src: str) -> str:
    out = []
    for line in src.splitlines():
        i, esc = 0, False
        cut = len(line)
        while i < len(line):
            c = line[i]
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == "%":
                cut = i
                break
            i += 1
        out.append(line[:cut])
    return "\n".join(out)


MATH_PATTERNS = [
    re.compile(r"\\\[(.*?)\\\]", re.S),
    re.compile(r"\$\$(.*?)\$\$", re.S),
    re.compile(r"\$([^$]*)\$"),
    re.compile(r"\\begin\{(?:equation|align|gather|multline)\*?\}(.*?)"
               r"\\end\{(?:equation|align|gather|multline)\*?\}", re.S),
]


def extract_math(text: str) -> list[str]:
    out = []
    for pat in MATH_PATTERNS:
        out.extend(m.strip() for m in pat.findall(text) if m.strip())
    return out


def _flatten_math(text: str) -> str:
    """Replace math with a placeholder token in the prose view; the raw
    segments are kept separately on the block for formula-aware consumers."""
    for pat in MATH_PATTERNS:
        text = pat.sub(" MATH ", text)
    return text


def _clean(text: str) -> str:
    text = _flatten_math(text)
    text = LABEL_RE.sub(" ", text)
    text = CITE_RE.sub(" ", text)
    text = REF_RE.sub(" REF ", text)
    text = USES_RE.sub(" ", text)
    text = LEAN_RE.sub(" ", text)
    text = re.sub(r"\\(?:emph|textit|textbf|texttt|mathrm|text)\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z@]+\*?", " ", text)
    text = re.sub(r"[{}~\\]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse(src: str) -> list[Block]:
    src = _strip_comments(src)

    envs = dict(THEOREM_LIKE and {})
    for m in NEWTHM_RE.finditer(src):
        envs[m.group("env").strip()] = m.group("title").strip()
    known = set(envs) | THEOREM_LIKE | {"proof"}

    line_of = [0] * (len(src) + 1)
    ln = 1
    for i, ch in enumerate(src):
        line_of[i] = ln
        if ch == "\n":
            ln += 1
    line_of[len(src)] = ln

    # section context
    sections = [(m.start(), _clean(m.group(1))) for m in SECTION_RE.finditer(src)]

    def section_at(pos: int) -> str:
        cur = ""
        for p, name in sections:
            if p <= pos:
                cur = name
            else:
                break
        return cur

    blocks: list[Block] = []
    pat = re.compile(r"\\begin\{(" + "|".join(sorted(map(re.escape, known), key=len, reverse=True)) + r")\*?\}")
    n = 0
    last_theorem: str | None = None

    for m in pat.finditer(src):
        env = m.group(1)
        endpat = re.compile(r"\\end\{" + re.escape(env) + r"\*?\}")
        e = endpat.search(src, m.end())
        if not e:
            continue
        body = src[m.end(): e.start()]

        title = ""
        b = body.lstrip()
        if b.startswith("["):
            depth, j = 0, 0
            for j, ch in enumerate(b):
                depth += (ch == "[") - (ch == "]")
                if depth == 0:
                    break
            title = _clean(b[1:j])
            body = b[j + 1:]

        labels = LABEL_RE.findall(body)
        n += 1
        if env == "proof":
            kind = "proof"
        elif env.lower().startswith(("def", "notation")) or envs.get(env, "").lower().startswith(("definition", "notation")):
            kind = "definition"
        else:
            kind = "theorem"

        bid = labels[0] if labels else f"{env}:{n}"
        blk = Block(
            id=bid, env=env, kind=kind, title=title,
            label=labels[0] if labels else "",
            text=_clean(body),
            refs=sorted(set(r.strip() for grp in REF_RE.findall(body)
                            for r in grp.split(","))),
            cites=sorted(set(c.strip() for grp in CITE_RE.findall(body)
                             for c in grp.split(","))),
            section=section_at(m.start()),
            line=line_of[m.start()],
            math=extract_math(body),
            uses=sorted({u.strip() for grp in USES_RE.findall(body)
                         for u in grp.split(",") if u.strip()}),
            declared_lean=sorted({u.strip() for grp in LEAN_RE.findall(body)
                                  for u in grp.split(",") if u.strip()}),
            lean_ok=bool(LEANOK_RE.search(body)),
        )
        if kind == "proof" and last_theorem:
            blk.proof_of = last_theorem
        if kind in ("theorem", "definition"):
            last_theorem = bid
        blocks.append(blk)

    return blocks


def read_project(paths: list[str]) -> list[Block]:
    """Concatenate a multi-file paper in the order given (arXiv sources are
    usually a main file plus \\input sections)."""
    out: list[Block] = []
    for p in paths:
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            out.extend(parse(fh.read()))
    return out
