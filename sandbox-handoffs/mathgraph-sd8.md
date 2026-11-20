# mathgraph-sd8 handoff (city mirror portfolio-poj8)

## Verdict: killed by C1; the time half survives

The kill test was pre-registered in `sandbox-handoffs/mathgraph-sd8-prereg.md`
(commit `96606ac`, before any score under these conditions). Every number below
is in `results/lfo.json`, written by `python -m mathgraph.lfo report`.

- **C1 fails for both encoders, so the test is killed under both readings.**
  Removing the query's name-defined family closes 40.2% of the bge-small gap
  and 37.5% of the bge-base gap. The bar was 50%. Closure is
  (holdout base − holdout family removed) / (holdout base − time base).
- **C2 passes for both.** Family removal beats removing as many random
  same-module rows. That control does nothing: 14.0% stays 14.0% (bge-small).
  The paired bootstrap gives p = 0.0001 for each encoder.
- **C3 passes for both, so the time half is not falsified.** Adding the
  13,008 post-pin declarations raises the time arm's false-match rate by
  7.7 pp (bge-small) and 8.3 pp (bge-base). The bar was 4 pp.

So name-defined family presence is a real and specific cause of the
holdout-vs-time gap, but it is less than half of it. The hypothesis needed it
to be at least half.

## Numbers

Rates are false-match rates on the eval halves (`halves()[1]`) at the frozen
10%-coverage thresholds, with Wilson 95% intervals. The matched-random cells
are averages over 20 draws, so they carry a percentile bootstrap interval.

| system (τ) | arm | base | family removed | matched random | siblings added |
|---|---|---|---|---|---|
| bge-small (0.9128) | holdout | 14.0% (112/801) [11.8, 16.6] | **9.2%** (74/801) [7.4, 11.4] | 14.0% [11.8, 16.6] | |
| | deletion | 13.0% (108/830) [10.9, 15.5] | 10.5% (87/830) [8.6, 12.8] | 12.9% [10.7, 15.3] | |
| | time | 2.2% (18/830) [1.4, 3.4] | 1.8% (15/830) [1.1, 3.0] | | **9.9%** (82/830) [8.0, 12.1] |
| bge-base (0.8780) | holdout | 12.7% (102/801) [10.6, 15.2] | **8.9%** (71/801) [7.1, 11.0] | 12.7% [10.5, 15.0] | |
| | deletion | 12.8% (106/830) [10.7, 15.2] | 10.5% (87/830) [8.6, 12.8] | 12.7% [10.5, 14.9] | |
| | time | 2.4% (20/830) [1.6, 3.7] | 2.2% (18/830) [1.4, 3.4] | | **10.7%** (89/830) [8.8, 13.0] |
| lexical (0.2125) | holdout | 12.5% (100/801) [10.4, 15.0] | 12.2% (98/801) [10.1, 14.7] | 12.5% [10.3, 14.8] | |
| | deletion | 12.0% (100/830) [10.0, 14.4] | 11.9% (99/830) [9.9, 14.3] | 12.0% [10.0, 14.4] | |
| | time | 8.1% (67/830) [6.4, 10.1] | 8.1% (67/830) [6.4, 10.1] | | 8.4% (70/830) [6.7, 10.5] |

The kill-test statistics come with bootstrap 95% intervals.

| | bge-small | bge-base | lexical (not gated) |
|---|---|---|---|
| gap, holdout − time | 11.8 pp [9.2, 14.5] | 10.3 pp [7.9, 12.9] | 4.4 pp [1.5, 7.4] |
| C1 closure (holdout) | **0.402** [0.296, 0.519] | **0.375** [0.264, 0.503] | 0.057 [−0.054, 0.235] |
| C2 random − family (holdout) | 4.7 pp [3.3, 6.2], p = 0.0001 | 3.8 pp [2.6, 5.2], p = 0.0001 | 0.2 pp [−0.2, 0.8], p = 0.19 |
| C3 rise (time, siblings added) | **7.7 pp** [6.0, 9.6] | **8.3 pp** [6.5, 10.2] | 0.4 pp [0.0, 0.8] |
| deletion closure (not gated) | 0.233 [0.144, 0.333] | 0.221 [0.133, 0.324] | 0.030 [0.0, 0.143] |

