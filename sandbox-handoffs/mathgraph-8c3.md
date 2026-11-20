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

## Results (run 2026-11-20, after the registration commit 083c0a7)

### Verdict: KILLED

K2 and K3 fire, and K1 passes. The verdict is the same under every reading
registered above:

- the point AUROC is also below 0.65;
- neither named confidence passes both K2 and K3.

| criterion | threshold | measured | verdict |
|---|---|---|---|
| K1 positives | ≥ 150 statement events | 307 | pass |
| K1 negatives | ≥ 150 events from ≥ 40 commits | 393 from 140 commits | pass |
| K2 AUROC of the best named confidence (`cos`) | 95% lower bound ≥ 0.65 | 0.625 [0.552, 0.693] | **kill** (point 0.625 also < 0.65) |
| K3 non-pfr precision at τ frozen on pfr (`cos`) | Wilson lower bound ≥ 50% | 40/146 = 27.4% [20.8, 35.1] | **kill** |

The other named confidence, `z`, fails both checks as well: AUROC 0.494
[0.403, 0.581], and transfer precision 34/102 = 33.3% [24.9, 42.9].

### The benchmark

- **Size.** 700 statement events from the six projects: 307 positive and 393
  negative (363 'same', 30 'later').
- **Dates.** From 2022-05-18 to 2026-09-30. By year: 2022 34, 2023 168, 2024
  405, 2025 86, 2026 7.
- **Reproducible extraction.** The tag additions agree exactly with the
  round-2 `ev.py` rows: 1,549 of 1,549, project by project.

| project | positive | negative | tag outcomes (pre / same / later / never; drops) |
|---|---|---|---|
| FLT | 66 | 64 | 65 / 56 / 7 / 30; renames 147, mathlib 17, repeat 21, no block 6, not ident 5 |
| LeanAPAP | 13 | 15 | 13 / 14 / 1 / 2; renames 27, mathlib 1 |
| carleson | 30 | 52 | 36 / 66 / 1 / 5; renames 145, mathlib 10, repeat 5, no block 1, not ident 11 |
| con-nf | 39 | 39 | 40 / 41 / 0 / 40; renames 52, repeat 2 |
| equational_theories | 76 | 62 | 85 / 74 / 5 / 25; renames 41, mathlib 1, repeat 5, not ident 1 |
| pfr | 83 | 161 | 86 / 155 / 19 / 45; renames 106, mathlib 9, repeat 8, not ident 17 |

- **Rename filter.** "renames" means `commit_removes_decls`. It removes 518 of
  the 1,549 additions, a third.
- **Statement drops.** No positive lost its gold to `gold_tagged_at_parent`.
- **Mixed blocks.** 3 positive blocks also carry same/later tags.

### Metrics

| confidence | AUROC pos vs neg [bootstrap 95%] | in-sample P@10% (70 of 700 answered) | τ frozen on pfr: non-pfr coverage, precision [Wilson] [bootstrap] |
|---|---|---|---|
| `cos` (named) | 0.625 [0.552, 0.693] | 27/70 = 38.6% [28.1, 50.3] | 32.0%; 27.4% [20.8, 35.1] [17.8, 38.0] |
| `z` (named) | 0.494 [0.403, 0.581] | 24/70 = 34.3% [24.3, 46.0] | 22.4%; 33.3% [24.9, 42.9] [22.3, 45.6] |
| per-query z (exploratory) | 0.500 [0.404, 0.602] | 38.6% | – |
| top-1 minus top-2 margin (exploratory) | 0.571 [0.508, 0.630] | 42/70 = 60.0% [48.3, 70.7] | – |
| lexical coverage (exploratory) | 0.517 [0.434, 0.591] | 22/70 = 31.4% [21.8, 43.0] | – |

The τ frozen on pfr at 10% coverage (cos 0.737, z 0.958) does not transfer.
It answers 32% (cos) and 22% (z) of the other projects' events instead of 10%.
This is the known risk from the soft-ranker probe. The pre-registered z did not
cure it.

### Secondary analyses (named, non-gating)

