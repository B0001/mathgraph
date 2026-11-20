# mathgraph-fxh handoff: neighbour-anchored blueprint `\lean` completion

## Bead

Hide a blueprint statement's `\lean` tag. Use the gold tags of its `\uses`
neighbours as anchors. Restrict candidates to the anchors' 1-hop Lean-reference
neighbourhood N1 and rank inside it. An empty or flat N1 abstains. In-project
only. First experiment: extend the pilot to a full leave-one-out over the 6
blueprints, with three rankers inside N1 (graph-only link count, lexical,
bge-small without docstrings), fresh global baselines on the same statements,
results split by edge direction, a hand check of reference extraction on 50
bodies, and r@1 and precision at 10% coverage with Wilson intervals.

Pre-registered kill test: kill if the Wilson lower bound on gold-in-N1 is below
60%, if median |N1| is above 300, or if the within-set ranker fails to beat the
graph-only baseline on r@1 and on precision at 10% coverage. Separately, kill
the realistic-use claim if the upstream-only direction gives gold-in-N1 below
40%.

Code: `mathgraph/complete.py` (the promoted pilot). Test:
`NeighbourAnchoredCompletion` in `tests/test_units.py`. Numbers:
`sandbox-handoffs/mathgraph-fxh.json`, which is the script's stdout.

## Verdict: not killed

| criterion | threshold | measured (614 anchored statements) | verdict |
|---|---|---|---|
| gold in N1 | Wilson lower bound ≥ 60% | 477/614 = 77.7% [74.2, 80.8] | pass |
| median \|N1\| | ≤ 300 | 39.5 (41 over non-empty N1) | pass |
| text ranker in N1 beats graph-only on r@1 **and** P@10% | both point estimates higher | lexical 31.6% vs 11.9%, 66.1% vs 26.2%; bge 30.1% vs 11.9%, 79.0% vs 26.2% | pass |
| realistic use: upstream-only gold in N1 | ≥ 40% | 329/496 = 66.3% [62.1, 70.3] | pass |

Reading of criterion 3: a text ranker survives only if it beats graph-only on
both metrics. Both rankers do, so the weaker reading ("on either") gives the
same verdict. Paired tests: lexical +170/−49 statements against graph,
p = 8e-17; bge +170/−58, p = 6e-14. The upstream rate has statements with at
least one upstream anchor as its denominator. Counted over all 614 anchored
statements it is 329/614 = 53.6% [49.6, 57.5], which still clears 40%.

The verdict also survives a stricter reference matcher (see the hand check).

### What the numbers do not support

1. **Most of the gain over the global baselines comes from restricting to the
   project, not to N1.** Ranking over the project's own declarations already
   lifts r@1 from 17.3% to 26.7% (lexical) and from 21.0% to 26.2% (bge). N1
   adds a significant further gain only on PFR (lexical +25/−5, bge +23/−3).
   On the other five projects it is a wash: lexical +40/−30, p = 0.28; bge
   +41/−37, p = 0.73. On carleson, bge over the project (66.9%) beats bge in N1
   (54.8%), because 31% of carleson's golds are not in N1. TheoremGraph-style
   project restriction is therefore the baseline this idea has to beat. Outside
   PFR it does not beat it.
2. **On PFR, neither text ranker beats graph-only on r@1.** PFR is the held-out
   project for the lexical weights. Lexical scores +46/−37 (p = 0.38) and bge
   +35/−44 (p = 0.37). The pooled win over graph comes from the other projects,
   where graph ties and abstains on 328 of 413 statements.
3. **Upstream direction (the realistic case):** gold clears the 40% bar, but at
   10% coverage the text rankers inside N_up (60.0%) do not beat graph-only
   (62.0%). Bge over the whole project reaches 74.0% there.
4. **Reference extraction is noisy.** Only 39.5% of extracted references are
   genuine (hand check below). So the graph-only baseline is measured on a
   noisy graph, and its numbers are a floor rather than a fair estimate of
   edge consistency.

## What was run

- **Corpus.** The 6 leanblueprint checkouts under `mathgraph-data/blueprints`:
  FLT, LeanAPAP, carleson, con-nf, equational_theories, pfr. Declarations come
  from `blueprint_decls.jsonl` + `pfr.jsonl` (25,566; 25,562 with a located
  body).
