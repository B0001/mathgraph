"""A dual encoder over the docstring/declaration parallel corpus.

No pretrained weights are used. They are not needed and would not help much:
the vocabulary that matters here (`tendsto`, `bdd`, `symm`, `rdist`) is not
what a general-purpose sentence encoder was trained on, and the parallel
corpus for exactly this mapping is already sitting in the library.

Both sides are bag-of-token linear encoders projected to a shared space:

    query side   q  in R^|Ve|   (stemmed English words)  ->  u = A^T q
    doc side     d  in R^|Vt|   (name + module tokens)   ->  v = B^T d

trained with InfoNCE over in-batch negatives. This is a low-rank factorisation
of the full English-to-token association matrix -- the same object the PMI
table approximates sparsely, but learned end-to-end and without the top-12
truncation that throws away most of the mass.
"""

from __future__ import annotations

import gzip
import math
import pickle
from collections import Counter

import numpy as np

from .index import doc_words, stem
from .names import split_name


def doc_tokens(row: dict) -> list[str]:
    """Declaration side: name tokens, plus module tokens under a namespace so
    the model can weight them separately from name tokens of the same spelling."""
    toks = list(row["tokens"])
    toks += ["mod:" + t for t in row.get("mod_tokens", ())]
    return toks


class DualEncoder:
    def __init__(self, ve: dict, vt: dict, A: np.ndarray, B: np.ndarray,
                 qidf: np.ndarray, didf: np.ndarray):
        self.ve, self.vt = ve, vt
        self.A, self.B = A, B
        self.qidf, self.didf = qidf, didf

    # -- encoding ---------------------------------------------------------

    def _bag(self, toks, vocab, idf, mat):
        idxs, wts = [], []
        for t, c in Counter(toks).items():
            j = vocab.get(t)
            if j is None:
                continue
            idxs.append(j)
            wts.append((1.0 + math.log(c)) * idf[j])
        if not idxs:
            return np.zeros(mat.shape[1], dtype=np.float32)
        w = np.asarray(wts, dtype=np.float32)
        n = np.linalg.norm(w)
        if n > 0:
            w /= n
        return (mat[idxs] * w[:, None]).sum(0)

    def encode_query(self, text: str, title: str = "", title_boost: float = 2.0):
        toks = doc_words(text) + doc_words(title) * int(round(title_boost))
        v = self._bag(toks, self.ve, self.qidf, self.A)
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def encode_doc(self, row: dict):
        v = self._bag(doc_tokens(row), self.vt, self.didf, self.B)
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def encode_corpus(self, rows, batch=4096) -> np.ndarray:
        out = np.zeros((len(rows), self.A.shape[1]), dtype=np.float32)
        for i, r in enumerate(rows):
            out[i] = self.encode_doc(r)
        return out

    # -- persistence ------------------------------------------------------

    def save(self, path):
        with gzip.open(path, "wb") as fh:
            pickle.dump({"ve": self.ve, "vt": self.vt, "A": self.A, "B": self.B,
                         "qidf": self.qidf, "didf": self.didf}, fh, protocol=4)

    @staticmethod
    def load(path):
        with gzip.open(path, "rb") as fh:
            d = pickle.load(fh)
        return DualEncoder(d["ve"], d["vt"], d["A"], d["B"], d["qidf"], d["didf"])


# ---------------------------------------------------------------------------
# training
# ---------------------------------------------------------------------------


def build_vocabs(pairs, rows, min_qf=3):
    qc, dc = Counter(), Counter()
    for text, row in pairs:
        qc.update(set(doc_words(text)))
    for r in rows:
        dc.update(set(doc_tokens(r)))
    ve = {w: i for i, (w, c) in enumerate(qc.most_common()) if c >= min_qf}
    vt = {t: i for i, t in enumerate(dc)}
    N = max(1, len(pairs))
    qidf = np.ones(len(ve), dtype=np.float32)
    for w, i in ve.items():
        qidf[i] = math.log(1.0 + N / (1 + qc[w]))
    M = max(1, len(rows))
    didf = np.ones(len(vt), dtype=np.float32)
    for t, i in vt.items():
        didf[i] = math.log(1.0 + M / (1 + dc[t]))
    return ve, vt, qidf, didf


