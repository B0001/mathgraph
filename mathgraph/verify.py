"""Verify a proposed alignment instead of producing one.

The division of labour this implements: a strong language model proposes a
declaration name for an informal statement; this layer decides whether to
trust it. Generation is what LLMs are good at, and knowing when they are
wrong is what they are bad at -- a hallucinated alignment is fluent,
well-typed-looking, and confident. The checks here are the opposite shape:
mechanical, exact where possible, and calibrated where not.

Three verdicts, in order of certainty:

  NONEXISTENT   the name is not in the index, including the to_additive
                shadow. Exact. This alone catches every fabricated name.
  REJECTED      the name exists but the statement's own words do not support
                it, or support a different declaration much better.
  VERIFIED      exists, and the evidence clears a threshold calibrated on
                held-out blueprint projects (never on PFR).

The asymmetry is deliberate: existence is proof-grade, textual support is
probabilistic, and the output says which kind of claim it is making.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from .align import Aligner
from .index import doc_words, stem

NONEXISTENT = "nonexistent"
REJECTED = "rejected"
VERIFIED = "verified"


@dataclass
class Verdict:
    proposal: str
    status: str
    evidence: float          # support the statement's words give the proposal
    rel_evidence: float      # proposal support / best support in the index
    exists: bool
    provenance: str = ""
    better: list = field(default_factory=list)   # stronger alternatives, if any
    reasons: list = field(default_factory=list)

    def to_json(self) -> dict:
        d = dict(self.__dict__)
        d["evidence"] = round(self.evidence, 4)
        d["rel_evidence"] = round(self.rel_evidence, 4)
        return d


class Verifier:
    def __init__(self, aligner: Aligner, tau_abs: float = 0.05,
                 tau_rel: float = 0.35, tau_pat: float = 0.25,
                 use_patterns: bool = True):
        self.al = aligner
        self.name2id = {r["name"]: i for i, r in enumerate(aligner.rows)}
        self.tau_abs = tau_abs
        self.tau_rel = tau_rel
        self.tau_pat = tau_pat
        self._patterns = None
        if use_patterns:
            import math as _m
            from collections import Counter as _C
            from .argmatch import lean_patterns
            cache, df = {}, _C()
            for i, r in enumerate(aligner.rows):
                pt = lean_patterns(r.get("head", ""))
                cache[i] = pt
                df.update(set(pt))
            N = len(aligner.rows)
            idf = {f: _m.log(1 + N / (1 + c)) for f, c in df.items()}
            mx = max(idf.values()) if idf else 1.0
            self._patterns = (cache,
                              lambda f: idf.get(f, _m.log(1 + N)) / mx)

    # -- evidence ---------------------------------------------------------

    def support(self, qw: dict[str, float], row: dict) -> float:
        """How much of the statement's (expanded) token mass lands on this
        declaration, normalised by the total query mass so it is comparable
        across statements of different lengths."""
        mass = sum(w * self.al.idf[t] for t, w in qw.items()) or 1.0
        toks = set(row["tokens"])
        hit = sum(w * self.al.idf[t] for t, w in qw.items() if t in toks)
        hit += 0.3 * sum(w * self.al.idf[t] for t, w in qw.items()
                         if t in set(row.get("mod_tokens", ())) - toks)
        return hit / mass

    def verify(self, text: str, proposal: str, title: str = "",
               math_segments: list | None = None) -> Verdict:
        proposal = proposal.strip()
        rid = self.name2id.get(proposal)
        if rid is None:
            return Verdict(proposal, NONEXISTENT, 0.0, 0.0, False,
                           reasons=["name not found in index (source or "
                                    "to_additive-generated)"])

        row = self.al.rows[rid]
        qw = self.al.query_weights(text, title=title)
        ev = self.support(qw, row)

        # Formula-pattern path: alpha-canonical argument patterns are sparse
        # but nearly conclusive when they fire (measured on PFR: they fire on
        # 8.6% of correct proposals vs 0.6% of sibling lemmas and 0% of
        # wrong-namespace or random ones). A firing pattern verifies on its
        # own, independent of lexical evidence.
        if self._patterns is not None and math_segments:
            from .argmatch import latex_patterns, pattern_score
            cache, pidf = self._patterns
            psc = pattern_score(latex_patterns(math_segments), cache[rid], pidf)
            if psc >= self.tau_pat:
                return Verdict(proposal, VERIFIED, ev, 1.0, True,
                               provenance=row.get("provenance", "source"),
                               reasons=[f"formula pattern match "
                                        f"({psc:.2f} >= {self.tau_pat})"])

        # best achievable support in the whole index, for scale
        res = self.al._score(qw, 8)
        best_ev, better = 0.0, []
        if len(res) != 3:
            ids, _s, _m, _raw = res
            for i in ids:
                r2 = self.al.rows[int(i)]
                e2 = self.support(qw, r2)
                if e2 > best_ev:
                    best_ev = e2
                if r2["name"] != proposal and e2 > max(ev * 1.5, ev + 0.08):
                    better.append({"name": r2["name"],
                                   "evidence": round(e2, 4)})
        rel = ev / best_ev if best_ev > 0 else (1.0 if ev > 0 else 0.0)

        reasons = []
        if ev < self.tau_abs:
            reasons.append(f"absolute evidence {ev:.3f} < {self.tau_abs}")
        if rel < self.tau_rel:
            reasons.append(f"relative evidence {rel:.3f} < {self.tau_rel}")
        status = VERIFIED if not reasons else REJECTED
        return Verdict(proposal, status, ev, rel, True,
                       provenance=row.get("provenance", "source"),
                       better=better[:3], reasons=reasons)


# ---------------------------------------------------------------------------
# proposer simulation
# ---------------------------------------------------------------------------
# Verification is a classification task over (statement, proposal) pairs, so
# it can be evaluated without any live model: take gold pairs, and corrupt
# them the ways proposers actually fail.


def corrupt(rng, rows, name2id, gold: str, mode: str) -> str | None:
    import random as _r
    gid = name2id.get(gold)
    if mode == "hallucinated":
        # recombine real tokens into a plausible nonexistent name
        parts = gold.split(".")
        donor = rows[rng.randrange(len(rows))]["name"].split(".")[-1]
        cand = ".".join(parts[:-1] + [donor + "_" + parts[-1].split("_")[-1]])
        return cand if cand not in name2id else cand + "'"
    if mode == "sibling":
        if gid is None:
            return None
        mod = rows[gid]["module"]
        sibs = [r["name"] for r in rows
                if r["module"] == mod and r["name"] != gold]
        return rng.choice(sibs) if sibs else None
    if mode == "wrong_namespace":
        tail = gold.split(".")[-1]
        alts = [n for n in name2id
                if n.endswith("." + tail) and n != gold]
        return rng.choice(alts) if alts else None
    if mode == "random":
        return rows[rng.randrange(len(rows))]["name"]
    raise ValueError(mode)


def evaluate(verifier: Verifier, gold_pairs: list[tuple[str, str, str]],
             seed: int = 0) -> dict:
    """gold_pairs: (text, title, gold_name). Reports acceptance rate per
    proposal population; a good verifier accepts correct proposals and
    rejects every corrupted population."""
    import random
    rng = random.Random(seed)
    rows = verifier.al.rows
    out = {}
    pops = ["correct", "sibling", "wrong_namespace", "hallucinated", "random"]
    for pop in pops:
        acc = tot = nonex = 0
        for text, title, gold in gold_pairs:
            prop = gold if pop == "correct" else corrupt(
                rng, rows, verifier.name2id, gold, pop)
            if prop is None:
                continue
            v = verifier.verify(text, prop, title)
            tot += 1
            if v.status == VERIFIED:
                acc += 1
            if v.status == NONEXISTENT:
                nonex += 1
        out[pop] = {"n": tot, "accept_rate": round(acc / max(1, tot), 3),
                    "caught_nonexistent": round(nonex / max(1, tot), 3)}
    return out
