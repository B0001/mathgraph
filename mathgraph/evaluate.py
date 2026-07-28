"""Calibration harness.

Positives are declarations that are in the index but whose docstrings never
trained the translation table. Negatives are declarations removed from the
index entirely -- their docstrings describe something the index genuinely does
not contain, so the only correct answer is to abstain.

Without the negative arm you cannot calibrate abstention at all: any threshold
looks fine if every query has an answer.
"""
from __future__ import annotations

import json, os, random, sys
import numpy as np
from .index import load
from .align import Aligner, MATCHED, AMBIGUOUS, UNMATCHED


def read(path, n, seed=0):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    random.Random(seed).shuffle(rows)
    return rows[:n]


def run(idx_dir="idx_eval", n=1500, **kw):
    art = load(idx_dir)
    al = Aligner(art, **kw)
    pos = read(os.path.join(idx_dir, "devpos.jsonl"), n)
    neg = read(os.path.join(idx_dir, "holdout.jsonl"), n)

    recs = []
    for r in pos:
        a = al.align(r["doc"], topk=5)
        names = [c.name for c in a.candidates]
        rank = names.index(r["name"]) + 1 if r["name"] in names else 0
        recs.append(("pos", a.coverage, a.margin, rank))
    for r in neg:
        a = al.align(r["doc"], topk=5)
        recs.append(("neg", a.coverage, a.margin, 0))
    return recs


def rank_report(recs):
    p = [r for r in recs if r[0] == "pos"]
    r1 = sum(1 for x in p if x[3] == 1) / len(p)
    r5 = sum(1 for x in p if x[3] > 0) / len(p)
    mrr = sum(1 / x[3] if x[3] else 0 for x in p) / len(p)
    return {"n": len(p), "recall@1": round(r1, 4), "recall@5": round(r5, 4),
            "mrr": round(mrr, 4)}


def sweep(recs, target_precision=0.90):
    """Find (tau_cov, delta) maximising answered-rate subject to precision."""
    covs = np.unique([round(x[1], 3) for x in recs])
    best = None
    grid_tau = np.quantile(covs, np.linspace(0.02, 0.98, 40))
    # ranges over the tail-mean separation statistic, which runs materially
    # higher than the rank-1-vs-2 margin it replaced (observed max ~0.62 on
    # the blueprint corpus); a grid topping out at 0.3 silently returns a
    # degenerate optimum
    grid_del = [0.0, 0.04, 0.08, 0.12, 0.18, 0.24, 0.3, 0.38, 0.46, 0.55, 0.7]
    for tau in grid_tau:
        for dl in grid_del:
            tp = fp = abst_pos = 0
            neg_ok = neg_bad = 0
            for kind, cov, mar, rank in recs:
                answered = cov >= tau and mar >= dl
                if kind == "pos":
                    if not answered:
                        abst_pos += 1
                    elif rank == 1:
                        tp += 1
                    else:
                        fp += 1
                else:
                    if answered:
                        neg_bad += 1
                    else:
                        neg_ok += 1
            ans = tp + fp
            if ans == 0:
                continue
            prec = tp / (ans + neg_bad)
            if prec < target_precision:
                continue
            yieldrate = ans / (tp + fp + abst_pos)
            if best is None or yieldrate > best["answer_rate"]:
                best = {"tau_cov": round(float(tau), 4), "delta_margin": dl,
                        "precision": round(prec, 4),
                        "answer_rate": round(yieldrate, 4),
                        "false_match_rate_on_absent": round(neg_bad / (neg_ok + neg_bad), 4)}
    return best


if __name__ == "__main__":
    kw = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    recs = run(**kw)
    print(json.dumps({"ranking": rank_report(recs),
                      "calibrated": sweep(recs)}, indent=2))
