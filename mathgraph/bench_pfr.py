"""Benchmark on a real paper rather than on library docstrings.

Terence Tao's Polynomial Freiman-Ruzsa blueprint is ordinary research prose
carrying `\\lean{...}` annotations written by the authors. That gives a gold
alignment over 200-odd statements of genuine paper text, which is the task
this tool actually performs -- docstring retrieval only approximates it.

Two arms:
  present  -- the paper's own formalisation is in the index; can the aligner
              find the right declaration from the informal statement?
  absent   -- only mathlib is indexed, so 95% of the paper's statements have
              no correct answer at all; does the aligner say so?
"""

from __future__ import annotations

import glob
import json
import sys

from .index import load
from .align import Aligner, MATCHED, AMBIGUOUS, UNMATCHED
from .latex import parse


def blueprint_blocks(pattern: str) -> list:
    out = []
    for f in sorted(glob.glob(pattern)):
        out.extend(parse(open(f, encoding="utf-8").read()))
    return [b for b in out if b.declared_lean and b.kind != "proof"
            and len(b.text.split()) >= 5]


def arm_present(al: Aligner, blocks) -> dict:
    known = {r["name"] for r in al.rows}
    hits1 = hits5 = n = 0
    ans = 0
    wrong = []
    for b in blocks:
        gold = [g for g in b.declared_lean if g in known]
        if not gold:
            continue
        n += 1
        a = al.align(b.text, title=b.title, topk=5)
        names = [c.name for c in a.candidates]
        if a.status != UNMATCHED:
            ans += 1
        if names and names[0] in gold:
            hits1 += 1
        elif len(wrong) < 6:
            wrong.append((b.id, gold[0], names[:2]))
        if set(names) & set(gold):
            hits5 += 1
    return {"n": n, "recall@1": round(hits1 / n, 3), "recall@5": round(hits5 / n, 3),
            "answered": round(ans / n, 3), "misses": wrong}


def arm_absent(al: Aligner, blocks) -> dict:
    known = {r["name"] for r in al.rows}
    n = fp = 0
    status = {MATCHED: 0, AMBIGUOUS: 0, UNMATCHED: 0}
    examples = []
    for b in blocks:
        if any(g in known for g in b.declared_lean):
            continue                       # genuinely present; not a negative
        n += 1
        a = al.align(b.text, title=b.title, topk=3)
        status[a.status] += 1
        if a.status == MATCHED:
            fp += 1
            if len(examples) < 6:
                examples.append((b.id, a.candidates[0].name, round(a.coverage, 3)))
    return {"n": n, "correct_abstention": round((n - fp) / n, 3),
            "false_match_rate": round(fp / n, 3), "status": status,
            "false_matches": examples}


def main(deploy="idx_deploy", mathlib_only="idx_mathlib_only",
         pattern="/home/claude/pfr/blueprint/src/chapter/*.tex", **kw):
    blocks = blueprint_blocks(pattern)
    out = {"blocks_with_gold": len(blocks)}
    al = Aligner(load(deploy), **kw)
    out["present"] = arm_present(al, blocks)
    al2 = Aligner(load(mathlib_only), **kw)
    out["absent"] = arm_absent(al2, blocks)
    return out


if __name__ == "__main__":
    kw = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(main(**kw), indent=2))