- **Statements.** Theorem and definition blocks under `<project>/blueprint/`
  with a `\lean` tag.
  - 650 of them name a declaration of the project's own Lean source (in scope).
  - 614 have at least one anchor; every table below uses these.
  - 36 have no anchor and always abstain (FLT 7, LeanAPAP 1,
    equational_theories 28).
  - A statement with several tags counts as found when any in-project tag is in
    the set or ranked first. 70 of the 614 have more than one.
- **Anchors.** Upstream anchors are the tags of the statements this one
  `\uses`; a proof's `\uses` count for its statement. Downstream anchors are
  the tags of the statements that `\uses` this one. The hidden statement's own
  tags are never anchors.
- **Bodies and references.** A declaration's body is its source lines up to the
  next scanned declaration of its module. The pilot's matcher is kept: a body
  mentions every declaration whose last name component equals the last
  component of one of its identifiers. Only anchors with a body in the project
  expand.
- **Candidate sets.**
  - `n1`: declarations linked to any anchor, either direction.
  - `up`: declarations whose body cites an upstream anchor.
  - `down`: declarations an anchor's body cites, for downstream anchors.
  - `project`: every declaration of the project.
  - `global`: mathlib plus the project.
  - Anchors are never candidates.
  - Median sizes: n1 39.5, up 8, down 17. 21 statements have an empty N1.
- **Rankers.**
  - **graph:** the number of anchors a candidate is linked to. Confidence is
    the count, plus the lead over the runner-up divided by (anchors + 1).
  - **lexical:** the shipped `Aligner` with `cli.LEX` weights, over idx_full
    (PFR) or idx_blueprint (the rest). Its PMI table is swapped for
    idx_mathlib's, so no project docstring trains it (the mathgraph-dem.1 leak).
    Confidence is the top candidate's share of the query's evidence mass.
  - **bge-small-en-v1.5:** the query is the bge retrieval prefix plus title and
    text. Project rows are embedded as name and head, with no docstring
    (dem.1). Mathlib rows reuse bench_pretrained's cached name+doc+head
    embeddings. Confidence is the top-1 cosine.
  - Every ranker abstains on an empty set or a tie at the top. Lexical also
    abstains when nothing scores above 0.
- **Metrics.**
  - r@1 is over every statement in the population; an abstention is a miss.
  - P@10% answers the most confident ceil(10% · N) statements
    (`bench_pretrained.precision_at_coverage`; a tie group straddling the cut
    is left out).
  - Intervals are Wilson 95%.
  - Paired tests are exact two-sided sign tests on discordant statements. `+a/−b`
    means the first system is right and the second wrong on `a` statements, and
    the reverse on `b`.
- Because of the PMI swap, the lexical numbers are not comparable to README's
  18.2% PFR present-arm figure.

## Results

### All projects, both directions (n1)

N = 614. Gold in N1: 477/614 = 77.7% [74.2, 80.8]. Median |N1| 39.5 (41 when
non-empty).

| ranker / candidates | answered | r@1 | r@1 95% | P@10% | P@10% 95% |
|---|---|---|---|---|---|
| graph/n1 | 187 | 73/614 = 11.9% | [9.6, 14.7] | 16/61 = 26.2% | [16.8, 38.4] |
| lexical/n1 | 560 | 194/614 = 31.6% | [28.0, 35.4] | 41/62 = 66.1% | [53.7, 76.7] |
| bge/n1 | 593 | 185/614 = 30.1% | [26.6, 33.9] | 49/62 = 79.0% | [67.4, 87.3] |
| lexical/project | 559 | 164/614 = 26.7% | [23.4, 30.3] | 34/62 = 54.8% | [42.5, 66.6] |
| bge/project | 614 | 161/614 = 26.2% | [22.9, 29.8] | 48/62 = 77.4% | [65.6, 86.0] |
| lexical/global | 542 | 106/614 = 17.3% | [14.5, 20.4] | 18/62 = 29.0% | [19.2, 41.3] |
| bge/global | 614 | 129/614 = 21.0% | [18.0, 24.4] | 40/62 = 64.5% | [52.1, 75.3] |

### Upstream only: the statement's own body cites an anchor it `\uses`

N = 496 statements with at least one upstream anchor. Gold in N_up:
329/496 = 66.3% [62.1, 70.3]. Median |N_up| 8 (9 when non-empty).

