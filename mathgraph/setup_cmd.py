"""`mathgraph setup` -- fetch the corpora and build the indices locally.

Everything this tool needs is derived from public repositories, so nothing
large ships in the wheel. The bootstrap is deliberately resumable: each stage
checks for its own output and skips if present, because the mathlib clone is
the slow part and nobody should pay for it twice.

Disk: ~400 MB checkouts, ~120 MB indices. Time: a few minutes, dominated by
the clone.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

MATHLIB_URL = "https://github.com/leanprover-community/mathlib4.git"
# Blueprint projects: paper prose with author-written \lean{} annotations.
# PFR is held out as the evaluation set and cloned separately.
BLUEPRINTS = [
    "https://github.com/teorth/pfr.git",
    "https://github.com/fpvandoorn/carleson.git",
    "https://github.com/ImperialCollegeLondon/FLT.git",
    "https://github.com/teorth/equational_theories.git",
    "https://github.com/leanprover-community/con-nf.git",
    "https://github.com/YaelDillies/LeanAPAP.git",
]


def _run(cmd, cwd=None, timeout=1800):
    return subprocess.run(cmd, cwd=cwd, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True)


def _log(msg):
    print(f"[mathgraph] {msg}", flush=True)


def clone_mathlib(root: str) -> str:
    dest = os.path.join(root, "mathlib4")
    if os.path.isdir(os.path.join(dest, "Mathlib")):
        _log("mathlib4 present, skipping clone")
        return dest
    _log("cloning mathlib4 (sparse, blobless -- a few minutes)")
    r = _run(["git", "clone", "--depth", "1", "--filter=blob:none",
              "--sparse", MATHLIB_URL, dest])
    if r.returncode:
        raise SystemExit(f"clone failed:\n{r.stdout[-2000:]}")
    r = _run(["git", "sparse-checkout", "set", "Mathlib"], cwd=dest)
    if r.returncode:
        raise SystemExit(f"sparse-checkout failed:\n{r.stdout[-2000:]}")
    return dest


def clone_blueprints(root: str) -> str:
    bp = os.path.join(root, "blueprints")
    os.makedirs(bp, exist_ok=True)
    for url in BLUEPRINTS:
        name = url.rsplit("/", 1)[-1][:-4]
        dest = os.path.join(bp, name)
        if os.path.isdir(dest):
            continue
        _log(f"cloning {name}")
        r = _run(["git", "clone", "--depth", "1", url, dest], timeout=900)
        if r.returncode:
            _log(f"  skipped ({name} unavailable)")
            shutil.rmtree(dest, ignore_errors=True)
    return bp


def build_all(root: str, bp_dir: str, mathlib_dir: str) -> dict:
    from .leanscan import write_index
    from .index import build
    from .harvest import harvest

    art = os.path.join(root, "artifacts")
    os.makedirs(art, exist_ok=True)
    meta = {}

    mathlib_raw = os.path.join(art, "mathlib.jsonl")
    if not os.path.exists(mathlib_raw):
        _log("scanning mathlib declarations")
        n = write_index(os.path.join(mathlib_dir, "Mathlib"), mathlib_raw)
        _log(f"  {n} declarations")
    meta["mathlib_decls"] = sum(1 for _ in open(mathlib_raw, encoding="utf-8"))

    pfr_dir = os.path.join(bp_dir, "pfr")
    pfr_raw = os.path.join(art, "pfr.jsonl")
    if os.path.isdir(pfr_dir) and not os.path.exists(pfr_raw):
        _log("scanning PFR declarations (evaluation set)")
        write_index(os.path.join(pfr_dir, "PFR"), pfr_raw)

    pairs_path = os.path.join(art, "blueprint_pairs.jsonl")
    decls_path = os.path.join(art, "blueprint_decls.jsonl")
    if not os.path.exists(pairs_path):
        _log("harvesting paper-prose/declaration pairs (PFR excluded)")
        roots = [os.path.join(bp_dir, d) for d in sorted(os.listdir(bp_dir))
                 if os.path.isdir(os.path.join(bp_dir, d))]
        pairs, decls = harvest(roots, exclude={"pfr"})
        with open(pairs_path, "w", encoding="utf-8") as fh:
            for p in pairs:
                fh.write(json.dumps(p, ensure_ascii=False) + "\n")
        seen = set()
        with open(decls_path, "w", encoding="utf-8") as fh:
            for d in decls:
                if d["name"] in seen:
                    continue
                seen.add(d["name"])
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
        _log(f"  {len(pairs)} pairs")
    meta["blueprint_pairs"] = sum(1 for _ in open(pairs_path, encoding="utf-8"))

    def _combine(parts, out):
        with open(out, "w", encoding="utf-8") as fh:
            for p in parts:
                if os.path.exists(p):
                    fh.write(open(p, encoding="utf-8").read())
        return out

    idx_mathlib = os.path.join(art, "idx_mathlib")
    if not os.path.exists(os.path.join(idx_mathlib, "index.pkl.gz")):
        _log("building index: mathlib only (absent-arm reference corpus)")
        meta["idx_mathlib"] = build(mathlib_raw, idx_mathlib)

    idx_full = os.path.join(art, "idx_full")
    if not os.path.exists(os.path.join(idx_full, "index.pkl.gz")):
        _log("building index: mathlib + PFR (present-arm reference corpus)")
        combined = _combine([mathlib_raw, pfr_raw], os.path.join(art, "_full.jsonl"))
        meta["idx_full"] = build(combined, idx_full)
        os.unlink(combined)

    idx_bp = os.path.join(art, "idx_blueprint")
    if not os.path.exists(os.path.join(idx_bp, "index.pkl.gz")):
        _log("building index: mathlib + blueprints (validation corpus)")
        combined = _combine([mathlib_raw, decls_path], os.path.join(art, "_bp.jsonl"))
        meta["idx_blueprint"] = build(combined, idx_bp)
        os.unlink(combined)

    return meta


def main(args) -> int:
    root = os.path.abspath(args.data_dir)
    os.makedirs(root, exist_ok=True)
    t0 = time.time()
    mathlib_dir = clone_mathlib(root)
    bp_dir = clone_blueprints(root)
    meta = build_all(root, bp_dir, mathlib_dir)
    cfg = {"data_dir": root, "artifacts": os.path.join(root, "artifacts")}
    with open(os.path.join(root, "mathgraph.json"), "w") as fh:
        json.dump(cfg, fh, indent=2)
    _log(f"done in {time.time() - t0:.0f}s")
    print(json.dumps(meta, indent=2))
    print(f"\nartifacts: {cfg['artifacts']}")
    print("try:  mathgraph query --data-dir %s \"a compact subset of a "
          "Hausdorff space is closed\"" % root)
    return 0
