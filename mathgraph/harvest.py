"""Harvest a paper-distribution parallel corpus.

Library docstrings are the wrong distribution for aligning papers: short,
library vocabulary, describing the declaration's own concepts. `leanblueprint`
projects are the right one -- ordinary mathematical prose with `\\lean{...}`
annotations written by the authors, which is exactly (paper statement,
declaration) supervision.

There is not much of it. That is the point: it does not need to be large to
move an encoder that already works in-distribution, it needs to be the right
shape.
"""

from __future__ import annotations

import json
import os
import sys

from .latex import parse
from .leanscan import scan_file


def find_tex(root: str) -> list[str]:
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".lake", ".git", "node_modules")]
        for fn in files:
            if fn.endswith(".tex"):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def find_lean(root: str) -> list[str]:
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".lake", ".git", "lake-packages")]
        for fn in files:
            if fn.endswith(".lean"):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def harvest_project(root: str) -> tuple[list[dict], list[dict]]:
    """Returns (pairs, declarations) for one project."""
    decls = []
    for path in find_lean(root):
        rel = os.path.relpath(path, root)
        module = rel[:-5].replace(os.sep, ".")
        for d in scan_file(path, module):
            decls.append(d.to_json())
    known = {d["name"] for d in decls}

    pairs = []
    for path in find_tex(root):
        try:
            src = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if "\\lean{" not in src:
            continue
        for b in parse(src):
            if not b.declared_lean or b.kind == "proof":
                continue
            text = (b.title + ". " + b.text).strip(". ").strip()
            if len(text.split()) < 5:
                continue
            targets = [t for t in b.declared_lean if t in known]
            if not targets:
                continue
            pairs.append({"text": text, "title": b.title, "targets": targets,
                          "math": b.math,
                          "project": os.path.basename(root), "id": b.id})
    return pairs, decls


def harvest(roots: list[str], exclude: set[str]) -> tuple[list[dict], list[dict]]:
    allp, alld = [], []
    for root in roots:
        name = os.path.basename(root.rstrip("/"))
        if name in exclude:
            continue
        p, d = harvest_project(root)
        if p:
            print(f"  {name:38s} {len(p):5d} pairs  {len(d):6d} decls",
                  file=sys.stderr)
        allp.extend(p)
        alld.extend(d)
    return allp, alld


if __name__ == "__main__":
    base = sys.argv[1]
    out_pairs, out_decls = sys.argv[2], sys.argv[3]
    excl = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else set()
    roots = [os.path.join(base, d) for d in sorted(os.listdir(base))
             if os.path.isdir(os.path.join(base, d))]
    pairs, decls = harvest(roots, excl)
    with open(out_pairs, "w", encoding="utf-8") as fh:
        for p in pairs:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    seen = set()
    with open(out_decls, "w", encoding="utf-8") as fh:
        for d in decls:
            if d["name"] in seen:
                continue
            seen.add(d["name"])
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"{len(pairs)} pairs, {len(seen)} declarations")
