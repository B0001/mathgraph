"""Align an informal mathematical statement to mathlib declarations.

The output is deliberately three-valued. A retrieval system that always
returns its best guess is useless here: a wrong lemma looks exactly like a
right one to a downstream consumer, and the whole point of a formal index is
that you can trust what it says. So the aligner returns MATCHED, AMBIGUOUS
(several candidates it cannot separate) or UNMATCHED (nothing in the index
explains the query), and the thresholds that separate those are fitted to a
target precision rather than picked by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .index import doc_words, stem

MATCHED = "matched"
AMBIGUOUS = "ambiguous"
UNMATCHED = "unmatched"

# How deep the candidate tail runs when measuring separation. Measured on the
# blueprint corpus: averaging ranks 1..9 beats rank 1 alone at every
# false-match budget from 0% to 10%, in-sample and under split-half selection.
# Ranks 1..4 recover most of it; beyond 10 the tail stops carrying signal.
MARGIN_TAIL = 10


@dataclass
class Candidate:
    name: str
    kind: str
    module: str
    score: float
    provenance: str = "source"

    def to_json(self) -> dict:
        return {
            "name": self.name, "kind": self.kind, "module": self.module,
            "score": round(self.score, 4), "provenance": self.provenance,
        }


@dataclass
class Alignment:
    query: str
    status: str
    coverage: float
    # separation of the top hit from the mean of its competitors; see
    # Aligner._separation. Serialized as "margin" by to_json(), but it is not
    # the rank-1-vs-rank-2 margin earlier versions wrote under that name, and
    # delta_margin constants do not transfer between the two.
    margin: float
    candidates: list = field(default_factory=list)

    @property
    def best(self) -> Optional[Candidate]:
        return self.candidates[0] if self.candidates else None

    def to_json(self) -> dict:
        return {
            "query": self.query,
            "status": self.status,
            "coverage": round(self.coverage, 4),
            "margin": round(self.margin, 4),
            "candidates": [c.to_json() for c in self.candidates],
        }


class Aligner:
    """Scores informal text against the mathlib name-token index."""

    def __init__(self, art: dict, max_df_frac: float = 0.03,
                 tau_cov: float = 0.2347, delta_margin: float = 0.2722,
                 expand_k: int = 8, expand_alpha: float = 0.85,
                 len_pivot: float = 0.75, mod_weight: float = 0.35,
                 prefix_weight: float = 0.7,
                 title_boost: float = 1.6):
        self.rows = art["rows"]
        self.idf = art["idf"]
        self.trans = art["trans"]
        self.N = len(self.rows)
        self.max_df = max(50, int(self.N * max_df_frac))
        self.tau_cov = tau_cov
        self.delta_margin = delta_margin
        self.expand_k = expand_k
        self.expand_alpha = expand_alpha
        self.mod_weight = mod_weight
        self.prefix_weight = prefix_weight
        self.title_boost = title_boost

        # Declaration length, measured as the IDF mass of its own name tokens,
        # pivoted BM25-style: divide by (1-p) + p*len/avg_len, so p=0 ignores
        # length entirely and p=1 divides by relative length in full.
        #
        # The L2 norm this used to divide by is wrong here. Nothing normalises
        # the query side, so raw/L2 grows as sqrt(number of tokens matched):
        # a nine-token name that matches loosely beats a four-token name that
        # matches exactly. In mathlib the short name is the general lemma and
        # the long one is a corner case of it, so that is precisely backwards
        # -- `IsCompact.isClosed` lost to
        # `TopologicalSpace.Compacts.isCompact_subsets_of_isCompact`.
        lens = np.asarray(
            [sum(self.idf.get(t, 0.0) for t in set(r["tokens"])) or 1.0
             for r in self.rows], dtype=np.float32)
        self.lennorm = ((1.0 - len_pivot)
                        + len_pivot * lens / float(lens.mean()))

        self.post = {t: np.asarray(v, dtype=np.int32)
                     for t, v in art["postings"].items()}
        self.modpost = {t: np.asarray(v, dtype=np.int32)
                        for t, v in art.get("mod_postings", {}).items()}
        # token -> stem, so a query word can hit a token that is a plural or
        # a participle of itself without going through the PMI table
        self.by_stem: dict[str, list[str]] = {}
        for t in self.idf:
            self.by_stem.setdefault(stem(t), []).append(t)
        # mathlib abbreviates aggressively: `symm` for symmetry, `bdd` for
        # bounded, `assoc` for associativity. A prefix index recovers those
        # without needing every abbreviation written down by hand.
        self.by_prefix: dict[str, list[str]] = {}
        for t in self.idf:
            if 3 <= len(t) <= 9:
                self.by_prefix.setdefault(t[:4], []).append(t)

    # -- query construction -------------------------------------------------

    def query_weights(self, text: str, title: str = "") -> dict[str, float]:
        w: dict[str, float] = {}

        def bump(tok: str, val: float, src_idf: Optional[float] = None) -> None:
            if tok not in self.idf:
                return
            if not (len(self.post.get(tok, ())) <= self.max_df
                    or tok in self.modpost):
                return
            # An expansion is a hypothesis about what mathlib calls this word;
            # it cannot be stronger evidence than the word actually written.
            # A token's contribution downstream is weight*IDF and nothing else
            # bounds the IDF of what an expansion lands on, so a rare token
            # reached by a prefix hop outweighs every word the query really
            # contains -- "compact" (IDF 5.0) reaching "companion" (IDF 11.3)
            # made `companion` the single heaviest term in a query about
            # compact sets. Capping at the source word's own IDF leaves
            # same-or-lower-IDF expansions untouched and defuses that.
            if src_idf is not None and self.idf[tok] > src_idf:
                val *= src_idf / self.idf[tok]
            if w.get(tok, 0.0) < val:
                w[tok] = val

        def absorb(text_: str, scale: float) -> None:
            for raw in doc_words(text_):
                src = self.idf.get(raw)
                bump(raw, 1.0 * scale)
                for t in self.by_stem.get(raw, ()):
                    bump(t, 0.95 * scale, src)
                if self.prefix_weight and len(raw) >= 5:
                    for t in self.by_prefix.get(raw[:4], ()):
                        if t != raw and (raw.startswith(t) or t.startswith(raw[:5])):
                            bump(t, self.prefix_weight * scale, src)
                for tok, sc in self.trans.get(raw, ())[: self.expand_k]:
                    bump(tok, self.expand_alpha * sc * scale, src)

        absorb(text, 1.0)
        if title:
            absorb(title, self.title_boost)
        return w

    def direct_tokens(self, text: str) -> set:
        """Tokens the query names outright, with no PMI hop."""
        out = set()
        for raw in doc_words(text):
            if raw in self.idf:
                out.add(raw)
            out.update(self.by_stem.get(raw, ()))
        return out

    # -- scoring ------------------------------------------------------------

    def _score(self, qw: dict[str, float], topk: int):
        if not qw:
            return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.float32), 0.0
        idx_parts, wt_parts = [], []
        mass = 0.0
        for tok, weight in qw.items():
            contrib = weight * self.idf[tok]
            arr = self.post.get(tok)
            if arr is not None and arr.size:
                mass += contrib
                idx_parts.append(arr)
                wt_parts.append(np.full(arr.size, contrib, dtype=np.float32))
            marr = self.modpost.get(tok)
            if self.mod_weight and marr is not None and 0 < marr.size <= self.max_df * 6:
                idx_parts.append(marr)
                wt_parts.append(np.full(marr.size, contrib * self.mod_weight,
                                        dtype=np.float32))
        if not idx_parts or mass <= 0:
            return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.float32), 0.0

        idxs = np.concatenate(idx_parts)
        wts = np.concatenate(wt_parts)
        order = np.argsort(idxs, kind="stable")
        sidx, swts = idxs[order], wts[order]
        uniq, start = np.unique(sidx, return_index=True)
        raw = np.add.reduceat(swts, start)

        # length-normalised score, plus the un-normalised evidence mass which
        # is what "coverage" is measured against
        norm = raw / self.lennorm[uniq]
        k = min(topk, norm.size)
        top = np.argpartition(-norm, k - 1)[:k]
        top = top[np.argsort(-norm[top])]
        return uniq[top], norm[top], mass, raw[top]

    @staticmethod
    def _separation(scores) -> float:
        """1 - (mean score of the competitors) / (score of the top hit).

        1.0 when nothing else was retrieved, 0.0 when the field is a flat tie.
        Uses up to MARGIN_TAIL-1 competitors; fewer if fewer were returned.
        """
        if scores.size < 2:
            return 1.0
        tail = scores[1:MARGIN_TAIL]
        return float((scores[0] - tail.mean()) / scores[0])

    def align(self, text: str, topk: int = 5, title: str = "") -> Alignment:
        qw = self.query_weights(text, title=title)
        res = self._score(qw, max(topk, MARGIN_TAIL))
        if len(res) == 3:
            return Alignment(text, UNMATCHED, 0.0, 0.0, [])
        ids, scores, mass, rawtop = res
        if ids.size == 0:
            return Alignment(text, UNMATCHED, 0.0, 0.0, [])

        # Separation is measured against the whole tail, not against rank 2
        # alone. Rank-1-vs-rank-2 cannot tell "one close rival" from "nine
        # close rivals", which are very different amounts of evidence, and it
        # is destroyed by a single near-duplicate: mathlib is full of primed
        # variants (`foo` / `foo'`) and to_additive twins that score
        # identically, and any one of them pinned the old statistic at ~0 and
        # forced a spurious AMBIGUOUS. Averaging the tail dilutes a lone
        # duplicate to a ninth of its former weight without needing an
        # equivalence relation over names.
        margin = self._separation(scores)
        ids, scores, rawtop = ids[:topk], scores[:topk], rawtop[:topk]

        cands = []
        for i, s in zip(ids, scores):
            r = self.rows[int(i)]
            cands.append(Candidate(r["name"], r["kind"], r["module"], float(s),
                                   r.get("provenance", "source")))
        coverage = float(rawtop[0] / mass) if mass else 0.0

        if coverage < self.tau_cov:
            status = UNMATCHED
        elif margin < self.delta_margin:
            status = AMBIGUOUS
        else:
            status = MATCHED
        return Alignment(text, status, coverage, margin, cands)
