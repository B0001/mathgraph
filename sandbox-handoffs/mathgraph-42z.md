# mathgraph-42z handoff: rebuilt timesplit positive arm

## Pre-registration (committed before any retrieval number on the new arm was computed)

### Why

The hctz build (mathgraph-269) scores bge's positives against their own row
re-embedded without its docstring, while every row a negative query can hit
keeps its docstring. The gold row is the only row in the corpus built from a
different text recipe. Computed from the hctz `dense.jsonl` / `lexical.jsonl`
(control corpus, whole arms), the AUROC of the raw top-1 score for correct
positives against each negative arm is:

| system | holdout | deletion | time | correct top-1 positives |
|---|---|---|---|---|
| bge-small | 0.375 | 0.364 | 0.700 | 65 / 1,206 |
| lexical | 0.576 | 0.585 | 0.623 | 127 / 1,206 |

With an AUROC below 0.5 against both in-library controls and about 32 to 63
correct positives per half, no confidence-signal experiment on these arms is
decisive.

### Inputs, fixed and read-only

These come from the hctz build at
`.claude/worktrees/portfolio-hctz/mathgraph/mathgraph-data/timesplit`.

- **Control index `idx_ctrl`.** 244,361 rows: PIN minus 4,102 holdouts minus
  1,660 deletion golds and their to_additive twins. It is copied unchanged
  into the new directory, and its sha256 is recorded.
- **Negative arms.** Time (1,660), holdout (1,602) and deletion (1,660)
  queries, taken unchanged from `arms.jsonl`.

### What is rebuilt

1. **Positive arm.** Every control row that is a source theorem with a
   cleaned docstring, no `to_additive` attribute, a docstring no other control
   row shares (these are the hctz filters), and a name no other control row
   carries. Counted before this pre-registration from the index alone:
   20,773 rows pass the hctz filters, and 106 of them share their name, which
   leaves **20,667 positives**. hctz had 1,206.
2. **Lexical (`Aligner(**LEX)`, coverage, top-5).** A lexical row holds name,
   module and type tokens only. No row holds docstring text, so the gold row
   is already built like every other row. The one leak is the PMI translation
   table, and it is cross-fitted:
   - The control index's 64,266 docstring rows are shuffled (seed 0) into 10
     folds.
   - Table *k* is `index.build`'s PMI over the docstring rows outside fold *k*.
   - A positive is scored with its own fold's table.
   - Each negative query is assigned a fold uniformly at random (seed 0) and
     scored with that fold's table. Every arm is therefore scored by the same
     kind of system: a table trained on 90% of the control docstrings.
   - There is no StructReranker.
3. **Dense (bge-small-en-v1.5).** Every control row is embedded from one text
   recipe, `name. head`. That is the text the hctz build gave only to the
   positives' rows. No row carries a docstring, so the gold row and every row
   a negative can hit are built the same way. Queries are unchanged: the bge
   query prefix plus the cleaned docstring. Scores are the top-1 cosine and the
   top-1 minus top-2 margin over all control rows.

### Targets (pass/fail, per system)

- **T1, comparable text.**
  - (a) Dense: one function builds every corpus row's text, and no corpus
    row's text contains its own cleaned docstring. The count must be 0.
  - (b) Lexical: no positive is scored by a table whose training docstrings
    include its own row. This is checked for each positive against the fold
    assignment, and the count must be 0.
- **T2, enough correct positives.** The number of positives whose top-1 is
  their own name must be at least 400 in each of `halves(positive names,
  seed 0)`, both the fit half and the eval half. This is checked separately
  for lexical and for bge-small.

The bead is satisfied for a system when T1 and T2 both pass for it. If T2
fails for a system, the counts are reported and the arm is not declared
decisive for that system. There is no further enlargement, because every
eligible row is already a positive.

### Descriptive (reported either way, not gated)

- The AUROC table above, recomputed on the new arms by the same function. The
  hctz values are kept as the before column.