| ranker / candidates | answered | r@1 | r@1 95% | P@10% | P@10% 95% |
|---|---|---|---|---|---|
| graph/up | 149 | 96/496 = 19.4% | [16.1, 23.1] | 31/50 = 62.0% | [48.1, 74.1] |
| lexical/up | 424 | 161/496 = 32.5% | [28.5, 36.7] | 30/50 = 60.0% | [46.2, 72.4] |
| bge/up | 456 | 155/496 = 31.2% | [27.3, 35.5] | 30/50 = 60.0% | [46.2, 72.4] |
| lexical/project | 448 | 116/496 = 23.4% | [19.9, 27.3] | 22/50 = 44.0% | [31.2, 57.7] |
| bge/project | 496 | 118/496 = 23.8% | [20.2, 27.7] | 37/50 = 74.0% | [60.5, 84.1] |
| lexical/global | 432 | 78/496 = 15.7% | [12.8, 19.2] | 12/50 = 24.0% | [14.3, 37.4] |
| bge/global | 496 | 96/496 = 19.4% | [16.1, 23.1] | 31/50 = 62.0% | [48.1, 74.1] |

### Downstream only: an anchor that `\uses` the statement cites it

N = 524 statements with at least one downstream anchor. Gold in N_down:
325/524 = 62.0% [57.8, 66.1]. Median |N_down| 17.

| ranker / candidates | answered | r@1 | r@1 95% | P@10% | P@10% 95% |
|---|---|---|---|---|---|
| graph/down | 63 | 23/524 = 4.4% | [2.9, 6.5] | 19/53 = 35.9% | [24.3, 49.3] |
| lexical/down | 492 | 181/524 = 34.5% | [30.6, 38.7] | 37/53 = 69.8% | [56.5, 80.5] |
| bge/down | 508 | 144/524 = 27.5% | [23.8, 31.5] | 41/53 = 77.4% | [64.5, 86.6] |
| lexical/project | 475 | 152/524 = 29.0% | [25.3, 33.0] | 33/53 = 62.3% | [48.8, 74.1] |
| bge/project | 524 | 151/524 = 28.8% | [25.1, 32.8] | 41/53 = 77.4% | [64.5, 86.6] |
| lexical/global | 459 | 100/524 = 19.1% | [16.0, 22.7] | 22/53 = 41.5% | [29.3, 54.9] |
| bge/global | 524 | 123/524 = 23.5% | [20.1, 27.3] | 35/53 = 66.0% | [52.6, 77.3] |

### PFR only (held out from the lexical weights' fit)

The n1 split. N = 201. Gold in N1: 185/201 = 92.0% [87.5, 95.0]. Median |N1| 40.

| ranker / candidates | answered | r@1 | r@1 95% | P@10% | P@10% 95% |
|---|---|---|---|---|---|
| graph/n1 | 102 | 54/201 = 26.9% | [21.2, 33.4] | 9/21 = 42.9% | [24.5, 63.4] |
| lexical/n1 | 192 | 63/201 = 31.3% | [25.3, 38.1] | 14/21 = 66.7% | [45.4, 82.8] |
| bge/n1 | 201 | 45/201 = 22.4% | [17.2, 28.6] | 9/21 = 42.9% | [24.5, 63.4] |
| lexical/project | 183 | 43/201 = 21.4% | [16.3, 27.6] | 10/20 = 50.0% | [29.9, 70.1] |
| bge/project | 201 | 25/201 = 12.4% | [8.6, 17.7] | 6/21 = 28.6% | [13.8, 50.0] |
| lexical/global | 178 | 28/201 = 13.9% | [9.8, 19.4] | 6/21 = 28.6% | [13.8, 50.0] |
| bge/global | 201 | 13/201 = 6.5% | [3.8, 10.8] | 1/21 = 4.8% | [0.9, 22.7] |

PFR up/down splits:
- **Upstream (N = 183):** gold 144/183 = 78.7% [72.2, 84.0]. r@1 is graph 27.9%,
  lexical 37.7%, bge 31.7%. P@10% is graph 12/19, lexical 11/19, bge 11/19.
- **Downstream (N = 182):** gold 147/182 = 80.8% [74.4, 85.8]. r@1 is graph
  6.6%, lexical 41.8%, bge 26.4%.
