# mathgraph-8c3 handoff: history-replay `\lean` suggester benchmark

City mirror bead `portfolio-vow8`, branch `sandbox/portfolio-vow8` (from
`origin/sandbox/portfolio-qs9g` at 4083590). Code: `mathgraph/replay.py`.
Test: `tests/test_replay.py`. Numbers: `results/replay.json`.

## Bead

Replay each blueprint's git history. At the parent of every commit that adds
`\lean{X}`, ask a project-wide ranker for a suggestion for that statement.

- If X already existed at the parent ('pre'), the event is a positive.
- If X did not exist yet ('same': it appears in the commit itself; 'later': it
  appears after the commit), the event is a real "not formalized yet" negative.
  The ranker should abstain on it.

The result is the first dated precision-at-coverage number for blueprint
`\lean` completion.

## Pre-registration

Written and committed before any ranker was run on any replay event. The only
numbers known at the time were the raw `ev.py` short-name label counts from the
bead and the round-2 synthesis:

| | pre | same | later | never |
|---|---|---|---|---|
| tags | 570 | 764 | 48 | 167 |

Dropping commits where `ev.py` saw a removed short name leaves 445 pre, 433
same and 41 later. No AUROC, precision or ranking figure on these events
existed when this section was committed. Any later change is listed under
"Deviations after registration", and this text stays as committed.

### Data

- **Projects.** The six leanblueprint repositories, as full (non-shallow)
  clones. They are mirrored into `build/replay/clones/` (gitignored) from the
  round-2 scratchpad, with HEADs:
  - carleson f7487cc
  - con-nf edbce7e
  - equational_theories dbc9a2bf
  - FLT 01980581
  - LeanAPAP fb5cb9c
  - pfr 1ef23c3
- **Mathlib names** for the mathlib filter: the rows of `idx_mathlib`, which
  include to_additive twins (mathlib pin b44f89d, 2026-07-26).
- **Encoder.** `BAAI/bge-small-en-v1.5` from the local HF cache, with
  `HF_HUB_OFFLINE=1`.

### Events

1. **Additions.** Walk `git log --reverse -p -- blueprint/src` per project, as
   `ev.py` does. A commit C with parent P adds tag X if `\lean{..X..}` occurs on
   an added diff line of C and not on a removed one. Merge commits carry no diff
   here and so contribute nothing.
2. **Declarations at a snapshot.** Run `leanscan` over every `.lean` blob of the
   snapshot, skipping `.lake/` and `lake-packages/`. Names are
   fully qualified. The prefix up to `_root_.` is cut, so
   `A._root_.foo` becomes `foo`. F(P), F(C) and F(H) are the name sets at P, at
   C, and at the clone HEAD H.
3. **Tag labels.** These use full names, not short names:
   - pre if X ∈ F(P);
   - same if X ∈ F(C) \ F(P);
   - later if X ∈ F(H) \ (F(P) ∪ F(C));
   - never otherwise.
4. **Tag drops.** Each dropped tag is counted under the first reason that
   applies, in this order:
   1. `repeat`: X already had an addition earlier in the same project. Only a
      tag's first addition is an event.
   2. `not_identifier`: X does not fully match leanscan's identifier pattern.
   3. `mathlib_name`: X names a mathlib declaration.
   4. `commit_removes_decls`: F(P) \ F(C) is non-empty, so C deletes or renames
      a project declaration. Every tag of C is dropped.
   5. `no_statement_block`: X is in no theorem or definition block of the
      `.tex` files C touches, as parsed by `latex.parse` at C.
   6. `never`.
5. **Unit of analysis: the statement event.** A statement event is a
   theorem/definition block at C that gains surviving tags in C.
   - It is **positive** if at least one of its surviving tags is pre. Its gold
     is those pre tags.
   - It is **negative** otherwise, when all its surviving tags are same or
     later.
   - Blocks that mix pre with same/later tags are positive, and are counted
     separately.
6. **Gold must be rankable.** Candidates exclude declarations already tagged at
   P, so gold is reduced to pre tags not tagged anywhere in `blueprint/` at P. A
   positive whose gold becomes empty is dropped (`gold_tagged_at_parent`).

### Query, candidates and rankers

- **Query.** The block's title and text at C, from `latex.parse`. This text
  already has `\lean`, `\uses`, `\label` and the `\ref` targets stripped. bge
  takes the bge v1.5 query prefix plus `title. text`. Lexical takes
  `query_weights(text, title=title)`.
- **Candidates at P.** Every leanscan declaration at P, deduplicated by name,
  minus every name tagged anywhere in `blueprint/` at P ("untagged-eligible").
- **bge.** Candidates are embedded as `name. head`, with no docstring, as in
  `complete.py`.
  - Score: cosine. Top-1: argmax over candidates.
  - Embeddings are cached by text hash, so each snapshot is incremental.
