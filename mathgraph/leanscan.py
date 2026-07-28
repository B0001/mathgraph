"""Extract declarations from Lean 4 source.

Line-oriented scanner. It does not typecheck anything -- it recovers the
declaration name, kind, enclosing namespace, docstring and the head of the
statement. That is all the alignment layer needs, and it means the index can
be built from a source checkout without a Lean toolchain.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict, field
from typing import Iterator, Optional

DECL_KINDS = (
    "theorem", "lemma", "def", "abbrev", "instance", "structure", "class",
    "inductive", "opaque", "axiom", "alias",
)

_MODIFIERS = r"(?:private\s+|protected\s+|noncomputable\s+|nonrec\s+|partial\s+|unsafe\s+|scoped\s+|local\s+)*"
_IDENT = r"[A-Za-z_\u03b1-\u03c9\u0391-\u03a9][A-Za-z0-9_'!?\u2080-\u2089\u03b1-\u03c9\u0391-\u03a9\.]*"

DECL_RE = re.compile(rf"^{_MODIFIERS}(?P<kind>{'|'.join(DECL_KINDS)})\s+(?P<name>{_IDENT})")
# `instance` may be anonymous: `instance : Foo Bar := ...`
ANON_INSTANCE_RE = re.compile(rf"^{_MODIFIERS}instance\b\s*(?::|\{{)")
NAMESPACE_RE = re.compile(rf"^namespace\s+(?P<name>{_IDENT})")
SECTION_RE = re.compile(rf"^section(?:\s+(?P<name>{_IDENT}))?\s*$")
END_RE = re.compile(rf"^end(?:\s+(?P<name>{_IDENT}))?\s*$")
DOC_OPEN_RE = re.compile(r"^\s*/--")
ATTR_RE = re.compile(r"^\s*@\[")


@dataclass
class Decl:
    name: str            # fully qualified
    kind: str
    module: str          # Mathlib.Order.Lattice
    line: int
    doc: str = ""
    head: str = ""       # first ~2 lines of the statement
    namespace: str = ""
    attrs: str = ""      # raw attribute line(s) preceding the declaration
    provenance: str = "source"
    tokens: list = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def _clean_doc(raw: str) -> str:
    body = raw.strip()
    if body.startswith("/--"):
        body = body[3:]
    if body.endswith("-/"):
        body = body[:-2]
    lines = [ln.strip() for ln in body.splitlines()]
    return " ".join(ln for ln in lines if ln).strip()


def scan_file(path: str, module: str) -> Iterator[Decl]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except (OSError, UnicodeDecodeError):
        return

    ns_stack: list[tuple[str, Optional[str]]] = []
    pending_doc = ""
    pending_attrs: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.rstrip("\n")

        # --- docstring block ---
        if DOC_OPEN_RE.match(stripped):
            buf = [stripped]
            if "-/" not in stripped[stripped.index("/--") + 3:]:
                j = i + 1
                while j < n and "-/" not in lines[j]:
                    buf.append(lines[j].rstrip("\n"))
                    j += 1
                if j < n:
                    buf.append(lines[j].rstrip("\n"))
                i = j
            pending_doc = _clean_doc("\n".join(buf))
            i += 1
            continue

        # attributes keep a pending docstring alive
        if ATTR_RE.match(stripped):
            buf = [stripped]
            j = i
            while "]" not in buf[-1] and j + 1 < n:
                j += 1
                buf.append(lines[j].rstrip("\n"))
            pending_attrs.append(" ".join(x.strip() for x in buf))
            i = j + 1
            continue

        m = NAMESPACE_RE.match(stripped)
        if m:
            ns_stack.append(("namespace", m.group("name")))
            pending_doc = ""
            pending_attrs = []
            i += 1
            continue

        m = SECTION_RE.match(stripped)
        if m:
            ns_stack.append(("section", m.group("name")))
            pending_doc = ""
            pending_attrs = []
            i += 1
            continue

        m = END_RE.match(stripped)
        if m:
            if ns_stack:
                ns_stack.pop()
            pending_doc = ""
            pending_attrs = []
            i += 1
            continue

        if ANON_INSTANCE_RE.match(stripped):
            pending_doc = ""
            pending_attrs = []
            i += 1
            continue

        m = DECL_RE.match(stripped)
        if m:
            local = m.group("name")
            kind = m.group("kind")
            ns = ".".join(nm for tag, nm in ns_stack if tag == "namespace" and nm)
            full = f"{ns}.{local}" if ns else local
            head_lines = [stripped]
            k = i + 1
            while k < n and len(head_lines) < 3 and not lines[k].strip().startswith(("theorem", "lemma", "def", "/--")):
                if ":=" in head_lines[-1] or "where" in head_lines[-1]:
                    break
                head_lines.append(lines[k].rstrip("\n"))
                k += 1
            yield Decl(
                name=full,
                kind="theorem" if kind == "lemma" else kind,
                module=module,
                line=i + 1,
                doc=pending_doc,
                head=" ".join(x.strip() for x in head_lines)[:400],
                namespace=ns,
                attrs=" ".join(pending_attrs),
            )
            pending_doc = ""
            pending_attrs = []
            i += 1
            continue

        if stripped.strip():
            pending_doc = "" if not stripped.strip().startswith("--") else pending_doc
        i += 1


def scan_tree(root: str, limit: Optional[int] = None) -> Iterator[Decl]:
    count = 0
    for dirpath, _dirs, files in os.walk(root):
        for fn in sorted(files):
            if not fn.endswith(".lean"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, os.path.dirname(root.rstrip("/")))
            module = rel[:-5].replace(os.sep, ".")
            for decl in scan_file(path, module):
                yield decl
                count += 1
                if limit and count >= limit:
                    return


def write_index(root: str, out_path: str) -> int:
    n = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for decl in scan_tree(root):
            fh.write(json.dumps(decl.to_json(), ensure_ascii=False) + "\n")
            n += 1
    return n


if __name__ == "__main__":
    import sys
    src, dst = sys.argv[1], sys.argv[2]
    print(write_index(src, dst))