- **Ranking over positives.**
  - bge: r@1 124/307 = 40.4% [35.1, 46.0]; r@5 54.4% [48.8, 59.9].
  - lexical: r@1 26.7% [22.1, 31.9]; r@5 42.7%.
  - bge r@1 by project: carleson 23/30, equational_theories 45/76, FLT 19/66,
    con-nf 11/39, LeanAPAP 4/13, pfr 22/83.
- **Per-project AUROC, `cos`.**
  - carleson 0.847 [0.681, 0.933]
  - LeanAPAP 0.805 [0.683, 0.958]
  - FLT 0.684 [0.508, 0.812]
  - con-nf 0.626 [0.465, 0.777]
  - pfr 0.625 [0.534, 0.720]
  - equational_theories 0.438 [0.236, 0.621]

  Median candidate counts run from about 450 to 2,400 per snapshot, except
  equational_theories at 11,782. That makes top-1 cosines high for everything,
  and its negatives (median 0.717) outscore its positives (0.708).
- **Per-project AUROC, `z`.**
  - carleson 0.919 [0.849, 0.969]
  - con-nf 0.630
  - FLT 0.617
  - LeanAPAP, equational_theories and pfr 0.34 each
- **Undefined z.** z is undefined, and so −∞, for 135 events, at snapshots
  with fewer than 5 untagged statements. 88 of them are positives (pfr 50,
  equational_theories 28). Exploratory: on the 565 events where z is defined,
  z scores 0.624 and cos 0.644. So the fallback rule costs z most of its
  pooled AUROC, but z does not beat raw cosine even where it exists.
- **Rename sensitivity.** Keeping only the 373 negatives whose short name is
  also absent at the parent gives cos 0.635 and z 0.498. Rename noise does not
  explain the result.
- **'same' vs 'later'.** Positives against 'same'-only negatives: cos 0.625.
  Against 'later'-only: 0.630.

### Exploratory only

- **Margin.** Top-1 minus top-2 separates correct top-1 answers from everything
  else at AUROC 0.739, against 0.694 for `cos`. It reaches 60% in-sample
  P@10%. This is a lead for a separately pre-registered test, not a result.
- **Name in query.** 85 of 307 positive queries contain a gold short name of 6+
  characters (punctuation stripped). This is an upper bound. It counts ordinary
  words such as `entropy` that happen to be lemma names.

### What the numbers support and what they do not

1. **The benchmark exists.** It is dated, reproducible and has real abstention
   negatives: 700 statement events, 2022–2026, six projects.
2. **A project-wide bge suggester is a usable shortlist, not a decider.** It
   ranks the right declaration first for 40% of already-formalized statements,
   and in the top 5 for 54%. But its confidence cannot tell "already formalized"
   from "not yet" (AUROC 0.63). Neither named confidence's pfr-frozen
   threshold gives more than 33% precision elsewhere. The registered bar was a
   50% lower bound.
3. **Calibration does not transfer between projects.** The z-score normaliser
   did not fix this. The "first dated precision-at-coverage number" for
   blueprint `\lean` completion is therefore 27.4% [20.8, 35.1] at τ frozen on
   pfr.
4. **Not tested here.** The 'N1 helps' sub-claim was excluded as registered;
   it waits for ydf.

### Deviations after registration

None in the protocol. Two code changes after the run cannot move any number:

- the `ev.py` rows lookup also accepts `hr/`, the durable copy's name;
- the embedding cache moved to the repo's `build/replay/`.

### Reproduce

The run took about 23 minutes on the M-series laptop. It used a worktree venv
with sentence-transformers 6.3.0, transformers 5.23.0 and torch 2.15.0, plus
pytest. bge ran from the local HF cache. The embedding cache peaked at 117 MB
and was deleted afterwards. Inputs are the durable, byte-identical copy of the
round-2 clones:

```bash
HF_HUB_OFFLINE=1 MATHGRAPH_DATA=/Users/benjaminhess/Downloads/mathgraph/mathgraph-data \
  python -m mathgraph.replay $MATHGRAPH_DATA/r2/clones results/replay.json
```

### Open questions

1. **Pre-register the margin as its next confidence?** It was the strongest
   signal here: selective AUROC 0.74, in-sample P@10% 60%. Test it with
   leave-one-project-out thresholds.
2. **Should z normalise over a pool that survives late snapshots?** Late
   snapshots have few untagged statements. Options: past snapshots, or all
   statements. That needs its own registration.
