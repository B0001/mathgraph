"""Calibration harness.

Positives are declarations that are in the index but whose docstrings never
trained the translation table. Negatives are declarations removed from the
index entirely -- their docstrings describe something the index genuinely does
not contain, so the only correct answer is to abstain.

Without the negative arm you cannot calibrate abstention at all: any threshold
looks fine if every query has an answer.
"""
from __future__ import annotations

import json, math, os, random, sys
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


# -- the arms GRAPH_THRESHOLDS is fitted on ---------------------------------
#
# Different arms from the ones above, and the reason is the corpus. `run` uses
# declarations held out of an index; `graph` runs on paper prose, so its
# thresholds have to be fitted on paper prose. The 439 harvested blueprint
# pairs are that -- author-written statements whose declaration the author
# named -- and the negative arm is the same statements against a mathlib-only
# index, where the project's own declaration genuinely does not exist.
#
# This procedure was documented before it was code, and was run by hand. That
# is how GRAPH_THRESHOLDS came to be fitted against a corpus (unvalidated
# to_additive reconstructions) that the index builder no longer produces.


def graph_arms(art_dir: str, pairs_path: str, present: str = "idx_blueprint",
               absent: str = "idx_mathlib", **kw):
    """Records shaped like `run`'s, for the `graph` operating point."""
    pairs = [json.loads(l) for l in open(pairs_path, encoding="utf-8")]
    al_p = Aligner(load(os.path.join(art_dir, present)), **kw)
    al_a = Aligner(load(os.path.join(art_dir, absent)), **kw)
    absent_names = {r["name"] for r in al_a.rows}

    recs = []
    for r in pairs:
        targets = set(r.get("targets") or [])
        a = al_p.align(r["text"], title=r.get("title", ""), topk=5)
        names = [c.name for c in a.candidates]
        hits = [i + 1 for i, n in enumerate(names) if n in targets]
        recs.append(("pos", a.coverage, a.margin, min(hits) if hits else 0))
        # a statement whose answer is in mathlib after all is not a negative
        if targets & absent_names:
            continue
        b = al_a.align(r["text"], title=r.get("title", ""), topk=5)
        recs.append(("neg", b.coverage, b.margin, 0))
    return recs


def _ceil4(x: float) -> float:
    """Round away from the answered region. A threshold is shipped as a 4-dp
    literal in cli.py, so the fit has to be evaluated at the literal: rounding
    a margin floor of 0.264849 down to 0.2648 re-admits the negative that set
    it, and the constraint the whole search enforces is silently broken."""
    return math.ceil(x * 1e4) / 1e4


def sweep_zero_false(recs):
    """Exhaustive search over every observed (coverage, margin) value at the
    zero-false-match constraint: of the pairs that admit no false match on the
    absent arm, take the one answering most, breaking ties toward more correct.

    Answered-not-rank-1 is not a false match here. The absent arm is what the
    constraint is about -- claiming a declaration for a statement whose answer
    does not exist -- and it is the failure the whole abstention layer exists
    to prevent.

    Every count reported is measured at the rounded thresholds, so it is the
    behaviour of the shipped constant rather than of an unrepresentable
    optimum near it."""
    pos = np.array([(c, m, r == 1) for k, c, m, r in recs if k == "pos"])
    neg = np.array([(c, m) for k, c, m, r in recs if k == "neg"])
    best = None
    for raw_tau in np.unique(pos[:, 0]):
        # the smallest margin admitting no negative at this coverage; every
        # delta below it is infeasible, every delta above it answers no more
        live = neg[neg[:, 0] >= raw_tau]
        tau = _ceil4(float(raw_tau))
        dl = _ceil4(float(live[:, 1].max())) if live.size else 0.0
        p = pos[(pos[:, 0] >= tau) & (pos[:, 1] >= dl)]
        n = neg[(neg[:, 0] >= tau) & (neg[:, 1] >= dl)]
        if len(n):                      # _ceil4(tau) can re-admit a negative
            continue
        cand = {"tau_cov": tau, "delta_margin": dl,
                "answered": int(len(p)), "correct": int(p[:, 2].sum()),
                "n_pos": int(len(pos)), "n_neg": int(len(neg)),
                "false_matches_on_absent": 0}
        key = (cand["answered"], cand["correct"])
        if best is None or key > (best["answered"], best["correct"]):
            best = cand
    return best


# -- the arms VERIFY_PROFILES is fitted on ----------------------------------
#
# Three proposal populations over the same 439 statements: the author's own
# declaration, the top-ranked candidate that is not it, and a random
# declaration. The middle one is the adversary that matters -- it is lexically
# the closest thing to the answer that is not the answer, which is the shape
# of a confident wrong LLM proposal.


