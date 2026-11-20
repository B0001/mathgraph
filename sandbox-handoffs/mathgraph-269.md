# mathgraph-269 handoff (city mirror portfolio-hctz)

## Verdict: killed

The pre-registered kill test kills the time-split arm. Theorems added to
mathlib after the pin are **easier** negatives than the ones the repo can
already make, not harder ones. This holds for both systems and against both
controls, so it is killed under either reading of "for both lexical and
bge-small". Every number below is in `results/timesplit.json`, written by
`python -m mathgraph.timesplit report`.

## Numbers

The table is at the 10%-coverage threshold, on the eval halves (fitting is
described under Decisions). Each cell is the false-match rate with its Wilson
95% interval.

| system | threshold | time | holdout | deletion | positives answered / precision |
|---|---|---|---|---|---|
| lexical (`Aligner`, LEX), on coverage | 0.2125 | **8.1%** (67/830) [6.4, 10.1] | 12.5% (100/801) [10.4, 15.0] | 12.0% (100/830) [10.0, 14.4] | 60/603; 8/60 = 13.3% [6.9, 24.2] |
| bge-small-en-v1.5, on top-1 cosine | 0.9128 | **2.2%** (18/830) [1.4, 3.4] | 14.0% (112/801) [11.8, 16.6] | 13.0% (108/830) [10.9, 15.5] | 76/603; 0/76 [0, 4.8] |

- **Kill test.** The time-arm rate minus the control rate must exceed the time
  arm's own Wilson half-width (1.86 pp lexical, 1.01 pp bge).
  - Lexical: −4.4 pp against holdout, −4.0 pp against deletion.
  - bge: −11.8 pp and −10.8 pp.
  - All four comparisons fail.
- **Against the shipped `idx_mathlib`** (the index the bead names): time-arm
  rates are 7.95% [6.75, 9.35] lexical and 2.23% [1.62, 3.06] bge. These are
  the same as against the control index.
- **GRAPH_THRESHOLDS** (lexical, whole arms) answers almost nothing on
  docstring queries.
  - Positives: 4/1206 answered, 2 correct.
  - Rates: time 5/1660 = 0.30% [0.13, 0.70], holdout 2/1602 = 0.12%
    [0.03, 0.45], deletion 3/1660 = 0.18% [0.06, 0.53].
  - The time arm is nominally highest, but by 0.12–0.18 pp. That is below
    its 0.29 pp half-width.
- **Exploratory and post hoc; not part of the kill test.**
  - A control query's docstring sits verbatim on a row that stayed indexed (a
    sibling's copied docstring) for 260/1602 holdout negatives and 160/1660
    deletion negatives, against 22/1660 time negatives.
  - With those excluded from every arm, at the same thresholds:
    - lexical: time 8.0% against holdout 11.5% and deletion 12.0%;
    - bge: time 2.1% against 11.5% and 12.1%.
  - So the ordering is not an artefact of copied docstrings.
  - Query length and the share of query words with no index token are about
    the same across arms (median 6–7 content words; about 16% unindexed).
  - A guess, not tested: a random PIN theorem keeps its indexed family of
    variants, while a new theorem often arrives with its family (examples:
    the Ramanujan formulas for E₂/E₄/E₆, the Cartan matrices E₆/E₇).
- **bge's 0/76 positive precision is a construction effect, not a bug.**
  - Each positive's own corpus row was re-embedded without its docstring.
  - So the positives scoring highest are those with a near-duplicate sibling
    docstring, which wins rank 1.
  - Overall positive recall@1 is 65/1206 dense and 127/1206 lexical.

## Audit (the second kill criterion)

- **The sheet.** `results/timesplit-audit.csv` holds 60 time-arm
  (query, system) false-match pairs. They are a seeded sample of the 165
  pairs (161 distinct queries) answered at the 10% thresholds. The `rater1`
  and `rater2` columns are empty.
- **The pre-registered two-person audit has not been done.** It needs two
  people.
- **Provisional single-rater pass.** This agent labelled the pairs. It is not
  a person and had no second rater, and the labels are deliberately kept out
  of the sheet so that they cannot anchor the human raters.
  - Equivalent or generalising: **3/60 = 5.0% [1.7, 13.7]**, far below the
    30% bar.
    - #5: `CircleIntegrable.mul_continuousOn` against `mul_of_continuousOn`,
      the same fact up to `mul_comm`.
    - #18: a private lemma renamed from `UniquelyDecodable` to
      `IsUniquelyDecodable` with no deprecated alias, so the deprecation
      filter cannot see it.
    - #47: `Seminorm.bound_sum_of_continuous` follows from
      `bound_of_continuous` because sup ≤ sum.
  - The other 57 are new relative to the declaration they matched.
    - Most matches are unrelated, or are a definition.
    - #32 (Egorov under weaker hypotheses) and #41 (`Set` in place of
      `Finset`) strengthen their match.
    - #57 matched `every`, a leanscan phantom row scanned out of a block
      comment (mathgraph-dem.2).
  - The provisional pass does not change the verdict, because criterion 1
    already kills the arm.

## Absent set

- **Commits.** PIN is b44f89d (2026-07-26). NOV is d9a3e61, which is
  mathlib's own `master-2026-11-15` tag (2026-11-15T08:37Z).
