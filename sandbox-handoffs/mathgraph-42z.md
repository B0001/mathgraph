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