- All splits are in the JSON.

bge/global on PFR (6.5%) agrees with dem.1's finding: with PFR docstrings
removed, bge-small's published 26.1% falls to about 5%.

### By project (n1, r@1)

| project | N | gold in N1 | 95% | median \|N1\| | graph | lexical N1 | bge N1 | lexical project | bge project | lexical global | bge global |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FLT | 122 | 92 = 75.4% | [67.1, 82.2] | 38 | 3.3% | 16.4% | 18.9% | 9.8% | 6.6% | 4.1% | 1.6% |
| LeanAPAP | 22 | 17 = 77.3% | [56.6, 89.9] | 15 | 27.3% | 40.9% | 31.8% | 31.8% | 22.7% | 27.3% | 9.1% |
| carleson | 166 | 115 = 69.3% | [61.9, 75.8] | 36.5 | 1.2% | 47.6% | 54.8% | 52.4% | 66.9% | 39.2% | 60.8% |
| con-nf | 53 | 42 = 79.2% | [66.5, 88.0] | 152 | 9.4% | 24.5% | 20.8% | 18.9% | 11.3% | 3.8% | 9.4% |
| equational_theories | 50 | 26 = 52.0% | [38.5, 65.2] | 40 | 4.0% | 20.0% | 16.0% | 10.0% | 12.0% | 0.0% | 12.0% |
| pfr | 201 | 185 = 92.0% | [87.5, 95.0] | 40 | 26.9% | 31.3% | 22.4% | 21.4% | 12.4% | 13.9% | 6.5% |

### Paired comparisons (r@1)

| comparison | pooled n1 (614) | pooled up (496) | pooled down (524) | PFR n1 (201) | non-PFR n1 (413) |
|---|---|---|---|---|---|
| lexical in set vs graph | +170/−49, p=8e-17 | +93/−28, p=2e-9 | +170/−12, p=7e-37 | +46/−37, p=0.38 | +124/−12, p=1e-24 |
| bge in set vs graph | +170/−58, p=6e-14 | +92/−33, p=1e-7 | +137/−16, p=4e-25 | +35/−44, p=0.37 | +135/−14, p=5e-26 |
| lexical: set vs project | +65/−35, p=0.004 | +86/−41, p=8e-5 | +91/−62, p=0.02 | +25/−5, p=3e-4 | +40/−30, p=0.28 |
| bge: set vs project | +64/−40, p=0.02 | +86/−49, p=0.002 | +63/−70, p=0.60 | +23/−3, p=9e-5 | +41/−37, p=0.73 |
| lexical: project vs global | +58/−0 | +38/−0 | +52/−0 | +15/−0 | +43/−0 |
| bge: project vs global | +32/−0 | +22/−0 | +28/−0 | +12/−0 | +20/−0 |
| lexical vs bge, in set | +62/−53, p=0.46 | +45/−39, p=0.59 | +63/−26, p=1e-4 | +36/−18, p=0.02 | +26/−35, p=0.31 |

Outside PFR the upstream gain over the project is not significant either:
lexical +41/−30 (p = 0.24), bge +44/−41 (p = 0.83). Also outside PFR, in the
downstream split, bge in N_down is significantly worse than bge over the
project: +31/−63, p = 0.001. Pooled, that comparison is +63/−70, p = 0.60.

## Hand check of reference extraction (50 bodies)

**Sample.** `random.Random(0).sample(sorted(P), 50)`, where P is the set of 724
gold declarations of the 614 anchored statements. For each body I read the
slice, the next scanned declaration, and every extracted in-project reference
with the lines that produced it.

Slice classes:
- **exact:** the declaration and nothing else but blank lines.
- **spill:** the slice also holds what follows the declaration — the next
  declaration's docstring or attributes, `include`/`variable`/`omit`/`open … in`
  lines, `end`/`section`/`namespace`, comments, anonymous instances, or
  declarations leanscan does not see — but this adds no reference.
- **spill+refs:** the spill adds at least one spurious reference.
- **truncated:** part of the declaration is missing from the slice.