- **Funnel.** Each line is what survives the filter, in order:
  - leanscan(NOV): 249,877
  - theorems: 192,454
  - not in leanscan(PIN) or elab(PIN): 10,213
  - declaration line added in `git diff PIN NOV -- Mathlib`: 10,067
  - no `_root_`: 9,808
  - not truncated: 9,760
  - not a window deprecation target: 7,868
  - statement differs from every PIN statement: 7,755
  - **has a docstring: 1,660** (above the bead's 150 NO-OP floor; all names
    unique)
- **Scan check.** The fresh leanscan(PIN) equals the shipped `mathlib.jsonl`
  name for name.

## Decisions and deviations from the bead text

1. **Head match.** This compares normalised *source* statements (keyword,
   name and body removed, whitespace collapsed) with every PIN source
   statement. The bead says "normalised elab head", but NOV has no elaborated
   environment without a Lean build.
2. **Deprecation filter.**
   - It covers aliases and `@[deprecated X]` wrappers whose line is added in
     the diff, or whose `since` is on or after the pin date.
   - A target is resolved against every enclosing namespace. Over-removal only
     costs negatives.
   - 510 NOV aliases put the target on the next line, which leanscan's head
     omits, so the target is read from source.
   - Without that fix, renames such as
     `CantorBendixson.iteratedDerivedSet_constant_iff_preperfect` came through
     as "new".
3. **Verso roles.** `doc.verso` is on in 1,356 NOV files and none at PIN.
   Role prefixes such as {name}`X` are stripped from every arm's query.
4. **Arms.** All arms are theorem docstrings.
   - Holdout is `index.build(holdout_frac=0.06)` as is. That includes keeping
     the holdouts' to_additive twins, the in-repo arm's known weakness.
   - Deletion is 1,660 theorems sampled from 25,650 PIN theorems whose name,
     statement and docstring are unchanged at NOV. Each gold and its
     to_additive twin is removed before the build. None was re-created as a
     twin, and 11 holdouts were dropped because their name stayed indexed.
   - Positives are `pmi_holdout_frac=0.06` probes, kept to source theorems
     with no to_additive attribute whose docstring no other indexed row
     shares: 1,206.
5. **One control index for all arms.** It has 244,361 rows, and its PMI is
   trained on about 88% of the docstrings. bge uses the same rows of the
   cached `emb_BAAI__bge-small-en-v1.5.npy`.
6. **Row order of the cached embedding (the bead's design question 2).**
   Re-embedding 64 random `idx_full` rows gives a minimum cosine of
   0.99999988 against the cache, so row i is still `idx_full` row i.
7. **The 10%-coverage threshold.**
   - Every arm is split in half (seed 0).
   - On the fit halves, each arm is subsampled to 603 and the four are pooled.
   - The threshold is `precision_at_coverage`'s cut, unrounded.
   - The kill test requires both controls to be beaten for both systems (the
     stricter reading).
8. **StructReranker.**
   - Math segments are the `$…$` spans of a docstring, and only about 1% of
     docstrings have any.
   - It changed the top-1 for 276 of 6,128 queries.
   - It never changes answer versus abstain, because coverage and margin come
     from `Aligner`.
   - Positive precision uses the `Aligner` top-1.
9. **Compute.** The bead budgets 1–2 CPU days, assuming corpus re-embedding.
   The run took about 10 CPU-minutes on the cached corpus embedding, with bge
   on CPU as the cache was built.

## Licence check (Apache-2.0)

- mathlib4 ships `LICENSE` (Apache-2.0) and no NOTICE file.
- The audit sheet quotes about 120 mathlib excerpts. `results/timesplit.json`
  carries the attribution.
- A public release of the data (for example portfolio-ge3) must ship the
  licence text alongside it.

## Unverified

- The two-person audit.
- How many renames remain beyond the audit's #18. The phantom spot-check
  (design question 3) is otherwise only the funnel plus the samples above.
- Labels are judged relative to the *matched* declaration only. No check was
  made that some other PIN declaration states the new theorem.

## Test run

`MATHGRAPH_DATA=<data dir> uv run pytest -q` printed
`97 passed in 801.37s (0:13:21)`. That is the 93 tests that passed before this
change, plus the 4 in `tests/test_timesplit.py`.

## Reproduce

```bash
# One network fetch: a blob:none partial clone holding both PIN and NOV.
git init mathgraph-data/mathlib4-nov && cd mathgraph-data/mathlib4-nov
git remote add origin https://github.com/leanprover-community/mathlib4.git
git config remote.origin.promisor true && git config remote.origin.partialclonefilter blob:none
git fetch --filter=blob:none --shallow-since=2026-11-13 origin +refs/heads/master:refs/remotes/origin/master
git fetch --no-tags --filter=blob:none --depth=1 origin b44f89d15d463ede557bdf673707a8610210becf
git sparse-checkout set Mathlib && git checkout d9a3e61fb84eff4c6bded19e8fbf7138f8890816 && cd ../..
export MATHGRAPH_DATA=/path/to/mathgraph-data     # mathlib4 at PIN, artifacts/
uv run python -m mathgraph.timesplit arms --nov mathgraph-data/mathlib4-nov
uv run python -m mathgraph.timesplit lexical
uv run --with sentence-transformers python -m mathgraph.timesplit dense
uv run python -m mathgraph.timesplit report
```

The working files go to `./mathgraph-data/timesplit` (gitignored). This run
made two environment choices:

- The dense stage ran in a worktree venv, `build/venv-dense`, with
  `HF_HUB_OFFLINE=1`, rather than `uv run --with`.
- `pytest` is not a repo dependency, so it was installed into the worktree
  `.venv` to run `uv run pytest -q`.