- Positive recall@1 per system.
- Dense only: the median corpus-text length of correct positives' gold rows
  against the top-1 rows of each negative arm.
- The median number of content words per query (`doc_words`) for each arm.

### Out of scope

- A new kill test of the time arm.
- Threshold fitting.
- StructReranker.
- `idx_mathlib` comparisons.
- Arm M (27 blueprint-to-mathlib LaTeX queries), which this bead does not
  grow.

## Verdict: both targets pass, for both systems

T1 and T2 pass for lexical and for bge-small. A confidence-signal experiment
on the timesplit negatives should use this positive arm. Every number is in
`results/timesplit-positive.json`, written by
`python -m mathgraph.timesplit pos-report`.

| system | T1 leaks | correct top-1 positives, fit / eval half | recall@1 | pass |
|---|---|---|---|---|
| lexical, 10-fold cross-fitted PMI | 0 positives scored by a table holding their docstring | 1,267 / 1,340 | 2,607 / 20,667 = 12.6% [12.2, 13.1] | yes |
| bge-small, `name. head` for every row | 0 rows whose text holds their docstring | 2,051 / 2,066 | 4,117 / 20,667 = 19.9% [19.4, 20.5] | yes |

For comparison, hctz had 127 correct top-1 positives in total for lexical and
65 for bge. Both T1 counts are mechanical checks of the construction, so 0 is
what the code guarantees and the check confirms it.

## Descriptive (pre-registered, not gated)

The table gives the AUROC of the raw top-1 score, correct positives against
each whole negative arm. The hctz rows are computed by the same function on
the hctz files.

| system | vs holdout | vs deletion | vs time |
|---|---|---|---|
| bge-small, rebuilt | **0.674** | **0.675** | 0.800 |
| bge-small, hctz | 0.375 | 0.364 | 0.700 |
| lexical, rebuilt | 0.583 | 0.596 | 0.637 |
| lexical, hctz | 0.576 | 0.585 | 0.623 |

- **bge.** The AUROC below 0.5 was the construction artefact. With one text
  recipe for every row it is 0.67 against both in-library controls.
- **Lexical** barely moves. Its rows never held docstrings, so the rebuild
  adds positives and changes no row.
- **Median content words per query.** Positive 6, time 7, holdout 6,
  deletion 6.
- **Median `name. head` length in characters.**
  - Correct positives' gold rows: 172.
  - Top-1 rows of the negative arms: time 126, holdout 138.5, deletion 140.
  - The post hoc section explains the gap.

## Post hoc (not pre-registered)

- **The length gap comes from selection, not construction.**
  - Every positive's gold row has a median of 173 characters, against 128
    for all rows. The arm is drawn from docstring-bearing source theorems,
    and their heads are long.
  - When a top-1 is wrong, its length is about the same in every arm:
    - incorrect positives: 137;
    - negatives with to_additive twins excluded: 126 to 141.
  - Within correct positives and within holdout, length barely tracks score
    (Spearman 0.03 and 0.06).
- **Self-mentions.**
  - 243 of 20,667 positive docstrings (1.2%) name their own declaration in
    backticks. For the negative arms the count is 18 (time), 19 (holdout)
    and 15 (deletion) of about 1,600 each.
  - For a positive, a self-mention leaks through the name that opens its gold
    row's text. bge recall@1 is 81/243 on these queries, against
    4,036/20,424 on the rest.
  - Lexical drops inline code, so it does not see the name (9/243).
  - Dropping these queries moves bge's AUROC against holdout from 0.674 to
    0.670.
  - The arm keeps them, as pre-registered. A later experiment can drop them:
    a backticked span equal to the name, equal to its last component, or
    ending in `.` followed by that component.
- **to_additive twins** (name-only text) are under 1% of top-1 rows in every
  arm.

## Decisions

1. **Comparable dense text means no row has a docstring**, rather than the
   gold keeping one.
   - A docstring query cannot be a leak-free positive against a corpus that
     holds its own docstring.
   - Stripping only the gold, as hctz did, is exactly the artefact.
   - Lexical needed no change here, because its rows hold name, module and
     type tokens only.
