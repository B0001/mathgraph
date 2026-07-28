"""Score the dense retriever on the same two arms as the lexical one.

Nothing about the protocol changes: same paper, same gold annotations, same
present/absent split. That is the point of having built the harness first --
a new retrieval stage is a drop-in, and its numbers are directly comparable
to the ones already in the README.
"""

from __future__ import annotations

import json
import sys

import numpy as np

from .index import load
from .align import Aligner
from .dense import DualEncoder
from .bench_pfr import blueprint_blocks

LEX = dict(len_pivot=0.75, mod_weight=0.1,
           prefix_weight=0.85, title_boost=2.5)


def encode_corpus(enc: DualEncoder, rows) -> np.ndarray:
    M = np.zeros((len(rows), enc.A.shape[1]), dtype=np.float32)
    for i, r in enumerate(rows):
        M[i] = enc.encode_doc(r)
    return M


def dense_topk(enc, M, text, title, k=200, title_boost=2.0):
    q = enc.encode_query(text, title, title_boost)
    if not np.any(q):
        return np.zeros(0, np.int64), np.zeros(0, np.float32)
    s = M @ q
    k = min(k, s.size)
    idx = np.argpartition(-s, k - 1)[:k]
    idx = idx[np.argsort(-s[idx])]
    return idx, s[idx]


def rrf(rank_lists, k=60.0):
    """Reciprocal rank fusion -- scale-free, so it does not need the two
    scorers to be on comparable scales, which they are not."""
    acc = {}
    for lst in rank_lists:
        for r, i in enumerate(lst):
            acc[i] = acc.get(i, 0.0) + 1.0 / (k + r + 1)
    order = sorted(acc.items(), key=lambda x: -x[1])
    return [i for i, _ in order], [v for _, v in order]


def run_arm(rows, enc, M, blocks, gold_filter, mode, al=None, topk=5):
    known = {r["name"] for r in rows}
    n = hits1 = hits5 = 0
    recs = []
    for b in blocks:
        gold = [g for g in b.declared_lean if g in known]
        if gold_filter == "present" and not gold:
            continue
        if gold_filter == "absent" and gold:
            continue
        n += 1
        didx, dsc = dense_topk(enc, M, b.text, b.title)
        if mode == "dense":
            ids = didx[:topk]
            top_score = float(dsc[0]) if dsc.size else 0.0
            # same separation statistic the lexical aligner uses, or the two
            # arms are not being compared on the same footing
            margin = Aligner._separation(dsc)
        else:
            a = al.align(b.text, title=b.title, topk=200)
            lidx = [r["_id"] for r in []] or []
            lex_names = [c.name for c in a.candidates]
            name2id = run_arm._name2id
            lidx = [name2id[nm] for nm in lex_names if nm in name2id]
            fused, fs = rrf([list(didx), lidx])
            ids = np.asarray(fused[:topk], dtype=np.int64)
            top_score = float(dsc[0]) if dsc.size else 0.0
            margin = Aligner._separation(np.asarray(fs, dtype=np.float64))
        names = [rows[int(i)]["name"] for i in ids]
        if gold_filter == "present":
            if names and names[0] in gold:
                hits1 += 1
            if set(names) & set(gold):
                hits5 += 1
        recs.append((gold_filter, top_score, margin,
                     1 if (names and names[0] in gold) else 0))
    out = {"n": n}
    if gold_filter == "present":
        out.update({"recall@1": round(hits1 / n, 3), "recall@5": round(hits5 / n, 3)})
    return out, recs


def sweep(recs, min_answers=5):
    scores = np.array([r[1] for r in recs])
    best = []
    for tau in np.quantile(scores, np.linspace(0.3, 0.999, 40)):
        for dl in (0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.55, 0.7):
            tp = fp = npos = 0
            for kind, sc, mar, ok in recs:
                ans = sc >= tau and mar >= dl
                if kind == "present":
                    npos += 1
                    if ans and ok:
                        tp += 1
                    elif ans:
                        fp += 1
                elif ans:
                    fp += 1
            if tp + fp >= min_answers:
                best.append({"precision": round(tp / (tp + fp), 3),
                             "answered": tp + fp,
                             "recall": round(tp / max(1, npos), 3),
                             "tau": round(float(tau), 3), "delta": dl})
    best.sort(key=lambda d: (-d["precision"], -d["answered"]))
    return best[:5]


def main(mode="dense", encoder="dense_mathlib.pkl.gz"):
    blocks = blueprint_blocks("/home/claude/pfr/blueprint/src/chapter/*.tex")
    enc = DualEncoder.load(encoder)

    art_d = load("idx_deploy")
    Md = encode_corpus(enc, art_d["rows"])
    run_arm._name2id = {r["name"]: i for i, r in enumerate(art_d["rows"])}
    al_d = Aligner(art_d, tau_cov=0.0, delta_margin=0.0, **LEX) if mode != "dense" else None
    pres, rp = run_arm(art_d["rows"], enc, Md, blocks, "present", mode, al_d)

    art_m = load("idx_mathlib_only")
    Mm = encode_corpus(enc, art_m["rows"])
    run_arm._name2id = {r["name"]: i for i, r in enumerate(art_m["rows"])}
    al_m = Aligner(art_m, tau_cov=0.0, delta_margin=0.0, **LEX) if mode != "dense" else None
    abst, ra = run_arm(art_m["rows"], enc, Mm, blocks, "absent", mode, al_m)

    return {"mode": mode, "encoder": encoder, "present": pres, "absent": abst,
            "calibration_top": sweep(rp + ra)}


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "dense"
    e = sys.argv[2] if len(sys.argv) > 2 else "dense_mathlib.pkl.gz"
    print(json.dumps(main(m, e), indent=2))