- **Readings of "for bge-small AND bge-base".**
  - Strict (primary: every encoder must pass): killed; time half not
    falsified.
  - Literal (one passing encoder is enough): the same, because C1 fails for
    both encoders and C3 passes for both.
- **Contingency.** Both bge gaps exclude 0, so C1 was evaluated for both.
- **Deletion closes less than holdout**, likely because a deletion gold was
  removed with its to_additive twin, so the strongest family member was
  already gone.
- **Lexical barely moves under any condition.** 8 of its 100 holdout false
  matches have a top-1 inside the family, against 48 of 112 for bge-small.
  Lexical false matches are not family-driven.

## Diagnostics

- **Families** (rule frozen in `mathgraph/lfo.py`, checked by
  `tests/test_lfo.py`):

  | arm | has an indexed family member | p90 size | max size |
  |---|---|---|---|
  | holdout | 43.4% | 3 | 20 |
  | deletion | 37.6% | 2 | 19 |
  | time | 7.3% | — | 9 |

  - A further 24.9% of time queries have family among the post-pin rows.
  - The matched-random draw ran short of same-module rows for 10 holdout
    and 9 deletion queries; all available rows were masked for those.
- **Base false matches whose top-1 is in the query's family.**
  - bge-small: holdout 48/112, deletion 26/108, time 3/18.
  - bge-base: holdout 42/102, deletion 31/106, time 3/20.
- **Siblings added, bge-small.**
  - 66 of the 82 answered time queries have a post-pin top-1.
  - 33 of those 66 are in the query's name-defined post-pin family.
  - bge-base: 73 of 89, and 35.

## Secondary analysis (not gated)

**The covariate.** J is the IDF-weighted Jaccard over constant identifiers
between a query and its nearest indexed same-module sibling, computed from
full declaration text re-read from source.
- Coverage is 100% in every arm, so binning went ahead.
- Pooled quintile edges: 0.109, 0.195, 0.271, 0.370.
- The arms sit far apart on it. Median base J is 0.29 for holdout, 0.27 for
  deletion and 0.11 for time. 415 of the 830 time eval queries fall in the
  lowest bin, against 39 of 801 holdouts.

**False-match rate rises with J in every arm.** bge-small, lowest to highest
bin:

| arm | lowest bin | highest bin |
|---|---|---|
| holdout | 5.1% | 20.2% |
| time | 1.7% | 8.5% |
| time with siblings added | 2.9% | 14.6% |

**Stratifying by J explains about a quarter of the gap.** The holdout-minus-
time gap shrinks:
- bge-small: 11.8 → 8.7 pp;
- bge-base: 10.3 → 8.1 pp;
- lexical: 4.4 → 4.6 pp (no change).

Within every bin, holdouts still false-match more often than time queries,
by 2.4× to 9×. The time arm's middle bins rest on 2 and 1 false matches. So
symbolic closeness explains part of the gap, less than the family rule does.

## Reading the result (post hoc, not part of the kill test)

- **The time arm's 2.2% says little about new theorems being easy.** Its
  co-arrived neighbourhood was missing from the index. With it indexed:
  - bge-small reaches 9.9%, recovering 65% of the gap to holdout
    (7.7 / 11.8 pp);
  - bge-base reaches 10.7%, recovering 80% (8.3 / 10.3 pp).
- **The two conditions are not mirror images.**
  - Siblings-added indexes every co-arrived declaration, and half of the new
    top-1s are outside the name family.
  - Family removal masks only the name family.
  - So the neighbours behind the gap are wider than names (stem, to_additive,
    alias) can define. Raising closure would need a broader family rule. That
    would be a new experiment, not a re-reading of this one.
- **Part of the remaining 4.1 pp (bge-small) may be design.** The holdout
  index keeps each holdout's own to_additive twin, while siblings-added
  excludes the query's twin and aliases and adds no to_additive expansions of
  post-pin rows. This is not measured.

## Decisions and deviations

1. **Lexical reproduction gate.**
   - Pre-registered criterion: top-1 identical for ≥ 99% of records, and the
     eval-half false-match counts identical.
   - Result: top-1 agreement is 96.2% (4,735/4,922). The counts are identical
     (100, 100 and 67), and the largest score difference is 0.0.
   - All 187 disagreements are exact ties: the published top-1 has the same
     normalised and raw score as this run's. `align(topk=5)` ranks 10
     candidates and this run ranks 50, and `argpartition` orders ties
     differently.
   - So the scores the rates depend on are reproduced exactly. The gate's
     top-1 clause is treated as passed on investigation. Lexical is not gated
     either way.
   - The bge-small gate passed outright: 100% top-1 agreement, a largest
     score difference of 0.0, and counts identical (112, 108 and 18).