| measure | count | rate [95%] |
|---|---|---|
| slices exact | 8/50 | 16.0% [8.3, 28.5] |
| spill, no reference added | 31/50 | 62.0% |
| spill that adds spurious references | 11/50 | 22.0% [12.8, 35.2] |
| truncated slices | 0/50 | 0.0% [0.0, 7.1] |
| extracted references that are genuine | 275/696 | 39.5% [35.9, 43.2] |
| bodies with at least one spurious reference | 44/50 | 88.0% [76.2, 94.4] |
| spurious references caused by spill | 61/421 | 14.5% [11.4, 18.2] |

References cluster by body, so the per-reference intervals are optimistic.

**Slicing error is bounded.** About one body in five gains spurious references
from spill, and none loses its own text (upper bound 7.1%). Most spurious
references come from the matcher, not the slice:
- namesakes in other namespaces, e.g. `rdist_symm` also matching
  `ProbabilityTheory.Kernel.rdist_symm`, or `.map`, `.trans`, `.symm`, `.comp`,
  `.fst` and `.mk` matching every project declaration with that last component;
- bound variables (`G`, `x`, `k`, `p`, `S`, `f`) matching declarations of that
  name;
- English words in comments and docstrings (`map`, `of`, `entropy`, `prime`);
- 13 declarations whose scanned name ends in `.`, so every token ending in `.`
  matches them.

**Missed references.** The audit did not set out to measure recall, so these
are a lower bound. 11 of the 50 bodies miss a genuine in-project reference,
for three reasons:
- **Undeclared to leanscan:** equational_theories declares its equations with
  `equation 14 := …`, and carleson uses `irreducible_def C7_5_11`. Neither form
  is scanned, so every `EquationN_implies_EquationM` misses both of its
  equations.
- **Unicode truncation:** leanscan cuts names at non-Greek unicode, e.g.
  `rowDecomp_𝔘_eq` → `rowDecomp_`, and `dist_𝓘` becomes a spurious `dist_`.
  This hits carleson hardest, and carleson has the lowest gold-in-N1 after
  equational_theories.
- **Unnamed or indented declarations:** auto-named instances
  (`instFiniteRangeComp`) and lemmas indented inside a `mutual` block are not
  scanned.

**Sensitivity.** I reran the graph criteria with every short name held by more
than one project declaration removed from the matcher, which drops the
namesake class:

| measure | pilot matcher | unique short names only |
|---|---|---|
| gold in N1 | 477/614 = 77.7% [74.2, 80.8] | 443/614 = 72.1% [68.5, 75.5] |
| median \|N1\| | 39.5 | 23 |
| upstream gold in N_up | 329/496 = 66.3% [62.1, 70.3] | 299/496 = 60.3% [55.9, 64.5] |
| graph r@1 | 73/614 (187 answered) | 72/614 (225 answered) |

Every graph criterion still passes. The variant is a scratch subclass, not
shipped: `Refs` with every `named[s]` that holds more than one declaration
deleted from `named` and `mentions`.

**Per body.** Columns are genuine / extracted in-project references.