def _sparse_bag(toks, vocab, idf):
    idxs, wts = [], []
    for t, c in Counter(toks).items():
        j = vocab.get(t)
        if j is None:
            continue
        idxs.append(j)
        wts.append((1.0 + math.log(c)) * idf[j])
    if not idxs:
        return np.zeros(0, np.int32), np.zeros(0, np.float32)
    w = np.asarray(wts, dtype=np.float32)
    n = np.linalg.norm(w)
    if n > 0:
        w /= n
    return np.asarray(idxs, dtype=np.int32), w


def prepare(pairs, ve, vt, qidf, didf):
    Q, D = [], []
    for text, row in pairs:
        qi, qw = _sparse_bag(doc_words(text), ve, qidf)
        di, dw = _sparse_bag(doc_tokens(row), vt, didf)
        if qi.size == 0 or di.size == 0:
            continue
        Q.append((qi, qw))
        D.append((di, dw))
    return Q, D


def _project(bags, mat, out):
    for r, (idx, w) in enumerate(bags):
        out[r] = (mat[idx] * w[:, None]).sum(0)
    return out


def train(pairs, rows, dim=128, epochs=6, batch=256, lr=0.05, tau=0.05,
          seed=0, log=print, resume=None):
    ve, vt, qidf, didf = (resume.ve, resume.vt, resume.qidf, resume.didf) \
        if resume else build_vocabs(pairs, rows)
    Q, D = prepare(pairs, ve, vt, qidf, didf)
    rng = np.random.default_rng(seed)
    A = resume.A if resume else (rng.standard_normal((len(ve), dim)) * 0.05).astype(np.float32)
    B = resume.B if resume else (rng.standard_normal((len(vt), dim)) * 0.05).astype(np.float32)

    mA = np.zeros_like(A); vA = np.zeros_like(A)
    mB = np.zeros_like(B); vB = np.zeros_like(B)
    step = 0
    n = len(Q)
    log(f"pairs={n} |Ve|={len(ve)} |Vt|={len(vt)} dim={dim}")

    for ep in range(epochs):
        perm = rng.permutation(n)
        tot, hits, nb = 0.0, 0, 0
        for s in range(0, n - batch + 1, batch):
            b = perm[s: s + batch]
            qb = [Q[i] for i in b]
            db = [D[i] for i in b]
            U = _project(qb, A, np.zeros((len(b), A.shape[1]), np.float32))
            V = _project(db, B, np.zeros((len(b), B.shape[1]), np.float32))
            un = np.linalg.norm(U, axis=1, keepdims=True) + 1e-8
            vn = np.linalg.norm(V, axis=1, keepdims=True) + 1e-8
            Uh, Vh = U / un, V / vn

            logits = (Uh @ Vh.T) / tau
            logits -= logits.max(1, keepdims=True)
            P = np.exp(logits); P /= P.sum(1, keepdims=True)
            hits += int((P.argmax(1) == np.arange(len(b))).sum())
            tot += float(-np.log(np.clip(np.diag(P), 1e-12, None)).mean())
            nb += 1

            G = P.copy()
            G[np.arange(len(b)), np.arange(len(b))] -= 1.0
            G /= (len(b) * tau)
            dUh = G @ Vh
            dVh = G.T @ Uh
            # backprop through the L2 normalisation
            dU = (dUh - (dUh * Uh).sum(1, keepdims=True) * Uh) / un
            dV = (dVh - (dVh * Vh).sum(1, keepdims=True) * Vh) / vn

            gA = np.zeros_like(A); gB = np.zeros_like(B)
            for r, (idx, w) in enumerate(qb):
                np.add.at(gA, idx, np.outer(w, dU[r]))
            for r, (idx, w) in enumerate(db):
                np.add.at(gB, idx, np.outer(w, dV[r]))

            step += 1
            for M, g, m, v in ((A, gA, mA, vA), (B, gB, mB, vB)):
                m *= 0.9; m += 0.1 * g
                v *= 0.999; v += 0.001 * g * g
                M -= lr * (m / (1 - 0.9 ** step)) / (np.sqrt(v / (1 - 0.999 ** step)) + 1e-8)
        log(f"epoch {ep+1}: loss {tot/max(1,nb):.4f}  in-batch top1 "
            f"{hits/max(1,nb*batch):.3f}")
    return DualEncoder(ve, vt, A, B, qidf, didf)
