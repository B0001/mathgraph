"""Freeze the benchmark so it can be used without cloning anything.

Emits:
  tasks.jsonl   one row per statement: text, title, arm, gold names
  scorer.py     standalone scorer (stdlib only) for a predictions file

A predictions file is jsonl: {"id": ..., "prediction": "Decl.name" | null}.
null means abstain. The scorer reports the three numbers that matter and
refuses to let an implementation hide behind any one of them:

  precision      of the answers given, how many are right
  recall         of the answerable statements, how many were answered right
  false-match    on the absent arm, how often something was asserted anyway
"""

from __future__ import annotations

import json
import os
import string
import sys

from .bench_pfr import blueprint_blocks
from .index import load

SCORER = '''#!/usr/bin/env python3
"""Score a predictions file against tasks.jsonl. Stdlib only.

usage: python scorer.py tasks.jsonl predictions.jsonl
predictions rows: {"id": <task id>, "prediction": <declaration name or null>}
"""
import json, sys

def main(tasks_path, preds_path):
    tasks = {t["id"]: t for t in map(json.loads, open(tasks_path, encoding="utf-8"))}
    preds = {}
    for row in map(json.loads, open(preds_path, encoding="utf-8")):
        preds[row["id"]] = row.get("prediction")

    tp = fp = abstain_pos = 0          # present arm
    neg_ok = neg_bad = 0               # absent arm
    missing = 0
    for tid, t in tasks.items():
        p = preds.get(tid, None)
        if tid not in preds:
            missing += 1
        if t["arm"] == "present":
            if p is None:
                abstain_pos += 1
            elif p in t["gold"]:
                tp += 1
            else:
                fp += 1
        else:
            if p is None:
                neg_ok += 1
            else:
                neg_bad += 1

    answered = tp + fp + neg_bad
    out = {
        "n_present": tp + fp + abstain_pos,
        "n_absent": neg_ok + neg_bad,
        "precision": round(tp / answered, 4) if answered else None,
        "recall": round(tp / max(1, tp + fp + abstain_pos), 4),
        "answer_rate_present": round((tp + fp) / max(1, tp + fp + abstain_pos), 4),
        "false_match_rate_absent": round(neg_bad / max(1, neg_ok + neg_bad), 4),
        "missing_predictions": missing,
    }
    print(json.dumps(out, indent=2))
    return out

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
'''

CARD = '''# paper2lean-bench

Aligning informal mathematical statements to formal library declarations,
with abstention scored as a first-class outcome.

## What it is

$N_PRES + $N_ABS statements from the blueprint of the Polynomial Freiman-Ruzsa
formalization (Tao et al.), ordinary research prose, each carrying the
authors' own `\\lean{...}` annotation as gold. These counts are computed from
the corpus that generated this release's tasks.jsonl, not hardcoded -- if you
edit this template and the numbers stop matching tasks.jsonl, that is a bug.

- **present arm** ($N_PRES): the gold declaration exists in the reference corpus
  (mathlib4 + the PFR formalization). The right move is to name it.
- **absent arm** ($N_ABS): the gold declaration exists only in the PFR project,
  which is *excluded* from the reference corpus for this arm. Nothing in the
  corpus is correct, so the only right move is to abstain (`null`).

Systems that always answer score a 100% false-match rate on the absent arm.
That is the failure mode this benchmark exists to expose: in real use, most
statements of a new paper are not in any library, and a wrong alignment is
indistinguishable from a right one downstream.

## Format

`tasks.jsonl`, one task per line:

```json
{"id": "...", "arm": "present", "title": "...", "text": "...",
 "section": "...", "gold": ["Decl.name", ...]}
```

Each statement names its reference `corpus` — the absent arm must be run
against mathlib alone, with the PFR formalization withheld, or its abstention
labels are meaningless. Each statement names its reference `corpus` — the absent arm must be run
against mathlib alone (PFR formalization withheld) or its abstention labels
are meaningless. Math is flattened to `MATH` in `text` (this benchmark is deliberately hard;
formula-aware systems should recover the math from the arXiv source).

Predict with anything. Emit `{"id": ..., "prediction": name-or-null}` per
task. Score with `python scorer.py tasks.jsonl predictions.jsonl`.

## Baselines (this repository)

| system | precision | recall | false-match (absent) |
|---|---|---|---|
| lexical + calibrated abstention | see note † | see note † | see note † |
| dense dual-encoder (docstring-trained) | ~0.06 | 0.006 | high |
| always-answer lexical top-1 | 0.04 | 0.074 | 1.00 |

† Not computed by this script, so not hardcoded here. A figure for this row
("~67%, on 3 answers out of 349") shipped in this exact spot for at least two
scorer revisions after it stopped matching the code that was supposed to
produce it. Reproduce it yourself against the corpus that generated this
release with `python -m mathgraph.bench_pfr` (see the parent repository's
README, "Calibration sweep over both arms combined", for the exact
invocation) and read `combined_calibration` off the output. The bar to
clear is: precision you would trust, at recall above a few percent, with
false-match near zero.

## Provenance and license

Statements are derived from the PFR blueprint (Apache 2.0,
github.com/teorth/pfr). Gold labels are the authors' own annotations.
Reference corpus: mathlib4 (Apache 2.0). This benchmark inherits Apache 2.0.
'''


def main(out_dir="bench_release", pattern=None):
    os.makedirs(out_dir, exist_ok=True)
    if pattern is None:
        pattern = os.path.join(
            os.environ.get("MATHGRAPH_DATA", "./mathgraph-data"),
            "blueprints/pfr/blueprint/src/chapter/*.tex",
        )
    blocks = blueprint_blocks(pattern)
    deploy = {r["name"] for r in load("idx_deploy")["rows"]}
    mathlib = {r["name"] for r in load("idx_mathlib_only")["rows"]}

    # The two arms use different reference corpora, so one statement can
    # appear in both: answerable against mathlib+PFR, unanswerable against
    # mathlib alone. Each task row names its corpus explicitly.
    n_pres = n_abs = 0
    with open(os.path.join(out_dir, "tasks.jsonl"), "w", encoding="utf-8") as fh:
        for b in blocks:
            gold_deploy = [g for g in b.declared_lean if g in deploy]
            gold_mathlib = [g for g in b.declared_lean if g in mathlib]
            base = {"title": b.title, "text": b.text, "section": b.section}
            if gold_deploy:
                n_pres += 1
                fh.write(json.dumps({
                    "id": f"pfr::present::{b.id}", "arm": "present",
                    "corpus": "mathlib4+pfr", "gold": gold_deploy, **base,
                }, ensure_ascii=False) + "\n")
            if b.declared_lean and not gold_mathlib:
                n_abs += 1
                fh.write(json.dumps({
                    "id": f"pfr::absent::{b.id}", "arm": "absent",
                    "corpus": "mathlib4", "gold": [], **base,
                }, ensure_ascii=False) + "\n")

    card = string.Template(CARD).substitute(N_PRES=n_pres, N_ABS=n_abs)
    open(os.path.join(out_dir, "scorer.py"), "w").write(SCORER)
    open(os.path.join(out_dir, "README.md"), "w").write(card)
    print(json.dumps({"present": n_pres, "absent": n_abs, "dir": out_dir}))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "bench_release")