- **lexical.** `index.build` over the snapshot's candidate rows, with `attrs`
  blanked so that no to_additive twins enter the index.
  - The PMI table is swapped for `idx_mathlib`'s, so no project docstring
    trains it.
  - Ranker: `Aligner(**LEX)`. Score: the normalised score. Confidence:
    coverage, as in `complete.py`.
  - It abstains when nothing is hit.
- No Refs/N1 and no `\uses` neighbourhoods. That sub-claim waits for ydf.

### Confidences, named before the run

- **`cos`**: bge's raw top-1 cosine.
- **`z`**: a project-normalised z-score, `(cos − μ_P) / σ_P`.
  - μ_P and σ_P are the mean and sample SD of the bge top-1 cosines of P's own
    untagged statement nodes. These are the theorem/definition blocks under
    `blueprint/` at P with no `\lean` tag.
  - Each node is ranked against the same candidate set. So z needs nothing that
    is not available at inference time.
  - If P has fewer than 5 untagged statements, z is undefined for its events.
    They then get confidence −∞: they are never answered and they sort last.

### Metrics

- **Correctness.** An answered positive is correct if its top-1 is in gold. An
  answered negative is always wrong.
- **AUROC.** For confidence c, the Mann-Whitney AUROC of positives against
  negatives, pooled over the six projects, with ties counting ½.
- **Transfer P@10%.** τ_c is the threshold that answers the top ⌈0.10·N_pfr⌉
  pfr events by c.
  - Ties use the `precision_at_coverage` rule: a tie group straddling the cut is
    left out.
  - The lowest answered pfr value is then applied to the pooled non-pfr
    events: answer iff c ≥ that value.
  - Reported as precision with a Wilson 95% interval, plus the achieved
    non-pfr coverage. If nothing is answered, the lower bound is 0.
- **Bootstrap.** CIs come from a commit-cluster bootstrap.
  - Clusters are the commits C. Resampling is stratified by project.
  - 2,000 replicates, seed 20261120, percentile 95% interval.
  - For transfer precision, τ is refitted inside each replicate on that
    replicate's pfr events.
  - Replicates without both classes are skipped and counted.

### Kill test

KILL if any of K1–K3 fires, under the primary readings.

- **K1, counts.** Fewer than 150 positive statement events, or fewer than 150
  negative statement events, or negatives from fewer than 40 distinct commits.
- **K2, AUROC.** "Best" is whichever of `cos` and `z` has the higher point
  AUROC.
  - Primary: KILL if its bootstrap 2.5th percentile is below 0.65. This
    mirrors the lower-bound reading of K3.
  - Secondary reading, reported but not the verdict: the point estimate below
    0.65.
- **K3, transfer.** For the same best confidence, KILL if the pooled non-pfr
  precision at τ frozen on pfr has a Wilson 95% lower bound below 50%.
  - Secondary reading: survive if either named confidence passes both the
    primary K2 and K3.

### Secondary analyses (named now, non-gating)

1. r@1 and r@5 over positives, for bge and lexical.
2. Per-project AUROC with bootstrap CIs.
3. In-sample pooled P@10% for `cos`, `z` and lexical coverage.
4. Sensitivity: keep only negatives whose short name is also absent at P.
   These guard against later renames.
5. Tag-level counts with every drop reason, and agreement with the `ev.py`
   rows on (name, commit).
6. AUROC for 'same' negatives against 'later' negatives, each against all
   positives.

### Exploratory only

None of these enters any verdict:

- per-query z over the candidate cosines;
- the top-1 minus top-2 margin;
- lexical coverage as a confidence;
- whether the gold short name occurs in the query text.

### Departures from the bead text, decided before the run

1. **Statement events, not tag events.** The ranker answers once per
   statement, and tag events would repeat the query. K1 counts statement
   events, which can only be fewer, so K1 is applied strictly.
2. **Full names, not short names.** A positive needs its exact gold among the
   candidates.
3. **The rename filter compares full name sets.** It also catches namespace
   moves.
4. **The z reading.** "Project-normalised, computed over that snapshot's
   untagged nodes" is read as normalising by the snapshot's untagged
   blueprint statements. The per-query alternative is exploratory only.
5. **Strict K2 reading.** The point reading is reported next to it.
6. **Lexical IDF.** Historical snapshots are in no prebuilt index, so lexical
   IDF comes from the snapshot's own declarations.
7. **Two extra drops:** first additions only, and `gold_tagged_at_parent`.

### Known risks

- **Squash-merged commits.** These add many statements and declarations at
  once and become clusters of 'same' negatives. The cluster bootstrap carries
  that dependence.
- **Scanner misses.** Declarations leanscan cannot see, such as macro-generated
  ones and some `mutual` blocks, label as 'never' and are dropped.
- **Statement text written at C.** It may echo the Lean name. The exploratory
  leakage check counts how often.
- **Uneven project sizes.** equational_theories has generated files with
  thousands of lemmas. bge's cosine scale differs by project, which is why `z`
  exists.
- **Compute.** Expected under an hour. A run over about two hours would be cut
  to a smaller configuration, and recorded as such.
