"""Ingest elaborated Lean types produced by `lean/DumpDecls.lean`.

Everything else in this package recovers declaration types by scraping source
text with regexes. That works without a Lean toolchain, which is why it is
the default -- but it loses precisely what elaboration adds:

  * notation resolved to underlying constants
  * implicit arguments and instances made explicit
  * the ~14k `@[to_additive]` declarations present with real types instead of
    reconstructed names
  * multi-line statements joined and normalised

The ingest converts each elaborated type into the same `head` shape the
existing scanner produces (`theorem <name> : <type>`), so `structmatch`,
`treematch` and `argmatch` consume it with no changes at all. That is the
point of the shape: the structural matchers were written against a text
interface, so improving the text improves them for free.

Requires a built mathlib (`lake exe cache get && lake build`) -- roughly
15 GB and an hour on a laptop, most of it the cache download. Untested in
the environment this package was developed in, which had no toolchain; the
regex path is unaffected and remains the default.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from .names import split_name

KIND_MAP = {"theorem": "theorem", "def": "def", "axiom": "axiom",
            "inductive": "inductive", "opaque": "opaque",
            "ctor": "ctor", "rec": "rec", "quot": "quot"}
SKIP_KINDS = {"ctor", "rec", "quot"}


def dump(mathlib_dir: str, script: str | None = None,
         out: str | None = None) -> str:
    """Run the Lean dumper inside a built mathlib checkout."""
    script = script or os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "lean", "DumpDecls.lean")
    if not os.path.isdir(mathlib_dir):
        raise SystemExit(f"no mathlib checkout at {mathlib_dir}")
    dest = os.path.join(mathlib_dir, "DumpDecls.lean")
    with open(script, encoding="utf-8") as src, open(dest, "w", encoding="utf-8") as dst:
        dst.write(src.read())
    print("[mathgraph] running lake env lean DumpDecls.lean "
          "(needs a built mathlib; several minutes)", flush=True)
    r = subprocess.run(["lake", "env", "lean", "DumpDecls.lean"],
                       cwd=mathlib_dir, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(r.stdout[-4000:])
    produced = os.path.join(mathlib_dir, "decls_elab.jsonl")
    if r.returncode or not os.path.exists(produced):
        raise SystemExit("lean dump failed -- is mathlib built? "
                         "(lake exe cache get && lake build)")
    if out and out != produced:
        os.replace(produced, out)
        return out
    return produced


def to_index_rows(elab_path: str, out_path: str) -> int:
    """Convert the elaborated dump into the scanner's row format."""
    n = 0
    with open(elab_path, encoding="utf-8") as fh, \
            open(out_path, "w", encoding="utf-8") as out:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = KIND_MAP.get(d.get("kind", "theorem"), "theorem")
            if kind in SKIP_KINDS:
                continue
            name = d["name"]
            module = d.get("module", "")
            typ = " ".join(d.get("type", "").split())
            row = {
                "name": name,
                "kind": kind,
                "module": module,
                "line": 0,
                "doc": "",
                # same shape the regex scanner emits, so every downstream
                # structural matcher works unchanged
                "head": f"{kind} {name.split('.')[-1]} : {typ}",
                "namespace": ".".join(name.split(".")[:-1]),
                "attrs": "",
                "provenance": "elaborated",
                "tokens": split_name(name),
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


def merge_docs(elab_rows: str, source_rows: str, out_path: str) -> int:
    """Carry docstrings over from the source scan.

    The elaborated dump has real types but no docstrings; the source scan has
    docstrings but scraped types. The union is strictly better than either,
    and the docstrings are what the PMI translation table trains on.
    """
    docs = {}
    for line in open(source_rows, encoding="utf-8"):
        d = json.loads(line)
        if d.get("doc"):
            docs[d["name"]] = d["doc"]
    n = 0
    with open(elab_rows, encoding="utf-8") as fh, \
            open(out_path, "w", encoding="utf-8") as out:
        for line in fh:
            d = json.loads(line)
            if not d.get("doc") and d["name"] in docs:
                d["doc"] = docs[d["name"]]
            out.write(json.dumps(d, ensure_ascii=False) + "\n")
            n += 1
    return n


if __name__ == "__main__":
    mathlib = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "mathlib_elab.jsonl"
    raw = dump(mathlib)
    print(to_index_rows(raw, out), "rows ->", out)
