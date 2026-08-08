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
import statistics
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
    """Present-arm recall via `Aligner.align` directly.

    This is a *different measurement* from the "PFR present arm" table in
    README.md, which comes from `cli.cmd_bench` (`uv run mathgraph bench`)
    scoring the same corpus through `StructReranker(lam=0.0, depth=10000)`
    instead. Both nominally compute lexical recall@1/@5 over the same blocks
    and index, but `align()` internally scores at `depth=max(topk,
    MARGIN_TAIL)=10` (align.py) rather than depth=10000, and the two runs of
    `np.argpartition`/`argsort` over different-sized slices are not
    guaranteed to break exact score ties the same way. Measured on the
    current idx_full corpus (176 present-arm statements): this function gets
    recall@1=0.188, `mathgraph bench` gets 0.182 -- recall@5 is identical
    (0.318) at both, consistent with the disagreement being a single
    near-tied statement flipping rank 1, not a real difference in ranking
    quality. Treat README's published present-arm recall@1/@5 as the
    canonical numbers; this function's own recall@1 is a byproduct of reusing
    `align()` for the combined-arm calibration sweep below, not a second
    measurement of the same thing. See mathgraph-7dw.
    """
    known = {r["name"] for r in al.rows}
    hits1 = hits5 = n = 0
    ans = 0
    wrong = []
    records = []                    # (coverage, margin, rank1_correct) per statement,
    for b in blocks:                # threshold-independent -- collected so a combined-arm
        gold = [g for g in b.declared_lean if g in known]     # sweep doesn't need a second pass
        if not gold:
            continue
        n += 1
        a = al.align(b.text, title=b.title, topk=5)
        names = [c.name for c in a.candidates]
        correct = bool(names and names[0] in gold)
        records.append((a.coverage, a.margin, correct))
        if a.status != UNMATCHED:
            ans += 1
        if correct:
            hits1 += 1
        elif len(wrong) < 6:
            wrong.append((b.id, gold[0], names[:2]))
        if set(names) & set(gold):
            hits5 += 1
    return {"n": n, "recall@1": round(hits1 / n, 3), "recall@5": round(hits5 / n, 3),
            "answered": round(ans / n, 3), "misses": wrong, "records": records}


def lexical_pool_stats(al: Aligner, blocks, depth: int = 10000) -> dict:
    """How often gold survives into the pool structural reranking sees, and
    how deep in it gold sits, at `cmd_bench`/`mathgraph bench`'s shipped
    depth (`StructReranker(depth=10000)`). This is the "lexical stage reaches
    the gold declaration N% of the time and puts it at median rank M" claim
    in README's "Why" section and `structmatch.py`'s module docstring --
    distinct from `arm_present`'s recall@1/@5, which score the *final*
    ranked list after truncation to topk=5, not the pre-rerank pool.
    """
    known = {r["name"] for r in al.rows}
    n = reached = 0
    ranks = []
    for b in blocks:
        gold = set(g for g in b.declared_lean if g in known)
        if not gold:
            continue
        n += 1
        qw = al.query_weights(b.text, title=b.title)
        res = al._score(qw, depth)
        if len(res) == 3:
            continue
        ids = res[0]
        for rank, i in enumerate(ids, start=1):
            if al.rows[int(i)]["name"] in gold:
                ranks.append(rank)
                reached += 1
                break
    return {"n": n, "depth": depth, "reached": reached,
            "reach_rate": round(reached / n, 3) if n else 0.0,
            "median_rank": statistics.median(ranks) if ranks else None}


def arm_absent(al: Aligner, blocks) -> dict:
    known = {r["name"] for r in al.rows}
    n = fp = 0
    status = {MATCHED: 0, AMBIGUOUS: 0, UNMATCHED: 0}
    examples = []
    records = []                    # (coverage, margin) per statement -- every answer here
    for b in blocks:                # is wrong by construction, so no correctness flag needed
        if any(g in known for g in b.declared_lean):
            continue                       # genuinely present; not a negative
        n += 1
        a = al.align(b.text, title=b.title, topk=3)
        records.append((a.coverage, a.margin))
        status[a.status] += 1
        if a.status == MATCHED:
            fp += 1
            if len(examples) < 6:
                examples.append((b.id, a.candidates[0].name, round(a.coverage, 3)))
    return {"n": n, "correct_abstention": round((n - fp) / n, 3),
            "false_match_rate": round(fp / n, 3), "status": status,
            "false_matches": examples, "records": records}


def combined_precision_sweep(present: dict, absent: dict) -> dict:
    """Best achievable precision over both PFR arms treated as one pool.

    Exhaustive grid search over every observed (coverage, margin) pair as a
    candidate (tau_cov, delta_margin) threshold. An "answer" is any present-arm
    or absent-arm statement clearing both thresholds; it is correct only if
    it's a present-arm statement whose rank-1 candidate is gold -- every
    absent-arm answer is wrong by construction, and a present-arm answer whose
    rank-1 is not gold is also wrong. Reports the threshold maximising
    precision, breaking ties toward more answers (a precision figure on a
    single lucky answer is not more informative than the same precision on
    several).

    No target precision and no minimum-answer floor: this is "best
    achievable", not "best that also clears some usability bar" -- the point
    of the number is to show how good the peak gets before coverage is
    considered at all.
    """
    recs = ([("pos", cov, mar, correct) for cov, mar, correct in present["records"]] +
            [("neg", cov, mar, False) for cov, mar in absent["records"]])
    covs = sorted({round(r[1], 4) for r in recs})
    dels = sorted({round(r[2], 4) for r in recs})
    best = None
    for tau in covs:
        for dl in dels:
            tp = ans = 0
            for kind, cov, mar, correct in recs:
                if cov >= tau and mar >= dl:
                    ans += 1
                    if kind == "pos" and correct:
                        tp += 1
            if ans == 0:
                continue
            key = (tp / ans, ans)
            if best is None or key > (best["precision"], best["answered"]):
                best = {"precision": round(tp / ans, 4), "answered": ans,
                        "correct": tp, "tau_cov": tau, "delta_margin": dl}
    n_combined = present["n"] + absent["n"]
    return {**best, "n_present": present["n"], "n_absent": absent["n"],
            "n_combined": n_combined}


def main(deploy="idx_deploy", mathlib_only="idx_mathlib_only",
         pattern="/home/claude/pfr/blueprint/src/chapter/*.tex", **kw):
    blocks = blueprint_blocks(pattern)
    out = {"blocks_with_gold": len(blocks)}
    al = Aligner(load(deploy), **kw)
    out["present"] = arm_present(al, blocks)
    out["lexical_pool"] = lexical_pool_stats(al, blocks)
    al2 = Aligner(load(mathlib_only), **kw)
    out["absent"] = arm_absent(al2, blocks)
    out["combined_calibration"] = combined_precision_sweep(out["present"], out["absent"])
    del out["present"]["records"], out["absent"]["records"]
    return out


if __name__ == "__main__":
    kw = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(main(**kw), indent=2))