| # | declaration (project) | lines | slice | refs | note |
|---|---|---|---|---|---|
| 1 | ZHat (FLT) | 31 | spill+refs | 0/25 | anonymous instance and next docstring; bound M, D, f; `Pi.*_apply` vs project `*_apply`; `map` |
| 2 | close_smooth_approx_periodic (carleson) | 21 | exact | 0/6 | `.aestronglyMeasurable`, `convolution`, variable `T` |
| 3 | ConNF.Litter (con-nf) | 12 | spill+refs | 1/6 | instance docstring words `litters`, `type`; `mathlib.` |
| 4 | ProbabilityTheory.exists_isUniform (pfr) | 30 | spill+refs | 3/5 | `map` from the next docstring |
| 5 | ent_sub_zsmul_sub_ent_le (pfr) | 107 | spill | 10/15 | `id`, `.comp`, `Kernel.*` namesakes |
| 6 | dist_of_U_add_le (pfr) | 95 | spill | 10/16 | `Measure.map`, `Kernel.*` namesakes |
| 7 | averaged_construct_good (pfr) | 38 | spill | 5/7 | local `hU`/`hV` match declarations of that name |
| 8 | Subgraph.Equation14_implies_Equation29 (equational_theories) | 5 | spill | 1/19 | `G`, `x`, `.trans`, `.symm`; misses `Equation14`/`29` |
| 9 | diff_rdist_le_4 (pfr) | 9 | spill | 4/8 | `p.hmeas2` matched a private lemma `hmeas2` |
| 10 | TileStructure.Forest.pairwiseDisjoint_rowDecomp (carleson) | 17 | exact | 1/1 | misses `rowDecomp_𝔘_*` (truncated names) |
| 11 | multiDist_of_perm (pfr) | 49 | spill | 2/8 | `.map`, `.pi`, `Kernel.*` |
| 12 | PFR_conjecture_aux (pfr) | 106 | spill | 15/20 | `entropy` from an in-body comment |
| 13 | ent_bsg (pfr) | 125 | spill | 15/30 | `.fst`/`.snd`/`.map`/`.comp`, `Kernel.*` |
| 14 | I3_prop_3_2 (carleson) | 128 | spill+refs | 5/9 | two indented `mutual` lemmas merged in |
| 15 | QHat.rat_join_zHat (FLT) | 26 | spill+refs | 4/10 | `subgroup.` and `of` from the next docstring |
| 16 | I_one_le (pfr) | 36 | spill | 10/11 | |
| 17 | Eq1729.parent (equational_theories) | 2 | exact | 1/8 | `FreeGroup.mk` → five `*.mk`; own short name `parent` |
| 18 | rdist_add_rdist_add_condMutual_eq (pfr) | 23 | spill | 3/4 | |
| 19 | ProbabilityTheory.entropy_comp_le (pfr) | 16 | spill+refs | 4/7 | `entropy` from the next docstring |
| 20 | forest_separation (carleson) | 59 | spill | 16/25 | locals p, p', d, k; `dist_` is truncated `dist_𝓘` |
| 21 | young_convolution (carleson) | 14 | spill | 1/9 | |
| 22 | ordConnected_C (carleson) | 12 | spill | 4/11 | |
| 23 | InfModel.Finite.Equation3994_implies_Equation3588 (equational_theories) | 22 | spill | 1/21 | misses `Equation3994`/`3588` |
| 24 | Subgraph.Equation1571_implies_Equation8 (equational_theories) | 6 | spill | 3/21 | misses `Equation1571`/`8` |
| 25 | Equation1648_not_implies_Equation206 (equational_theories) | 23 | spill | 2/20 | field `op` → eight `*.op`; misses `Equation1648`/`206` |
| 26 | Eq1323.Equation1323_not_implies_Equation2744 (equational_theories) | 22 | spill | 14/42 | namesakes in other `Eq*` namespaces |
| 27 | tile_sum_operator (carleson) | 34 | spill | 8/16 | `Q` is truncated `Qᵣ` |
| 28 | TileStructure.Forest.biUnion_rowDecomp (carleson) | 9 | spill | 3/3 | misses `rowDecomp_𝔘_*` |
| 29 | diff_ent_le_rdist' (pfr) | 7 | spill | 2/3 | |
| 30 | john_nirenberg (carleson) | 46 | spill | 10/22 | `induction`/`zero`/`succ` match declarations |
| 31 | FermatLastTheorem.of_p_ge_5 (FLT) | 22 | spill | 1/8 | comment words `prime`, `integers`, `of` |
| 32 | TileStructure.Forest.lower_oscillation_bound (carleson) | 85 | spill | 16/21 | misses `C7_5_11` (`irreducible_def`) |
| 33 | condRho_sum_le' (pfr) | 27 | spill+refs | 4/6 | `phi` from the next docstring |
| 34 | Subgraph.Equation387_implies_Equation43 (equational_theories) | 8 | spill+refs | 1/14 | `of`, `order` from the next docstring; misses `Equation387`/`43` |
| 35 | pairwiseDisjoint_L0' (carleson) | 3 | spill | 1/2 | misses `𝔏₀'` (not scanned) |
| 36 | rho_continuous (pfr) | 5 | exact | 2/3 | |
| 37 | NumberField.InfiniteAdeleRing.instIsModuleTopology_fLT (FLT) | 10 | spill+refs | 2/25 | module doc and comments: 14 `*.map`, `algebra` |
| 38 | integer_ball_cover (carleson) | 142 | exact | 2/6 | `ball_` is truncated `ball_𝓘` |
| 39 | condRuzsaDist_le (pfr) | 35 | spill | 10/18 | misses auto-named `instFiniteRangeComp` |
| 40 | exceptional_set (carleson) | 13 | exact | 7/7 | |
| 41 | ProbabilityTheory.exists_isUniform_measureSpace (pfr) | 10 | spill | 3/3 | |
| 42 | ConNF.Tree (con-nf) | 9 | spill+refs | 1/7 | anonymous instance: `deriv`, `Derivative` |
| 43 | homomorphism_pfr (pfr) | 101 | exact | 2/5 | |
| 44 | BohrSet.regularity (LeanAPAP) | 3 | spill | 2/2 | |
| 45 | Eq1729.enlarge_op (equational_theories) | 369 | spill | 30/98 | 66 namesakes in other namespaces; `Eq1729.*` judged by namespace |
| 46 | antichain_decomposition (carleson) | 43 | spill+refs | 1/6 | unscanned `def 𝔏₀'` merged in; misses the unicode-named `ℜ₀`, `𝔏₀_subset_ℭ` and others |
| 47 | sum_of_conditional_distance_le (pfr) | 70 | exact | 11/14 | |
| 48 | rdist_of_neg_le (pfr) | 246 | spill | 11/21 | |
| 49 | AffineSpace.finrank (pfr) | 4 | spill | 1/1 | |
| 50 | partialFourierSum_bound (carleson) | 77 | spill | 9/21 | `T` matched a private def in another file |

