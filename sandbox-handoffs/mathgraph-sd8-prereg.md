# mathgraph-sd8 pre-registration: leave-family-out test of the co-arrival hypothesis

City mirror portfolio-poj8. Written and committed before any score under the
conditions below was computed. The only outcome numbers seen when this was
written are the baseline ones already published in `results/timesplit.json`
(mathgraph-269). The family rule is frozen in code in the same commit:
`stem`, `link_target`, `resolve` and `Families` in `mathgraph/lfo.py`, checked
by `tests/test_lfo.py`.

## Hypothesis

At the frozen 10%-coverage thresholds, bge-small answers 14.0% of random
holdouts and 13.0% of deletions, but only 2.2% of theorems new at NOV
(eval halves). The co-arrival hypothesis says the gap comes from family
presence, not from novelty. A holdout or a deletion leaves its family in the
index; a new theorem tends to arrive with its family, which the index then
lacks.

## Inputs (read-only)

- The hctz time-split outputs, from the snapshot
  `mathgraph-data/hctz-timesplit/` (byte-identical to the hctz worktree's
  `mathgraph-data/timesplit/`):
  - `arms.jsonl`: time 1,660, holdout 1,602, deletion 1,660, positive 1,206;
  - `idx_ctrl` (244,361 rows);
  - `dense.jsonl` and `lexical.jsonl` (the published baseline);
  - `scans.pkl` (leanscan at PIN, 241,703 rows, and at NOV, 249,877 rows).
- The post-pin set: the 13,008 NOV-scan rows whose names leanscan(PIN) lacks,
  in `scans.pkl` order. This is the row set of r2's `E_new.npy`
  (`mathgraph-data/r2/`, 13,008 × 384, bge-small).
- Corpus embeddings over `idx_full`, in shared `mathgraph-data/artifacts/`:
  `emb_BAAI__bge-small-en-v1.5.npy` and `emb_BAAI__bge-base-en-v1.5.npy`.
- Source trees: PIN at `mathgraph-data/mathlib4` (b44f89d) and NOV at the hctz
  worktree's `mathgraph-data/mathlib4-nov` (d9a3e61).

## Family rule (frozen)

The family of a declaration q (module m) is every other declaration X such that:

1. X is in module m and `stem(X) == stem(q) != ""`. The stem is the last name
   component with:
   - primes removed;
   - the snake-case components cut before the first `of` after the first
     component (the `_of_` hypothesis tail);
   - the camel/snake tokens `add Add mul Mul left Left right Right Within NE On`
     dropped (case-sensitive, so `ne` in `mul_ne_zero` stays);
   - the remainder joined and lowercased.
2. X and q are a to_additive pair, either direction. The pair is the twin
   `index.build` would generate from the scanned `@[to_additive]` attribute
   (`timesplit.twin`), on PIN-scan and NOV-scan rows.
3. X and q are linked by an alias, either direction. The link is an `alias`
   row (leanscan scans only single-name aliases), or a declaration whose
   `@[deprecated T]` names T. The target is resolved innermost-namespace-first
   against the scanned names, and read from source when it sits on the next
   line.

No embedding enters the rule. Item 3 also counts non-deprecated aliases, a
small widening of "deprecated alias": an alias is the same constant.

## Conditions

Every query keeps its arm and its eval-half membership from mathgraph-269.
Within each system, every condition is scored on the same `idx_ctrl` rows with
the same query encoding.

| arm | condition | what changes for query q |
|---|---|---|
| holdout, deletion, time | base | nothing (reproduces mathgraph-269) |
| holdout, deletion | family removed | every indexed member of family(q) is masked |
| holdout, deletion | matched random | k = (number of indexed family members) random indexed rows of q's module, outside family(q), are masked; 20 seeded draws per query, averaged; if the module has fewer than k such rows, all are masked and the shortfall is reported |
| time | siblings added | the 13,008 post-pin rows join the index, minus q itself and every name in its to_additive/alias links (item 2 and 3 of the rule) |
| time | family removed (exploratory) | the indexed (PIN) members of family(q) are masked |

The post-pin rows are raw scan rows: no to_additive expansion is applied to
them. This is conservative for the siblings-added prediction.

**Dense** (bge-small-en-v1.5 and bge-base-en-v1.5, CPU, `HF_HUB_OFFLINE=1`). This
follows `timesplit.run_dense`:
- the cached corpus embedding is restricted to `idx_ctrl` names;
- the positives' own rows are re-embedded without docstrings;
- queries carry the bge retrieval prefix;
- the score is the top-1 cosine after the per-query mask (-inf on masked rows).

Post-pin rows are embedded with `bench_pretrained.doc_text`, the corpus text.
For bge-small, that embedding must match r2's `E_new.npy`.