def verify_arms(art_dir: str, pairs_path: str, corpus: str = "idx_blueprint",
                **kw):
    """(project, population, evidence, rel_evidence, pattern_fired) per proposal.

    Collected once at zero thresholds, because accept is
    `pattern_fired or (ev >= tau_abs and rel >= tau_rel)` -- so a threshold
    sweep is arithmetic over these rows rather than thousands of re-verifies.
    """
    import random
    from .verify import Verifier
    pairs = [json.loads(l) for l in open(pairs_path, encoding="utf-8")]
    al = Aligner(load(os.path.join(art_dir, corpus)), **kw)
    known = {r["name"] for r in al.rows}
    names = [r["name"] for r in al.rows]
    rng = random.Random(0)
    V = Verifier(al, tau_abs=0.0, tau_rel=0.0)

    def rec(p, proposal):
        v = V.verify(p["text"], proposal, p.get("title", ""),
                     math_segments=p.get("math", []))
        return (v.evidence, v.rel_evidence,
                bool(v.reasons and "formula pattern" in v.reasons[0]))

    rows = []
    for p in pairs:
        gold = [t for t in p["targets"] if t in known]
        if not gold:
            continue
        proj = p.get("project", "?")
        a = al.align(p["text"], title=p.get("title", ""), topk=5)
        rows.append((proj, "correct") + rec(p, gold[0]))
        wrong = next((c.name for c in a.candidates if c.name not in set(gold)),
                     None)
        if wrong:
            rows.append((proj, "top_wrong") + rec(p, wrong))
        rows.append((proj, "random") + rec(p, rng.choice(names)))
    return rows


def accept_rate(rows, population, tau_abs, tau_rel, projects=None) -> float:
    sel = [r for r in rows if r[1] == population
           and (projects is None or r[0] in projects)]
    if not sel:
        return 0.0
    return sum(1 for _, _, ev, rel, fired in sel
               if fired or (ev >= tau_abs and rel >= tau_rel)) / len(sel)


def dominating(rows, tau_abs, tau_rel, projects=None):
    """A threshold accepting strictly more correct proposals at no worse rate
    on *every* negative population -- the repo's stated refit criterion.

    Searching ~100k grid points against 439 statements will find one of these
    whether or not the improvement is real, so `__main__` refits on half the
    blueprint projects and scores on the other half before believing it."""
    base = {p: accept_rate(rows, p, tau_abs, tau_rel, projects)
            for p in ("correct", "top_wrong", "random")}
    grid = [sorted({round(r[2], 4) for r in rows if r[1] == "correct"}),
            sorted({round(r[3], 4) for r in rows if r[1] == "correct"})]
    best = None
    for ta in grid[0]:
        for tr in grid[1]:
            c = accept_rate(rows, "correct", ta, tr, projects)
            if c <= base["correct"]:
                continue
            if any(accept_rate(rows, p, ta, tr, projects) > base[p]
                   for p in ("top_wrong", "random")):
                continue
            if best is None or c > best[0]:
                best = (c, ta, tr)
    return base, best


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        # `verify <artifacts>` -- the published verifier table, plus whether
        # any threshold beats a shipped profile in a way that survives being
        # scored on projects it was not fitted on.
        from .cli import LEX, VERIFY_PROFILES
        art = sys.argv[2] if len(sys.argv) > 2 else "./mathgraph-data/artifacts"
        rows = verify_arms(art, os.path.join(art, "blueprint_pairs.jsonl"),
                           tau_cov=0.0, delta_margin=0.0, **LEX)
        projs = sorted({r[0] for r in rows})
        fit = {p for i, p in enumerate(projs) if i % 2 == 0}
        held = set(projs) - fit
        out = {"projects": projs, "held_out": sorted(held), "profiles": {}}
        for name, kw in VERIFY_PROFILES.items():
            ta0, tr0 = kw["tau_abs"], kw["tau_rel"]
            base, _ = dominating(rows, ta0, tr0)
            entry = {"thresholds": [ta0, tr0],
                     "rates": {k: round(100 * v, 1) for k, v in base.items()}}
            _, best = dominating(rows, ta0, tr0, projects=fit)
            if best is None:
                entry["transfers"] = "nothing dominates in-fold"
            else:
                _, ta, tr = best
                entry["refit_on_fit_half"] = [ta, tr]
                entry["held_out"] = {
                    k: [round(100 * accept_rate(rows, k, ta0, tr0, held), 1),
                        round(100 * accept_rate(rows, k, ta, tr, held), 1)]
                    for k in ("correct", "top_wrong", "random")}
            out["profiles"][name] = entry
        print(json.dumps(out, indent=2))
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "graph":
        # `graph <artifacts>...` -- positives come from the first corpus, and
        # negatives from every one given, so a threshold can be fitted to hold
        # on a validated and an unvalidated corpus at once. Both ship.
        from .cli import LEX
        arts = sys.argv[2:] or ["./mathgraph-data/artifacts"]
        kw = dict(tau_cov=0.0, delta_margin=0.0, **LEX)
        pairs = next(p for p in (os.path.join(d, "blueprint_pairs.jsonl")
                                 for d in arts) if os.path.exists(p))
        recs = graph_arms(arts[0], pairs, **kw)
        for extra in arts[1:]:
            recs += [r for r in graph_arms(extra, pairs, **kw) if r[0] == "neg"]
        print(json.dumps(sweep_zero_false(recs), indent=2))
        sys.exit(0)
    kw = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    recs = run(**kw)
    print(json.dumps({"ranking": rank_report(recs),
                      "calibrated": sweep(recs)}, indent=2))
