# mathgraph-ydf handoff: name-resolved Lean references for neighbour completion

## Bead

Follow-up to mathgraph-fxh (PR #4, branch `sandbox/portfolio-qs9g`). fxh's
reference extraction linked a body to every declaration whose last name
component matched one of its identifiers. On fxh's 50-body hand check only
39.5% of those links were genuine. Outside PFR, the 1-hop neighbourhood N1 did
not beat plain project restriction (lexical +40/−30, p = 0.28; bge +41/−37,
p = 0.73). This bead replaces the matcher with name resolution, hand-checks 50
fresh bodies, and re-runs complete.py's leave-one-out.

Pre-registered acceptance criteria (bead text, plus the worker's notes fixed
before any test result):

1. On a fresh 50-body hand check, reference precision is at least 70%, and
   recall is not lower than the old matcher's on the same bodies.
2. Report N1 against project restriction per project, with paired sign tests.
   Kill the claim that the graph adds over project restriction if, outside PFR
   and on the n1 split, neither text ranker has N1 ahead at p < 0.05 with the
   better matcher. Also report Bonferroni over the two rankers (p < 0.025).

Code:
- `mathgraph/leanrefs.py`: the resolver.
- `mathgraph/complete.py`: wired to the resolver. fxh's matcher is kept as
  `PilotRefs` behind `--pilot`. Adds sign tests and `kill_test_ydf`.
- `mathgraph/handcheck.py`: the pre-registered sample and its scoring.

Tests: `LeanRefs` and `NeighbourAnchoredCompletion` in `tests/test_units.py`.
Numbers: `sandbox-handoffs/mathgraph-ydf.json` (the script's stdout).
Judgments: `sandbox-handoffs/mathgraph-ydf-handcheck.json`.

## Verdict: the graph-over-project claim is killed

| criterion | threshold | measured | verdict |
|---|---|---|---|
| reference precision, fresh 50 bodies | at least 70% | 246/250 = 98.4% [96.0, 99.4] | pass |
| recall against the pilot, same candidates | resolved genuine ≥ pilot genuine | 246 vs 239 | pass |
| outside PFR, n1: N1 beats project | a text ranker ahead at p < 0.05 | lexical +47/−31, p = 0.089; bge +53/−40, p = 0.21 | **killed** |
| the same, Bonferroni over the two rankers | p < 0.025 | as above | **killed** |

On the first two criteria the resolved matcher is the better matcher: 98.4%
precise against the pilot's 43.3%, with no recall loss on the same bodies.

The kill does not depend on which matcher is better. With fxh's matcher the
same test gives lexical +40/−30 (p = 0.28) and bge +41/−37 (p = 0.73). With
the resolved matcher it gives lexical +47/−31 (p = 0.089) and bge +53/−40
(p = 0.21). Both rankers have N1 ahead, and neither reaches 0.05.

### What the numbers do and do not support

1. **The resolved graph is a much better graph, but not a better verdict.**
   - Edges fall from 303,067 to 60,329.
   - Median |N1| halves (39.5 → 19) while gold-in-N1 is unchanged
     (477 → 474 of 614).
   - Graph-only r@1 rises from 73 to 106 of 614 (+38/−5 statements,
     p = 2.5e-7). bge in N1 rises from 185 to 202 (+23/−6, p = 0.002). Lexical
     in N1 rises from 194 to 201 (+16/−9, p = 0.23).
   - Project-wide rankers do not use references, so they are unchanged. The
     N1-over-project margin therefore grows: outside PFR, lexical goes from
     +40/−30 to +47/−31 and bge from +41/−37 to +53/−40. It is still not
     significant.
2. **Outside PFR the effect is heterogeneous, not absent.**
   - FLT favours N1 strongly: bge +21/−0, p = 1e-6; lexical +18/−3,
     p = 0.0015.
   - carleson favours the whole project: bge +14/−33, p = 0.008. There,
     27.7% of golds are not in N1, and bge over the project reaches 66.9% r@1.
   - con-nf, equational_theories and LeanAPAP are small and not significant.
   - Pooling the five cancels FLT against carleson. A per-project claim
     ("N1 helps on FLT and PFR") would need its own pre-registration. It was
     not this bead's test.
3. **A lead, not a result: the upstream split.** Outside PFR, lexical in N_up
   beats lexical over the project, +54/−30 (p = 0.012). That is the realistic
   direction (the statement's own body cites an anchor it `\uses`).
   - It was not the pre-registered split.
   - The non-PFR row holds six such comparisons. Under Bonferroni (0.0083) it
     fails.
   - bge in N_up is +54/−41, p = 0.22.
4. **fxh's own kill test still passes with the resolved matcher:**
   - gold-in-N1 Wilson lower bound 73.7% (bar: 60%);
   - median |N1| 19 (bar: at most 300);
   - lexical and bge beat graph-only on r@1 and on P@10%: 32.7% and 32.9%
     against 17.3% r@1, and 71.0% and 77.4% against 31.1% P@10%;
   - upstream gold-in-set 65.3% (bar: 40%).

## Hand check of reference extraction (fresh 50 bodies, blind)

### Sample

The sample was pre-registered and fixed before any test result.

- **P:** the 724 gold declarations of the 614 anchored statements, as in fxh.
- **dev:** `random.Random(0).sample(sorted(P), 50)`. This is fxh's sample, and
  it was used to develop the resolver.
- **test:** `random.Random(20261120).sample(sorted(P - set(dev)), 50)`. It does
  not overlap dev. `python -m mathgraph.handcheck sample` rebuilds it.
- **Candidates per body:** pilot references ∪ resolved references, self
  excluded. That gives 565 candidates: 237 from both matchers, 13 resolved
  only and 315 pilot only.

### Judging, blind to the matcher

- **Judges.** Five fresh Claude Opus 5.5 subagents, each given 9 to 11 bodies,
  balanced by candidate count.
- **What each judge saw:**
  - the body's source lines, which may run past the declaration's end;
  - the column-0 scope lines before the body;
  - each candidate's kind, location and header, sorted by name, without the
    matcher labels.
- **What they could open.** The project sources, `mathlib.jsonl` and the
  `mathlib4` checkout. They were told not to open mathgraph's code, samples or
  handoffs.
- **Genuine** means that an identifier written inside the body's own
  declaration resolves to the candidate under Lean 4 name resolution. That
  includes resolution through enclosing namespaces, the declaration's own name
  prefix, `open`/`export`, dot notation on the receiver's type, or a project
  notation that expands to the candidate.
- **Not genuine:**
  - text in comments;
  - text outside the declaration;
  - locals;
  - namesakes (another project declaration, Mathlib or core);
  - implicit use: instances, coercions, unnamed `simp` lemmas, and tactics
    such as `ext` that use an `@[ext]` lemma without naming it.
- Every judgment carries a coded note with the line and token. None was
  marked unsure.
- **Unblinding.** The matcher labels were joined only after all 565
  judgments were in. `python -m mathgraph.handcheck score
  sandbox-handoffs/mathgraph-ydf-handcheck.json` reproduces every number below.

### Results

| measure | resolved | pilot |
|---|---|---|
| extracted references | 250 | 552 |
| genuine | 246 | 239 |
| precision [95%] | **98.4% [96.0, 99.4]** | 43.3% [39.2, 47.5] |
| bodies with at least one spurious reference | 4/50 | 42/50 |
| genuine references the other matcher missed | 13 | 6 |

- The union holds 252 genuine references. The resolved matcher has 246 of
  them (97.6%) and the pilot 239 (94.8%). This recall is relative to the
  union: a reference neither matcher extracted is not counted.
- References cluster by body, so the per-reference intervals are optimistic.
- The pilot's 43.3% agrees with fxh's dev-set figure of 39.5%.
- The judges' codes for the pilot's 313 spurious references:
  - namesake 184;
  - local 59;
  - absent from the body 28;
  - other 26 (tactic names and named-argument labels);
  - outside the declaration 11;
  - implicit 5.

**The four spurious resolved references.**
- **Tactic names that collide with a declaration in an enclosing namespace.**
  `ring` linked to `Hurwitz.ring` (B12), and `ext` to `ZHat.ext` (B32) and
  `WeightTwoAutomorphicForm.ext` (B36). The resolver reads tactic keywords as
  identifiers.
- **A namesake through the untyped-field rule.**
  `(𝓘 u₁ ∩ 𝓘 u₂ : Set X).indicator` (B46) is Mathlib's `Set.indicator`. The
  resolver linked `MeasureTheory.BoundedCompactSupport.indicator`, because the
  ascription's `Set` never reaches the namespaces it consults.

**The six genuine references the resolver misses.** The pilot found them.
- **Notation:** `d[X ; μ # Z ; μ'']` → `rdist` (B02), and `𝓞` → `Hurwitz`
  (B25).
- **The `:=` gap:** `instance nontrivial : Nontrivial ZHat :=` (B16), and
  `let task : β → Set PartialSolution :=` (B23).
- **Dot notation on a receiver whose type is not written:**
  - `N₁.pos_litter_lt_pos` (B42), where `N₁` is bound by `induction … using`;
  - `ξ.flexApprox.ExactlyApproximates` (B42), a field of a field.

**The 13 genuine references only the resolver found.**
- **Six names leanscan truncates at a unicode character.** The pilot's
  identifier pattern cannot match them: `S_eq_zero_of_topCube_mem_𝓙₀` (B17);
  `eI𝒬u_mul`, `norm_eI𝒬u_mul_eq` and `boundedCompactSupport_eI𝒬u_mul` (B26);
  `c𝓑` and `r𝓑` (B30).
- **Four cases of field notation on a constant.**
  `continuous_entropy_restrict_probabilityMeasure.comp` and
  `continuous_measureEntropy_probabilityMeasure.comp` (B21),
  `equivalenceOn_urel.trans` (B39), and
  `le_or_ge_or_disjoint.resolve_left` (B46). The pilot looks up only `*.comp`,
  `*.trans` and so on.
- **Three cases of dot notation through a binder type.** `hg.restrict` and
  `hg.restrict.aestronglyMeasurable` (B26), and
  `(ξ.flexApprox A).litters_permutative` (B42).

Candidate names are leanscan's index names, so a truncated name such as
`TileStructure.Forest.c` stands for the declaration at its location (`c𝓑`).
The judges judged by location, which is also how both matchers identify rows.

### Audit after unblinding

This audit is mine and was not blind.

- I read the notes of all ten decisive judgments: the four spurious resolved
  references and the six resolved misses.
- I re-read the source behind three of them (B16, B23 and B46). All ten agree
  with the judges.
- I also read 48 of the 309 pilot-only rejections: all 28 coded other or
  implicit, and 20 random namesake or local ones. I read 20 random resolved
  acceptances as well. I found no judgment I would change.

Caveat: each body had one judge, and there was no inter-rater check. The
recall margin is 7 references (13 against 6). It would flip only if at least 8
of the 309 pilot-only rejections were wrong. The audit found 0 wrong in a
sample of 48 (Wilson upper bound 7.4%), so a flip is unlikely but not excluded.

### Per body

Columns are genuine / extracted references for each matcher.

| # | declaration (project) | lines | resolved | pilot |
|---|---|---|---|---|
| B01 | diff_rdist_le_1 (pfr) | 10 | 3/3 | 3/5 |
| B02 | rdist_triangle (pfr) | 30 | 5/5 | 6/10 |
| B03 | isUniform_sub_const_of_rdist_eq_zero (pfr) | 25 | 4/4 | 4/4 |
| B04 | boundary_measure (carleson) | 126 | 15/15 | 15/24 |
| B05 | Subgraph.Equation2_implies_Equation1689 (equational_theories) | 4 | 1/1 | 1/8 |
| B06 | ProbabilityTheory.IdentDistrib.tau_eq (pfr) | 14 | 3/3 | 3/4 |
| B07 | IsDedekindDomain.FiniteAdeleRing.baseChangeAlgEquiv (FLT) | 6 | 3/3 | 3/10 |
| B08 | condRuzsaDist_of_sums_ge (pfr) | 10 | 1/1 | 1/1 |
| B09 | GaloisRepresentation.IsHardlyRamified.three_adic (FLT) | 11 | 4/4 | 4/7 |
| B10 | continuous_carlesonOperatorIntegrand (carleson) | 20 | 6/6 | 6/11 |
| B11 | InfModel.Finite.Equation28770_implies_Equation2 (equational_theories) | 20 | 1/1 | 1/22 |
| B12 | Hurwitz.starRing (FLT) | 6 | 0/1 | 0/7 |
| B13 | TileStructure.Forest.adjoint_tree_estimate (carleson) | 13 | 7/7 | 7/15 |
| B14 | ProbabilityTheory.chain_rule (pfr) | 6 | 3/3 | 3/5 |
| B15 | enorm_Ks_sub_Ks_le (carleson) | 12 | 3/3 | 3/4 |
| B16 | ZHat.nontrivial (FLT) | 3 | 1/1 | 2/2 |
| B17 | TileStructure.Forest.local_dens2_tree_bound (carleson) | 60 | 16/16 | 15/24 |
| B18 | KLDiv (pfr) | 8 | 0/0 | 0/2 |
| B19 | rdist_of_sums_ge' (pfr) | 13 | 4/4 | 4/7 |
| B20 | Θ.finite_and_mk_le_of_le_dist (carleson) | 42 | 3/3 | 3/13 |
| B21 | multiTau_continuous (pfr) | 25 | 7/7 | 5/14 |
| B22 | Tile.correlation (carleson) | 3 | 1/1 | 1/3 |
| B23 | Eq1729.not_817 (equational_theories) | 31 | 9/9 | 10/40 |
| B24 | ConNF.StrSet (con-nf) | 7 | 2/2 | 2/2 |
| B25 | Hurwitz.left_ideal_princ (FLT) | 36 | 3/3 | 4/14 |
| B26 | TileStructure.Forest.tree_projection_estimate (carleson) | 68 | 17/17 | 12/23 |
| B27 | rdist_def (pfr) | 5 | 0/0 | 0/6 |
| B28 | condRho_le (pfr) | 8 | 4/4 | 4/4 |
| B29 | ZHat.torsionfree (FLT) | 6 | 2/2 | 2/3 |
| B30 | TileStructure.Forest.correlation_near_tree_parts (carleson) | 47 | 17/17 | 15/28 |
| B31 | approx_hom_pfr' (pfr) | 26 | 2/2 | 2/2 |
| B32 | ZHat.multiples (FLT) | 29 | 3/4 | 3/15 |
| B33 | ConNF.Atom (con-nf) | 15 | 1/1 | 1/9 |
| B34 | rhoMinus_of_subgroup (pfr) | 12 | 4/4 | 4/7 |
| B35 | ProbabilityTheory.entropy_pair_eq_add (pfr) | 8 | 2/2 | 2/2 |
| B36 | TotallyDefiniteQuaternionAlgebra.WeightTwoAutomorphicForm.distribMulAction (FLT) | 6 | 2/3 | 2/10 |
| B37 | ProbabilityTheory.condMutual_comp_comp_le (pfr) | 33 | 3/3 | 3/5 |
| B38 | cover_big_ball (carleson) | 33 | 6/6 | 6/8 |
| B39 | forest_inner (carleson) | 52 | 15/15 | 14/22 |
| B40 | ConNF.Support (con-nf) | 15 | 4/4 | 4/11 |
| B41 | construct_good_improved' (pfr) | 30 | 2/2 | 2/2 |
| B42 | ConNF.StrAction.approximates_of_flexApprox_exactlyApproximates (con-nf) | 47 | 19/19 | 20/63 |
| B43 | smul_C2_1_2 (carleson) | 15 | 3/3 | 3/9 |
| B44 | iter_multiDist_chainRule (pfr) | 47 | 4/4 | 4/8 |
| B45 | kvm_ineq_I (pfr) | 41 | 3/3 | 3/4 |
| B46 | TileStructure.Forest.correlation_separated_trees (carleson) | 21 | 6/7 | 5/17 |
| B47 | entropy_of_W_le (pfr) | 34 | 9/9 | 9/13 |
| B48 | dyadic_property (carleson) | 131 | 4/4 | 4/8 |
| B49 | entropic_PFR_conjecture_improv (pfr) | 18 | 7/7 | 7/12 |
| B50 | boringEnergy (LeanAPAP) | 2 | 2/2 | 2/3 |

"lines" counts the listed lines: the longer of the resolver's command and the
pilot's slice.

## Results with the resolved matcher (614 anchored statements)

The population is unchanged: rows located in a project's files count as
in-project, exactly as with the pilot. 36 statements still have no anchor
(FLT 7, LeanAPAP 1, equational_theories 28). Every ranker, candidate set and
metric is defined as in `mathgraph-fxh.md`; only the references differ. Pilot
numbers are fxh's and are reproduced exactly by `--pilot`.

### All projects, n1

N = 614. Gold in N1: 474/614 = 77.2% [73.7, 80.3] (pilot 77.7%). Median |N1|
19 (pilot 39.5).

| ranker / candidates | answered | r@1 | P@10% | pilot r@1 | pilot P@10% |
|---|---|---|---|---|---|
| graph/n1 | 233 | 106/614 = 17.3% | 19/61 = 31.1% | 73/614 = 11.9% | 16/61 = 26.2% |
| lexical/n1 | 558 | 201/614 = 32.7% | 44/62 = 71.0% | 194/614 = 31.6% | 41/62 = 66.1% |
| bge/n1 | 592 | 202/614 = 32.9% | 48/62 = 77.4% | 185/614 = 30.1% | 49/62 = 79.0% |
| lexical/project | 559 | 164/614 = 26.7% | 34/62 = 54.8% | same | same |
| bge/project | 614 | 161/614 = 26.2% | 48/62 = 77.4% | same | same |
| lexical/global | 542 | 106/614 = 17.3% | 18/62 = 29.0% | same | same |
| bge/global | 614 | 129/614 = 21.0% | 40/62 = 64.5% | same | same |

### Outside PFR, n1 (the kill test's population)

N = 413. Gold in N1: 291/413 = 70.5% [65.9, 74.7] (pilot 70.7%). Median |N1|
15 (pilot 39).

| ranker / candidates | answered | r@1 | P@10% | pilot r@1 | pilot P@10% |
|---|---|---|---|---|---|
| graph/n1 | 116 | 41/413 = 9.9% | 11/42 = 26.2% | 19/413 = 4.6% | 7/42 = 16.7% |
| lexical/n1 | 367 | 137/413 = 33.2% | 30/42 = 71.4% | 131/413 = 31.7% | 28/42 = 66.7% |
| bge/n1 | 391 | 149/413 = 36.1% | 37/42 = 88.1% | 140/413 = 33.9% | 35/42 = 83.3% |
| lexical/project | 376 | 121/413 = 29.3% | 25/42 = 59.5% | same | same |
| bge/project | 413 | 136/413 = 32.9% | 32/42 = 76.2% | same | same |

### Upstream and downstream splits

| split | N | gold in set | median size | graph r@1 | lexical in set | bge in set | lexical project | bge project |
|---|---|---|---|---|---|---|---|---|
| pooled up | 496 | 324 = 65.3% [61.0, 69.4] | 6 | 22.2% | 34.3% | 33.5% | 23.4% | 23.8% |
| pooled down | 524 | 326 = 62.2% [58.0, 66.3] | 8 | 7.6% | 36.8% | 32.1% | 29.0% | 28.8% |
| non-PFR up | 313 | 186 = 59.4% [53.9, 64.7] | 3 | 18.2% | 33.6% | 34.2% | 25.9% | 30.0% |
| non-PFR down | 342 | 180 = 52.6% [47.3, 57.9] | 7 | 6.4% | 33.6% | 32.8% | 33.3% | 37.4% |
| PFR up | 183 | 138 = 75.4% [68.7, 81.1] | 9 | 29.0% | 35.5% | 32.2% | 19.1% | 13.1% |
| PFR down | 182 | 146 = 80.2% [73.8, 85.4] | 10 | 9.9% | 42.9% | 30.8% | 20.9% | 12.6% |

Upstream P@10% (pooled): graph 29/49 = 59.2%, lexical 32/50 = 64.0%, bge
30/50 = 60.0%, bge over the project 37/50 = 74.0%. fxh's observation stands: in
the realistic direction, the most confident answers come from bge over the
whole project, not from N_up.

### By project (n1, r@1), with N1 against project

| project | N | gold in N1 | median \|N1\| | graph | lexical N1 | bge N1 | lexical project | bge project | lexical N1 vs project | bge N1 vs project |
|---|---|---|---|---|---|---|---|---|---|---|
| FLT | 122 | 89 = 73.0% | 10 | 13.1% | 22.1% | 23.8% | 9.8% | 6.6% | +18/−3, p=0.0015 | +21/−0, p=1e-6 |
| LeanAPAP | 22 | 16 = 72.7% | 12.5 | 22.7% | 40.9% | 27.3% | 31.8% | 22.7% | +3/−1, p=0.62 | +3/−2, p=1 |
| carleson | 166 | 120 = 72.3% | 20 | 7.8% | 47.6% | 55.4% | 52.4% | 66.9% | +15/−23, p=0.26 | +14/−33, p=0.008 |
| con-nf | 53 | 44 = 83.0% | 113 | 9.4% | 28.3% | 20.8% | 18.9% | 11.3% | +7/−2, p=0.18 | +7/−2, p=0.18 |
| equational_theories | 50 | 22 = 44.0% | 11.5 | 4.0% | 14.0% | 22.0% | 10.0% | 12.0% | +4/−2, p=0.69 | +8/−3, p=0.23 |
| pfr | 201 | 183 = 91.0% | 26 | 32.3% | 31.8% | 26.4% | 21.4% | 12.4% | +27/−6, p=3e-4 | +31/−3, p=8e-7 |

The same N1-against-project tests with the pilot matcher:

| project | lexical | bge |
|---|---|---|
| FLT | +11/−3, p=0.057 | +15/−0, p=6e-5 |
| LeanAPAP | +3/−1, p=0.62 | +3/−1, p=0.62 |
| carleson | +16/−24, p=0.27 | +12/−32, p=0.004 |
| con-nf | +4/−1, p=0.38 | +7/−2, p=0.18 |
| equational_theories | +6/−1, p=0.12 | +4/−2, p=0.69 |
| pfr | +25/−5, p=3e-4 | +23/−3, p=9e-5 |

### Paired comparisons (r@1, n1 split): resolved, then pilot

| comparison | pooled (614) | PFR (201) | non-PFR (413) |
|---|---|---|---|
| lexical in N1 vs graph | +167/−72, p=7e-10; +170/−49, p=8e-17 | +42/−43, p=1; +46/−37, p=0.38 | +125/−29, p=2e-15; +124/−12, p=1e-24 |
| bge in N1 vs graph | +169/−73, p=6e-10; +170/−58, p=6e-14 | +36/−48, p=0.23; +35/−44, p=0.37 | +133/−25, p=5e-19; +135/−14, p=5e-26 |
| lexical: N1 vs project | +74/−37, p=6e-4; +65/−35, p=0.004 | +27/−6, p=3e-4; +25/−5, p=3e-4 | **+47/−31, p=0.089**; +40/−30, p=0.28 |
| bge: N1 vs project | +84/−43, p=3e-4; +64/−40, p=0.02 | +31/−3, p=8e-7; +23/−3, p=9e-5 | **+53/−40, p=0.21**; +41/−37, p=0.73 |
| lexical vs bge, in N1 | +59/−60, p=1; +62/−53, p=0.46 | +32/−21, p=0.17; +36/−18, p=0.02 | +27/−39, p=0.18; +26/−35, p=0.31 |

The same ranker under the two matchers, on the same statements (pooled n1):
graph +38/−5 (p = 2.5e-7), bge +23/−6 (p = 0.002), lexical +16/−9 (p = 0.23).
Every split is in the JSON under `set_vs_project`, for pooled, PFR, non-PFR
and each project.

## The resolver

`leanrefs.Project(files, Mathlib(mathlib.jsonl)).refs(rows)` returns
{row: rows its command references}. Rows are matched to commands by (module,
line). What it does, from the module docstring:

- Comments, docstrings and strings are blanked. A body ends at the next
  column-0 command, not at the next scanned declaration (fxh's spill).
- Scopes are tracked: `namespace`, every `section` form (including `public`,
  `noncomputable` and `@[expose]` sections, which leanscan misses), `mutual`
  and `end`. `theorem Foo.bar` opens `Foo` for its own command.
- Locals shadow globals: section `variable`s, signature binders, and the
  binders of the body (fun, quantifiers, big operators, have/let/obtain,
  intro/rintro/`with` names, match alternatives, set-builder).
- A global is looked up in the enclosing namespaces innermost first, then as
  written, under every `open` in scope (`in`, explicit, `hiding`, `renaming`)
  and every `export` alias. `protected` needs a qualifier and `private` stays
  in its file. Failing all that, the last component is dropped, which is field
  notation on a constant.
- `x.f` on a local whose binder type `T …` is written resolves to `T.f`.
  Otherwise `f` is looked up in the namespaces the command mentions, linking
  only when every candidate is a project declaration and `f` is not a core
  field.
- Mathlib's names (from `mathlib.jsonl`) count as existing, so a Mathlib name
  shadows a project namesake exactly where Lean's lookup reaches it first.

Coverage: every index row matches a command except 23, which are declarations
inside `/- -/` commented-out code that leanscan indexes. Those cite nothing,
but they stay in the population, as with the pilot.

### Known misses

- **Dot notation without a written type.** One example is a local whose field
  has several project owners (dev #12, `Vindep.rdist_eq`). Another is a
  receiver whose type only elaboration knows (dev #44 `(ρ • B).IsRegular`,
  dev #49 `(vectorSpan k s).finrank`).
- **The token before `:=` is never resolved.** The rule exists for
  `have h :=`, `(x := e)` and structure fields. It also drops the last
  identifier of a type ascription that ends right before `:=`. That happens
  in the declaration's own statement (`theorem t : P := …`,
  `instance : Nontrivial ZHat := …`, hand-check B16) and in a typed
  `let`/`have` (`let task : β → Set PartialSolution := …`, B23).
  - For the declaration's own `:=` alone, the corpus loses 380 of 60,329
    edges (0.6%): con-nf 187, equational_theories 147, FLT 28, carleson 13,
    LeanAPAP 5, pfr 0.
  - It was found after the freeze, so it is left in.
  - Fix: skip only binder and field positions.
- **Tactic names read as identifiers.** `ring` and `ext` link to a project
  declaration of that name in an enclosing namespace (`Hurwitz.ring`,
  `ZHat.ext`). That is three of the hand check's four false positives. Fix:
  skip the leading word of a tactic step when it is a tactic.
- **The untyped-field rule misses an ascribed receiver.** In
  `(s : Set X).indicator`, `Set` never enters the namespaces the rule
  consults, so the project's only other `*.indicator` wins (B46).
- **Unseen by any text matcher.** Notation, coercions, instances, unfolding,
  `simp` sets, and leanscan's gaps (`equation N :=`, auto-named instances).

### Fixed after the freeze

`open X renaming a → b` was parsed off by one: the `renaming` keyword was taken
as the first old name. The six projects contain no `open … renaming`. After the
fix, the hand-check sample and the full leave-one-out (summary and records)
regenerate byte-identical. Test: `test_open_in_explicit_hiding_and_renaming`.

### Elaboration is not available here

Elaborated dependency data would make most of the misses above disappear.
It cannot be produced on CPU in this session:

| project | toolchain | Mathlib pin |
|---|---|---|
| pfr | v4.33.0-rc1 | 38b74e6, plus AddCombi e2a3266 |
| FLT | v4.33.0-rc1 | 79d0395 |
| carleson | v4.32.0 | 81a5d25 |
| LeanAPAP | v4.32.0 | 81a5d25, plus AddCombi 8ab3947 |
| equational_theories | v4.29.1 | 5e932f9 |
| con-nf | v4.21.0-rc3 | 5b77ef3 |

- The only built Mathlib is `mathgraph-data/mathlib4` at b44f89d
  (v4.33.0-rc1). It matches no pin.
- Only v4.33.0-rc1 and v4.34.0-rc2 are installed.
- Elaborating would mean building five Mathlib revisions on four toolchains,
  plus the projects. That is far beyond this bead's two-hour bound, and needs
  network caches.

## Reproduce

```
export HF_HUB_OFFLINE=1 MATHGRAPH_DATA=/path/to/mathgraph-data
uv run --with sentence-transformers python -m mathgraph.complete records.json \
  > sandbox-handoffs/mathgraph-ydf.json          # resolved matcher
uv run --with sentence-transformers python -m mathgraph.complete records-pilot.json --pilot
python -m mathgraph.handcheck sample sample.json  # the 50 test bodies and their candidates
python -m mathgraph.handcheck score sandbox-handoffs/mathgraph-ydf-handcheck.json
```

- **Inputs.** As for fxh, plus `artifacts/mathlib.jsonl`, which provides
  Mathlib names for the resolver.
- **Cost.** About 5 to 6 minutes per run on Apple silicon, with bge on MPS and
  peak RSS 2.1 GB. Building the six resolver projects takes about 1.5 minutes
  of that.
- **Determinism.** Two resolved runs gave byte-identical stdout and records.
  `--pilot` reproduces every number in `mathgraph-fxh.json`
  (statements, no_anchor, pooled, pfr, by_project, kill_test), which checks
  that the refactor changed nothing but the references.
- **Environment.** The worktree venv: sentence-transformers 6.3.0, torch
  2.15.0, numpy 2.5.1, pytest 9.2.0.
- **Tests.** `MATHGRAPH_DATA=… .venv/bin/python -m pytest -q` gave 107
  passed in 15 minutes: fxh's 96, plus 11 new (8 `LeanRefs` tests and 3
  completion helpers). The run shared the machine with another worker's suite.
  The venv is the project environment, so this equals `uv run --no-sync pytest
  -q`.

## Not done, and follow-ups (not filed: the worker does not edit mathgraph's bead store)

- Fix the `:=` skip, tactic names and ascribed receivers. Together they
  account for 2 of the 6 misses and 4 of the 4 false positives in the hand
  check. The `:=` skip is 0.6% of edges, and none of the three can move the
  verdict.
- An inter-rater check of the hand check: a second blind judge on some of the
  same bodies.
- A per-project or upstream-only claim (FLT, PFR; lexical N_up outside PFR)
  would need its own pre-registered test on fresh data.
- Elaborated references for the projects that share the installed toolchain
  (pfr and FLT on v4.33.0-rc1). This would need their Mathlib pins built, so it
  is a network and compute job, not a session job.
- carleson is where N1 loses most: 27.7% of golds lie outside N1. Its unicode
  names and notation-heavy statements are where a text resolver is weakest.
