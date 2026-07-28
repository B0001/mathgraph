"""Domain-adapt the dual encoder onto paper prose.

Pretrain on the ~69k library docstrings, then continue training on a mixture
of those and the ~1k harvested blueprint pairs, upsampled. Straight
fine-tuning on 1k pairs collapses the space; the mixture keeps the library
vocabulary intact while dragging the query side toward how papers actually
read.

PFR is excluded everywhere -- both its blueprint pairs and the docstrings on
its own Lean declarations. It is the test set.
"""

from __future__ import annotations

import json
import random
import sys

import numpy as np

from .index import load
from .names import split_name
from .dense import train, DualEncoder


def blueprint_rows(path: str) -> dict:
    rows = {}
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        d["tokens"] = split_name(d["name"])
        d["mod_tokens"] = [t for t in split_name(d["module"])
                           if t not in ("basic", "defs", "lemmas")]
        rows[d["name"]] = d
    return rows


def augment(text: str, rng: random.Random, keep=0.5, cap=16) -> str:
    """Make a docstring look like a paper statement.

    The measured gap is structural, not topical: a paper statement is ~13
    English words wrapped around formula blocks, so most of the relation is
    stated in symbols and never reaches the encoder. Dropping words at random
    reproduces that condition over the 69k docstrings already available, which
    is 65x more data than the harvested blueprint corpus.
    """
    ws = text.split()
    if len(ws) <= 4:
        return text
    kept = [w for w in ws if rng.random() < keep]
    if len(kept) < 3:
        kept = rng.sample(ws, min(3, len(ws)))
    return " ".join(kept[:cap])


def build(idx_dir="idx_deploy", pairs_path="blueprint_pairs.jsonl",
          decls_path="blueprint_decls.jsonl", holdout_prefix="PFR.",
          upsample=25, dim=192, pre_epochs=10, ft_epochs=6, seed=0,
          n_augment=2):
    art = load(idx_dir)
    rows = art["rows"]

    bp_rows = blueprint_rows(decls_path)
    vocab_rows = rows + list(bp_rows.values())

    doc_pairs = [(r["doc"], r) for r in rows
                 if r.get("doc") and not r["module"].startswith(holdout_prefix)]

    bp_pairs = []
    for line in open(pairs_path, encoding="utf-8"):
        d = json.loads(line)
        for t in d["targets"]:
            row = bp_rows.get(t)
            if row is not None:
                bp_pairs.append((d["text"], row))
                break

    rng = random.Random(seed)
    rng.shuffle(doc_pairs)
    rng.shuffle(bp_pairs)
    print(f"docstring pairs {len(doc_pairs)}  blueprint pairs {len(bp_pairs)}",
          file=sys.stderr)

    enc = train(doc_pairs, vocab_rows, dim=dim, epochs=pre_epochs,
                batch=384, lr=0.06, tau=0.05, seed=seed,
                log=lambda m: print("  pre:", m, file=sys.stderr))

    aug = []
    for _ in range(n_augment):
        for text, row in doc_pairs:
            aug.append((augment(text, rng), row))
    mix = bp_pairs * upsample + aug + rng.sample(
        doc_pairs, min(len(doc_pairs), len(bp_pairs) * upsample))
    rng.shuffle(mix)
    print(f"adaptation mixture {len(mix)}", file=sys.stderr)
    enc = train(mix, vocab_rows, dim=dim, epochs=ft_epochs, batch=256,
                lr=0.012, tau=0.05, seed=seed + 1, resume=enc,
                log=lambda m: print("  ft :", m, file=sys.stderr))
    return enc


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dense_adapted.pkl.gz"
    enc = build()
    enc.save(out)
    print("saved", out)
