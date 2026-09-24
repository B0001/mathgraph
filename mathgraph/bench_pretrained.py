"""Score pretrained dense encoders on the PFR blueprint's two arms, reported as
precision at coverage (mathgraph-br3).

Same protocol as bench_dense: the same blueprint blocks, the present arm
against idx_full, and the absent arm against idx_mathlib, where no correct
answer exists. The difference is the question asked. Instead of recall@k,
this asks: if the system answers only when its top-1 score clears a
threshold, how precise is it at a given coverage of the pooled arms? An
absent-arm answer is always wrong, because there is nothing to find.
The pre-registered protocol is in the mathgraph-br3 bead notes.

The encoder is not a dependency of mathgraph. Run it with:
    uv run --with sentence-transformers python -m mathgraph.bench_pretrained BAAI/bge-small-en-v1.5
Corpus embeddings are cached next to the index artifacts (one file per model).
"""

from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

from .bench_pfr import blueprint_blocks
from .index import load

DATA = os.environ.get("MATHGRAPH_DATA", "./mathgraph-data")
PATTERN = os.path.join(DATA, "blueprints/pfr/blueprint/src/chapter/*.tex")
# bge v1.5 model card's retrieval instruction for short queries against passages
QUERY_PREFIX = {"BAAI/": "Represent this sentence for searching relevant passages: "}
COVERAGES = (0.01, 0.05, 0.10, 0.20)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def precision_at_coverage(recs: list[dict], key: str, coverages=COVERAGES) -> list[dict]:
    """Answer the top ceil(c*N) records by `key`, which is the same as
    thresholding at that record's score. Ties at the cut are all answered or
    all left out, so coverage is never inflated by tie order."""
    n = len(recs)
    ordered = sorted(recs, key=lambda r: -r[key])
    out = []
    for c in coverages:
        m = max(1, math.ceil(c * n))
        tau = ordered[m - 1][key]
        answered = [r for r in ordered if r[key] >= tau]
        if len(answered) > m:  # a tie group straddles the cut: leave the whole group out
            answered = [r for r in ordered if r[key] > tau]
        if not answered:
            out.append({"coverage_target": c, "answered": 0, "coverage": 0.0, "correct": 0,
                        "precision": None, "wilson95": None, "tau": round(float(tau), 4)})
            continue
        k = sum(r["ok"] for r in answered)
        lo, hi = wilson(k, len(answered))
        out.append({"coverage_target": c, "answered": len(answered), "coverage": round(len(answered) / n, 4),
                    "correct": k, "precision": round(k / len(answered), 4),
                    "wilson95": [round(lo, 4), round(hi, 4)], "tau": round(float(tau), 4)})
    return out


def doc_text(r: dict) -> str:
    return ". ".join(x for x in (r["name"], r.get("doc") or "", r.get("head") or "") if x)


def main(model_name: str) -> dict:
    from sentence_transformers import SentenceTransformer

    import torch

    # Apple-silicon GPU when present; embeddings are compared by cosine, so fp32 MPS is fine
    model = SentenceTransformer(model_name, device="mps" if torch.backends.mps.is_available() else "cpu")
    full = load(os.path.join(DATA, "artifacts", "idx_full"))["rows"]
    mathlib_names = {r["name"] for r in load(os.path.join(DATA, "artifacts", "idx_mathlib"))["rows"]}
    in_mathlib = np.array([r["name"] in mathlib_names for r in full])
    cache = os.path.join(DATA, "artifacts", f"emb_{model_name.replace('/', '__')}.npy")
    if os.path.exists(cache):
        M = np.load(cache)
    else:
        M = model.encode([doc_text(r) for r in full], batch_size=128, normalize_embeddings=True,
                         show_progress_bar=True, convert_to_numpy=True).astype(np.float32)
        np.save(cache, M)
    assert M.shape[0] == len(full)
    names = [r["name"] for r in full]
    full_names = set(names)
    prefix = next((p for k, p in QUERY_PREFIX.items() if model_name.startswith(k)), "")

    blocks = blueprint_blocks(PATTERN)
    Q = model.encode([prefix + ". ".join(x for x in (b.title, b.text) if x) for b in blocks],
                     normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)
    recs = []
    for b, q in zip(blocks, Q):
        s = M @ q
        for arm, mask in (("present", None), ("absent", in_mathlib)):
            gold = [g for g in b.declared_lean if g in (full_names if arm == "present" else mathlib_names)]
            if (arm == "present" and not gold) or (arm == "absent" and gold):
                continue  # same arm filters as bench_dense.run_arm
            sc = np.where(mask, s, -np.inf) if mask is not None else s
            top2 = np.argpartition(-sc, 1)[:2]
            top2 = top2[np.argsort(-sc[top2])]
            recs.append({"arm": arm, "title": b.title, "text": b.text[:300], "top1": names[top2[0]],
                         "score": float(sc[top2[0]]), "margin": float(sc[top2[0]] - sc[top2[1]]),
                         "ok": int(arm == "present" and names[top2[0]] in gold)})
    pres = [r for r in recs if r["arm"] == "present"]
    return {
        "model": model_name, "n_present": len(pres), "n_absent": len(recs) - len(pres),
        "recall@1": round(sum(r["ok"] for r in pres) / max(1, len(pres)), 4),
        "by_score": precision_at_coverage(recs, "score"),
        "by_margin": precision_at_coverage(recs, "margin"),
        "records": recs,
    }


if __name__ == "__main__":
    res = main(sys.argv[1])
    out = os.path.join(DATA, "artifacts", f"br3_{sys.argv[1].replace('/', '__')}.json")
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "records"}, indent=1))
    print("records ->", out)