**Lexical**: `Aligner(idx_ctrl, tau_cov=0, delta_margin=0, **LEX)`.
- Masking post-filters the candidate list `align(q, topk=50)` ranks. The
  score is the coverage (raw/mass) of the first unmasked candidate. If all 50
  are masked, q is rescored with every row.
- Siblings added: post-pin rows are scored by the control Aligner's own
  scoring as if appended to its index. Every statistic is held at the control
  index's values: IDF, PMI table, df cut-offs, field gates, length pivot and
  mean, and query mass.
- The query's top-1 is whichever of the control top-1 and the best eligible
  post-pin row has the higher length-normalised score.

## Thresholds and rates

- Frozen 10%-coverage thresholds, fitted by `timesplit.score_system` on the
  base fit halves:
  - lexical and bge-small: recomputed from the published hctz records (0.2125
    and 0.9128 rounded);
  - bge-base: fitted the same way on its own base records, before any other
    condition is scored.
- The same strictness flag applies everywhere.
- Rates are on `halves()[1]` (seed 0) of each arm, with Wilson 95% intervals.
  The matched-random condition has a fractional count, so it gets a
  percentile bootstrap interval.

## Reproduction gates (stop and investigate if any fails)

- bge-small base equals hctz `dense.jsonl`: top-1 identical for ≥ 99% of
  records, and the eval-half false-match counts identical.
- Lexical base equals hctz `lexical.jsonl` (ctrl): the same two conditions.
- The bge-base cache row check: re-embedding 64 random `idx_full` rows gives a
  minimum cosine of at least 0.999.
- The bge-small post-pin embedding against r2 `E_new.npy`: a minimum row
  cosine of at least 0.999.

## Kill test (gated: bge-small and bge-base, holdout arm, eval halves)

Notation: F(arm, condition) is the false-match rate.

- **C1 (gap closure).** Compute
  `closure = (F(holdout, base) − F(holdout, family removed)) / (F(holdout, base) − F(time, base))`.
  KILL if closure < 0.50.
- **C2 (beats the matched control).** Run a paired bootstrap over holdout
  eval-half queries: 10,000 resamples, seed 0, d = F(matched random) −
  F(family removed). Let p = (1 + #{d* ≤ 0}) / 10,001. KILL if p ≥ 0.05.
- **C3 (separate falsification of the time half).** Compute
  `rise = F(time, siblings added) − F(time, base)`. FALSIFIED if
  rise < 4 pp.

**Reading of "for bge-small AND bge-base" (primary: strict).**
- Each criterion must hold for both encoders, so one failing encoder kills
  (or, for C3, falsifies). This matches mathgraph-269, which took the stricter
  of two readings.
- The literal Boolean reading (kill only if both encoders fail) is reported
  next to it.

**Contingency.** If an encoder's base holdout-vs-time gap has a 95% bootstrap
interval that includes 0, there is no gap for it to close. C1 is then decided
by the other encoder, and this is reported.

**Not gated, reported with the same statistics:**
- the deletion arm;
- lexical, whose gap is within about 1 SE of noise;
- time with its family removed.

Point estimates decide C1 and C3. Bootstrap intervals (closure: independent
resampling of holdout and time queries; rise: paired) are reported alongside.

## Secondary analysis (not gated)

**The covariate.** J(q) is the IDF-weighted Jaccard over constant identifiers
between q and its nearest indexed sibling.
- **Text.** A declaration's full source text runs from its scanned line to
  the line before the next scanned declaration of the same file, with
  comments and docstrings removed. It comes from the PIN tree, or the NOV
  tree for time queries and post-pin rows. A generated-twin query uses its
  source original's text.
- **Constant identifiers.** Lean identifiers in that text that name a scanned
  declaration (PIN ∪ NOV), either exactly or as a trailing suffix of a full
  name (for `open` namespaces).
- **Weights.** IDF is computed over all PIN-scan declarations as
  log(1 + N/(1 + df)). J = Σ idf(A ∩ B) / Σ idf(A ∪ B).
- **Nearest sibling.** The maximum over source rows of q's module that are
  indexed under the condition, excluding q itself and masked rows. Post-pin
  rows count for "siblings added". J = 0 when there is no such row.

**Coverage gate.** Coverage is the share of an arm's eval-half queries whose
own text yields at least one constant identifier. Bin only if it is at least
90% in every arm binned; otherwise report coverage and stop.

**Bins.** Pooled quintiles of J over the eval halves of the three base arms,
with duplicate edges merged.

**Report**, for each system:
- F per (arm, condition, bin) with Wilson intervals;
- the holdout-minus-time gap stratified by bin (CMH weights
  n_h·n_t/(n_h + n_t)) against the unstratified gap.

## Diagnostics reported

- Per arm: indexed family sizes (share ≥ 1, median, p90, max).
- The share of answered false matches whose top-1 is in family(q), per arm and
  condition (for siblings added: whether the top-1 is a post-pin row, and
  whether it is in family(q)).
- The matched-random shortfall.
- The reproduction gates.