## Differences from the pilot

The pilot reported 467/612 with median |N1| 55–184 per project. This run gets
477/614 with medians 15–152 (pooled 39.5). Four changes account for the
difference:

1. **Candidates come from the statement's own project only.** The pilot let a
   short name match declarations of any project, and that is where most of its
   |N1| came from. The gold is always in-project, so this cannot lose a gold.
2. **Only `<project>/blueprint/` TeX is parsed.** The pilot's `'blueprint' in r`
   test matched every path under `mathgraph-data/blueprints`, so it also read
   carleson's and equational_theories' `paper/*.tex`. Some labels there
   duplicate blueprint labels.
3. **Any in-project tag of a multi-tag statement counts** for gold-in-set and
   for r@1. The pilot used the first tag only. This follows bench_pretrained's
   convention.
4. **Unlabelled blocks keep per-file ids.** `theorem:3` restarts in every file.

## Reproduce

```
HF_HUB_OFFLINE=1 MATHGRAPH_DATA=/path/to/mathgraph-data \
  uv run --with sentence-transformers python -m mathgraph.complete records.json \
  > sandbox-handoffs/mathgraph-fxh.json
```

- **Inputs.** `idx_mathlib`, `idx_blueprint`, `idx_full`, `blueprint_decls.jsonl`,
  `pfr.jsonl`, the blueprint checkouts, and bench_pretrained's cached
  `emb_BAAI__bge-small-en-v1.5.npy`, in idx_full row order. If the cache is
  missing, run bench_pretrained once first.
- **Cost.** About 3 minutes on Apple silicon (bge on MPS), with peak RSS 2.4 GB.
- **`HF_HUB_OFFLINE=1`.** Here, the Hub token refresh failed, and
  sentence-transformers 6.3 then could not build the tokenizer. With the model
  cached, offline mode costs nothing.
- **Environment.** A venv inside the worktree: sentence-transformers 6.3.0,
  transformers 5.23.0, torch 2.15.0, numpy 2.5.1.
- **Determinism.** Two runs gave identical summaries.
- **Records.** `records.json` holds per-statement records: top-1 and confidence
  per ranker and set. It is not committed; it is about 850 KB and regenerates
  in one run.

## Not done, and follow-ups (not filed: the worker does not edit mathgraph's bead store)

- **No combined score.** Graph links plus text was not tried; the bead names
  three separate rankers. Neither was 2-hop.
- **A cleaner reference graph.** This is what decides whether graph-only or
  edge consistency carries signal. It needs three things:
  - name resolution through namespaces and `open`;
  - comments, docstrings and binders skipped;
  - bodies cut at the next command.
- **Scanner gaps.** leanscan would need fixing for unicode names,
  `irreducible_def`, `equation N :=` and auto-named instances. These gaps hit
  carleson and equational_theories and lower their gold-in-N1.
- **The open question.** Outside PFR, does N1 beat project-wide ranking? Today
  it does not. A significant win there is what the realistic-use claim would
  need beyond the 40% bar.