2. **The dense system measured here is bge over `name. head`**, not the
   shipped `doc_text` corpus (`bench_pretrained`), which includes docstrings.
   For the 180,095 of 244,361 control rows without a docstring the two texts
   are identical. So this is the case most golds are in anyway.
3. **Cross-fitting replaces the single 6% PMI holdout.** Each table sees 90%
   of the control docstrings. hctz's table saw 94%.
4. **Device.** bge ran on MPS for the corpus and the queries alike. hctz ran
   on CPU to match its cache. The new corpus cache is
   `emb_BAAI__bge-small-en-v1.5.npy` in the output directory, row-aligned
   with that directory's `idx_ctrl`.
5. **`PYTHONHASHSEED=0` for every stage.**
   - `index.translation()` is `index.build`'s PMI block, factored out
     unchanged. It orders exactly tied entries by set iteration.
   - Recomputing hctz's control table from its rows and PMI holdouts gives
     the stored table except for the order of ties in 12 of 2,743 words.
   - With `expand_k=8`, a tie that straddles rank 8 can change a query's
     expansion, so the seed is pinned. This is filed as mathgraph-gno.
6. **`run_dense` now shares `row_text` and `_top2` with the new stage.** The
   arithmetic is the same, and the hctz numbers were not rerun.

## Compute

- Lexical: 21.8 min wall, 725 s CPU, 1.1 GB peak.
- Dense: 18.6 min wall, of which 14.5 min was corpus embedding on MPS. 141 s
  CPU, 1.5 GB peak.
- The machine's load average was about 20 throughout.

## Data

The output is in `mathgraph-data/timesplit-xfit/` in the main checkout
(gitignored). The directory is self-contained:

- `idx_ctrl/`, copied from hctz (sha256 in `arms_meta.json`);
- `arms.jsonl` (every query carries its fold);
- `lexical.jsonl`, `dense.jsonl`, `emb_BAAI__bge-small-en-v1.5.npy`;
- `hctz_lexical.jsonl`, `hctz_dense.jsonl` (the before column).

To rescore a lexical query, rebuild its fold's table with
`PYTHONHASHSEED=0`:
`translation(rows, {id(rows[i]) for i, g in pmi_folds(rows).items() if g == fold})`.

## Not done

- **Arm M** is still 27 queries. This is filed as mathgraph-em8.
- **The time arm's kill test** has not been rerun on the docstring-free dense
  corpus. Its hctz verdict holds for the docstring corpus only.

## Test run

- `MATHGRAPH_DATA=<main checkout>/mathgraph-data uv run pytest -q` printed
  `102 passed in 883.22s (0:14:43)`. That includes the 2 new tests in
  `tests/test_timesplit.py`: a withheld docstring teaches the PMI table
  nothing, and the AUROC counts ties as half.
- A one-line change was made after that run: `arms_meta.json` no longer
  records the source path, which kept a home directory out of the results
  JSON. `pos-arms` was then rerun and `arms.jsonl` came out byte-identical.
  `pytest -q tests/test_timesplit.py` was rerun and printed `6 passed`.

## Reproduce

```bash
export MATHGRAPH_DATA=/path/to/mathgraph-data PYTHONHASHSEED=0
SRC=/path/to/hctz/mathgraph-data/timesplit    # idx_ctrl/, arms.jsonl, lexical.jsonl, dense.jsonl
uv run python -m mathgraph.timesplit pos-arms --src $SRC
uv run python -m mathgraph.timesplit pos-lexical
# a worktree venv with sentence-transformers 6.3.0, torch 2.15.0, transformers 5.23.0
HF_HUB_OFFLINE=1 build/venv-dense/bin/python -m mathgraph.timesplit pos-dense
uv run python -m mathgraph.timesplit pos-report
```

Outputs go to `./mathgraph-data/timesplit-xfit` and
`results/timesplit-positive.json` by default.