2. **Other gates.**
   - Corpus cache row checks: minimum cosine 0.99999988 (bge-small) and 1.0
     (bge-base). So the bge-base cache, built 2026-09-24, is CPU-identical
     and row-aligned.
   - This run's bge-small embedding of the post-pin rows against r2's
     `E_new.npy`: minimum row cosine 0.9999996.
   - Lexical appended-row scoring against the Aligner's own scores: largest
     difference 1.9e-6 (float32).
3. **The bge-base threshold** is 0.8780, fitted by `score_system` on its own
   base records, which the pre-registration allows.
4. **Dense control rows.**
   - Rows are selected by name, as in `timesplit.run_dense`. That gives
     244,392 `idx_full` rows for 244,361 control names (duplicate names), and
     no control name is missing.
   - The 1,215 positive rows are re-embedded without docstrings.
5. **Post-pin embeddings.** They are computed by this code for both encoders
   (`mathgraph-data/lfo/emb_new_*.npy`, 20 and 40 MB) rather than read from
   r2. For bge-small they are checked against r2 (item 2).
6. **No lexical query** needed the full-index rescore: every masked query
   found an unmasked candidate within its top 50.
7. **Compute.**
   - Times: plan 2.5 min, bge-small 32 min, bge-base 42 min, lexical 1.5 min,
     covariate 3 min.
   - That is about 1.4 CPU-hours, niced, on the 8-core host. The bead
     budgeted about one CPU-day.

## Unverified

- **Family members are not checked by hand.** The rule is name-only by design.
  - Spot checks look right, for example
    `ContinuousWithinAt.clm_bundle_apply` →
    `Continuous/ContinuousAt/ContinuousOn.clm_bundle_apply`.
  - Generic last components such as `ext` or `mono` can join unrelated
    declarations of one module.
- **The split of family effects by type** (twin, stem, alias) is not reported.
- **The post hoc reading above has not been tested**: the broader neighbour
  set and the twin asymmetry.
- **These are docstring queries only.** Whether the result transfers to LaTeX
  queries (arm M) is open, as the r2 synthesis notes.

## Test run

`MATHGRAPH_DATA=<data dir> UV_OFFLINE=1 uv run --with pytest pytest -q` printed
`106 passed in 1137.44s (0:18:57)`. `tests/test_lfo.py` adds 9 tests to the 97
that passed in mathgraph-269:
- 6 for the family rule on known mathlib twins;
- 3 for the kill criteria on synthetic data.

## Reproduce

```bash
export MATHGRAPH_DATA=/path/to/mathgraph-data      # artifacts/, mathlib4 at PIN,
                                                   # hctz-timesplit/ (the mathgraph-269 outputs)
NOV=/path/to/mathlib4-nov                          # see mathgraph-269.md
python -m mathgraph.lfo plan --nov $NOV
HF_HUB_OFFLINE=1 python -m mathgraph.lfo dense --system bge-small --r2 $MATHGRAPH_DATA/r2/E_new.npy
HF_HUB_OFFLINE=1 python -m mathgraph.lfo dense --system bge-base
python -m mathgraph.lfo lexical
python -m mathgraph.lfo covariate --nov $NOV
python -m mathgraph.lfo report                     # -> results/lfo.json
```

- **Working files** go to `./mathgraph-data/lfo` (gitignored).
- **The dense stages** ran in a worktree venv, `build/venv-dense`, with
  torch 2.15.0, sentence-transformers 6.3.0, transformers 5.23.0 and
  numpy 2.5.4, all on CPU.
- **Inputs are read-only.**
  - `mathgraph-data/hctz-timesplit/` is byte-identical to the hctz worktree's
    `mathgraph-data/timesplit/`.
  - `mathgraph-data/r2/` is byte-identical to the r2 scratchpad.
- **Licence.** `results/lfo.json` holds counts and rates only, with no mathlib
  text or names. The mathgraph-269 licence note applies to any release of the
  arms.
