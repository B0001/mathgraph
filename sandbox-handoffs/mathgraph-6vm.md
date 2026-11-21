# mathgraph-6vm handoff (city mirror portfolio-4ene)

Kernel-certified relabel audit of in-library negatives.

## Pre-registration

This section was committed before any check ran on a holdout, deletion or
positive unit. Git history shows the order. At commit time, three things had
been done:

- The oracle had been probed on synthetic pairs only. These were H's written
  into the probe file itself, plus near-miss pairs of control-index theorems
  that are in no arm (probe evidence below).
- Names had not been resolved yet. `#kresolve` runs as the first pipeline
  stage, before any check.
- The unit counts and thresholds had been checked against
  `results/timesplit.json`.

### Question

Of the holdout and deletion queries that the time-split run counts as false
matches at τ, how many retrieved a top-1 T that **proves** the query's own
theorem H? For those, the label is wrong, not the retriever. The audit claims
that number, not the mechanism. Retrieval nominates and the kernel decides,
which is atlas-lean's dedup pattern, here aimed at benchmark labels.

### Inputs (read-only)

- **Timesplit outputs.**
  `mathgraph-data/hctz-timesplit/` holds them: `arms.jsonl`, `lexical.jsonl`
  and `dense.jsonl` (rows with `corpus == "ctrl"`), and `idx_ctrl`. It is the
  byte-identical snapshot of the hctz build.
- **Units.** One unit per (system, query), for every holdout (1,602),
  deletion (1,660) and positive (1,206) query under lexical and bge-small:
  8,936 units in all.
  - H is the query's own theorem.
  - T is that system's ctrl top-1.
  - The units contain 8,382 distinct non-gold (H, T) pairs. A pair shared by
    both systems is checked once and counted once per unit.
  - 192 positive units already have T = H. They are correct by name and need
    no check. 70 units have no top-1.
- **τ and halves.** They come from `timesplit.score_system` and `halves(·, 0)`,
  which reproduce `results/timesplit.json` exactly.
  - τ is non-strict: lexical 0.21251466870307922, bge-small
    0.9128261208534241.
  - Eval-half answers match that file: lexical holdout 100/801 and deletion
    100/830; bge-small 112/801 and 108/830; positives 60/603 and 76/603.
- **Gate population.** Eval-half holdout and deletion units of both systems:
  420 above τ and 2,842 below.
- **Lean.** mathlib4 built at the pin b44f89d, Lean v4.33.0-rc1. Checks run
  from that checkout with `lake env lean`, and nothing is written into it.

### Oracle

**Real check, per (H, T).** One line per check:

```lean
attribute [-simp] <H and/or T, whichever are [simp] lemmas> in
theorem kaudit.cN : type_of% @H := by intros; first
  | kalt "K1" (exact T ..)
  | kalt "K2" (exact (T ..).symm)
  | kalt "K3" (exact (T ..).1)
  | kalt "K4" (exact (T ..).2)
  | kalt "K5" (simpa only [] using T ..)
  | kalt "D1" (apply T <;> assumption)
  | kalt "D2" (symm; apply T <;> assumption)
  | kalt "D3" (apply (T ..).1 <;> assumption)
  | kalt "D4" (apply (T ..).2 <;> assumption)
```

- **`kalt "tag" (tac)`.** Defined in `lean/KAudit.lean`, it runs `tac` and
  then fails unless the goal is closed by a complete term: no goals left, no
  unassigned holes, no `sorry`. When it succeeds it records the tag.
- **Null check.** It runs per (H, T if T is a simp lemma). It has the same
  statement and the same erasure, with the alternatives
  `kalt "N1" (trivial) | kalt "N2" (simp; done) | kalt "N3" (positivity)`.
- **CERTIFIED** needs all four of these:
  - The real check closes. That means its proof term (from `#kdump`, which
    calls `getUsedConstants`) contains no `sorryAx`. A theorem that
    elaborates has passed `addDecl`, so the kernel checked it.
  - The term uses T.
  - The term does not use H.
  - The null check fails.
- **Settings.**
  - `maxHeartbeats` is 200000 per declaration, Lean's default.
  - `Elab.async` is false and `autoImplicit` is false.
  - Linters are off.
- **Closing alternative.** `kalt` records it. `first` stops at the first
  alternative that closes and K1–K5 come first, so a D tag means no K
  alternative closed.

Deviations from the bead text, and why:

1. **`intros`, not `intro*`.** `intro*` does not parse at v4.33.0-rc1
   ("unexpected token '*'").
2. **D1–D4 added.**
   - `T ..` leaves T's explicit hypothesis arguments as holes, and `exact`
     rejects unassigned holes. The probe's error was "don't know how to
     synthesize implicit argument `hab`".
   - So the verbatim block fails whenever T needs a hypothesis that H's own
     context holds, even when H and T are the same statement. That would
     undercount closures and bias kill (a) toward KILL.
   - D1–D4 hand those holes to `assumption`.
   - Because the K alternatives are tried first, the **verbatim-oracle**
     numbers (K tags only) are reported next to the full ones. The gate uses
     the full oracle.
3. **Null erases T too.** When T is a simp lemma, the null erases T as well as
   H; otherwise `simp` could close H by using T.
4. **Only real simp lemmas are erased.** Membership comes from
   `SimpTheorems.isLemma` in the pin's environment. On a name that is not a
   simp lemma, `attribute [-simp]` only warns at this version.
5. **`simp; done` in the null.** A `simp` that makes progress without closing
   would otherwise stop `first` before `positivity` is tried.
6. **Private names.** A private H or T cannot be named from another file.
   Such units are not checked and are reported by reason; so are names that
   are absent from the pin's environment.
   - The primary analysis is on checked units.
   - A sensitivity analysis counts unchecked units as not certified.
7. **Kernel certification.** It is the theorem command's own `addDecl`; no
   separate call is made.
8. **Every alternative must close completely (`kalt`).**
   - In the probe, `simpa only [] using T ..` succeeded as a tactic for an
     unrelated T while leaving T's holes unassigned.
   - The theorem then failed only at its end. Meanwhile `first` had already
     committed to K5 and never tried D1–D4.
   - Example: `Nat.lt_irrefl` from itself failed this way, although D1
     proves it.
   - `kalt` turns such a partial success into a failure, so `first` moves on.
9. **`-DmaxErrors=0`.** Lean exits after 100 errors by default, and most
   checks fail by design.

### Kill test

Both parts are computed on gate-population units that were checked, with both
systems pooled. The test is OR-combined.

- **(a)** Take the certified rate among the units above τ. KILL if its Wilson
  95% upper bound is below **15%**.
- **(b)** Take the certified rate above τ minus the certified rate below τ.
  KILL if that gap is **5 pp or less** (point estimate). Its Newcombe 95%
  interval is reported alongside. A gap that small would mean closures are
  tactic noise, not retrieval of real equivalents.

The verdict is KILL if (a) or (b) holds, else SURVIVES. It is reported either
way, together with the sensitivity version that counts unchecked units as not
certified.

### Secondary numbers (reported, not gates)

- **Closure profile.**
  - Closure by alternative, and the verbatim-oracle rates.
  - The null-closure rate.
  - Closed-but-not-certified checks, by reason: null closes, uses H, or no T.
- **Kernel-EQUIV vs IMPLIES.** For certified pairs, the reverse check proves T
  from H with the same block and the roles swapped. It is EQUIV if that
  closes, uses H and does not use T.
- **to_additive-map.** Units whose T is H's `to_additive` translation, or the
  reverse, by Mathlib's translation table at the pin. This is metadata, not
  kernel: counts and their certified share.
- **Deprecated top-1.** Units whose T is deprecated, and how many of those are
  aliases of H.
- **Verbatim sibling docstrings.** The negatives whose docstring sits
  verbatim on a row that stayed indexed: 260 holdout and 160 deletion, counted
  as `timesplit.report` counts them. Rates are given for these rows and for
  the rest.
- **Relabel at τ, on eval halves, per system.**
  - FMR before (answered / n) and after (answered and not certified / n, the
    same denominator).
  - Positive precision before (top-1 is gold) and after (gold or certified).
- **AUROC.** It is computed over whole arms, since it needs no threshold, with
  a 1,000-draw bootstrap stratified by class (seed 0). Two definitions are
  given, each before relabelling (correct means T = H) and after (correct
  means T = H or certified):
  - correct positives vs holdout and deletion queries;
  - correct vs incorrect over all three arms.

  Two cautions apply:
  - The round-2 simulation caps the relabelled AUROC near 0.62 even at 100%
    closure.
  - The notes never define their "0.48", so no number here is claimed to
    explain it.
- **Time arm, item (4).**
  - Each of the 1,660 time-arm heads is elaborated at the pin as
    `example <statement> := sorry`, inside the declaration's namespace.
  - It is run with `autoImplicit` false, mathlib's setting and the primary
    run, and again with it true. The second run is a crude stand-in for the
    `variable` lines that a head does not carry.
  - The result is the failure rate with a Wilson interval, broken down by the
    kind of the first error. It is not a closure rate.
- **Hand check.** This agent reads 20 certified pairs for vacuity. They are
  sampled with seed 0, from the above-τ gate population first.

### Configuration and compute

- **Probe rate.** In probe 2, 270 commands took 1,046 s in one Lean process
  at a machine load average of about 27. That is roughly 3 s per check.
- **The full design does not fit the bound.** All 8,936 units, with a null
  per H, would be about 13k checks, about 5–6 h on the 2 allowed processes.
  The worker rule caps a run at about two hours.
- **Pre-registered configuration.**
  - **Eval halves only:** 4,468 units, 4,161 real checks. The kill test uses
    only eval halves.
  - **Gate population first in every batch file,** then eval-half positives.
  - **Real checks first.** The null and reverse checks run only for pairs
    whose real check closed, since nothing else can be certified, so the
    certification rule is unchanged.
  - **Relabelled FMR, precision and AUROC** are therefore on eval halves.
- **Bounds.**
  - Each batch file is killed after 3 h of wall time. Any unit not reached by
    then is reported as not run; because of the ordering, those are positives
    first.
  - A file that stalls for 30 min, or crashes, is resumed past the check that
    stopped it, and that check is reported.
- **What the full run would need.** About twice the check stage: the fit
  halves are 4,468 more units and about 4.2k more pairs.

### Probe evidence (synthetic pairs only)

- **Probe 1** was a hand-written file run against the pin.
  - `attribute [-simp]` on a name that is not a simp lemma only warns.
  - `intro*` does not parse.
  - `exact lt_of_lt_of_le ..` against `Nat.lt_of_lt_of_le` fails ("don't
    know how to synthesize implicit argument"), while
    `apply lt_of_lt_of_le <;> assumption` closes.
  - A private H gives "Unknown constant", but `mkPrivateNameCore` finds it.
  - With `mul_one` erased, `simp` no longer closes `mul_one`, which is the
    round-2 self-simp confound.
- **Probe 2** ran this pipeline on H's written into the batch, plus 120
  near-miss pairs drawn from control-index theorems in no arm. Every case
  came out as expected:

  | Case | Expected | Got |
  |---|---|---|
  | `n = n - m + m` from `Nat.sub_add_cancel` | D2 | D2 |
  | the iff-with-hypothesis case | D3 | D3 |
  | `le_antisymm` | D1 | D1 |
  | `n + 0 = n` | null closes, not certified | null closes |
  | unrelated T against `mul_one` (erased) | fails | fails |
  | `Nat.add_comm` from `add_comm` | K1 | K1 |
  | `Nat.le_of_lt_succ` from `Nat.lt_succ_iff` | D3 | D3 |

  Of the 120 near-miss pairs, 6 closed.
- **The core-only template test** caught the K5 partial-success bug fixed by
  `kalt` (deviation 8).
- **The report path** was dry-run end to end on fake results.

## Results

Everything below came after the pre-registration commit (fa12002). The
numbers are in `results/kaudit.json`, written by
`python -m mathgraph.kaudit report`.

### Verdict: KILL, on both parts of the kill test

| | certified / checked | rate | 95% interval |
|---|---|---|---|
| (a) above τ, eval-half holdout+deletion, both systems | **8 / 394** | 2.0% | Wilson [1.0, 4.0]; the upper bound is under the 15% bar |
| below τ | 46 / 2,608 | 1.8% | Wilson [1.3, 2.3] |
| (b) gap, above minus below | | **+0.27 pp** | Newcombe [−0.9, +2.2]; ≤ 5 pp |

- **Sensitivity.** Counting unchecked units as not certified gives 8/420
  above and 46/2,842 below, the same verdict.
- **Verbatim oracle.** The bead's block alone (K closures only) gives 3/394
  (0.8%) above and 21/2,608 (0.8%) below. The deviations D1–D4 did not create
  a gap either.
- **By system and arm, above τ:**
  - lexical: holdout 1/90, deletion 0/90;
  - bge-small: holdout 4/108, deletion 3/106.
- **Conclusion.** The in-library false matches at τ are almost all real
  errors. Only about 2% retrieve a top-1 that proves the held-out theorem in
  one kernel-checked step. The rate is the same where the retriever is
  confident as where it is not, so these closures are background sibling-lemma
  coincidences, not retrieval of real equivalents.
- **Agreement with hctz.** This matches the provisional single-rater audit in
  mathgraph-269 (3/60 time-arm pairs equivalent or generalising).

### Relabel (secondary), eval halves

| | lexical | bge-small |
|---|---|---|
| FMR holdout, before → after | 12.5% → 12.4% | 14.0% → 13.5% |
| FMR deletion, before → after | 12.0% → 12.0% | 13.0% → 12.7% |
| positive precision at τ, before → after | 8/60 → 8/60 | 0/76 → 1/76 |
| AUROC, correct positives vs negatives | 0.546 [0.48, 0.60] → 0.561 [0.50, 0.62] | 0.380 [0.30, 0.46] → 0.539 [0.48, 0.59] |
| AUROC, correct vs incorrect | 0.550 → 0.565 | 0.383 → 0.542 |

- Both AUROC rows use a 1,000-draw stratified bootstrap.
- bge-small's "before" AUROC is the round-2 construction artefact: positives
  were re-embedded without their docstring, and only 32 eval-half positives
  are correct by name.
- The relabel lifts it to about 0.54, still near chance and under the
  simulated 0.62 cap. Nothing here is claimed to explain the round-2 "0.48".

### Breakdowns

- **Closures.** 70 checked units closed and 65 were certified (62 distinct
  pairs).
  - Closing alternatives: K1 26, D1 25, D4 8, D3 4, K2 4, K4 2, K3 1.
  - Five closures failed certification, all because the null closed. Among
    closed gate-population units the null closed 5/59.
  - No closure used H.
- **Kernel-EQUIV vs IMPLIES.** Of the 65 certified units, 29 are EQUIV (H
  also proves T in one step) and 36 are IMPLIES only.
- **to_additive-map** (metadata, not kernel).
  - 45 checked units retrieve H's to_additive twin or its source, and none of
    them closes.
  - 19 of those are above-τ gate units. That is a second relabel candidate,
    larger than the kernel one.
  - Exploratory, not pre-registered: counting the twins as correct gives
    27/394 above τ, Wilson upper bound about 9.8%. (a) still kills.
- **Deprecated top-1.** 26 units, 5 certified. In 6 of them T is a deprecated
  alias whose new name is H, which the index kept.
- **Verbatim sibling docstrings** (gate population).
  - Duplicate rows: 11/407 certified (2.7%), 3/83 above τ.
  - Other rows: 43/2,595 (1.7%), 5/311 above τ.
- **Unchecked units.** 260 of the 3,262 gate-population units were not
  checked (per-system counts are in `breakdowns.status`):
  - a private H or T: 77 (2.4%);
  - a name with no constant at the pin: 151 (4.6%). Of these, 89 are top-1s
    (81 of them lexical) and 62 are H's;
  - no top-1 at all: 32 (1.0%).
- **Heartbeat timeouts.** 65 gate-population checks hit 200,000 heartbeats
  and count as not closed.

### Time arm, item (4): heads at the pin

- **Failure rates.**
  - autoImplicit false: **1,596/1,660 = 96.1%** [95.1, 97.0] fail to
    elaborate.
  - autoImplicit true: **1,537/1,660 = 92.6%** [91.2, 93.8].
- **Strict failures by first error:**
  - an unknown identifier, constant or namespace: 1,218;
  - a message containing "expected", a coarse bucket that also catches
    "function expected" and "type expected": 352;
  - universe: 10; instance: 7; other: 9.
- **Auto-implicit failures by first error.** Auto-implicit trades unknown
  names (108) for unsynthesisable instances (588) and "expected" errors (658).
- **Consequence.** Only 64 heads (123 with auto-implicit) are even
  statable at the pin. So this oracle cannot audit the time arm. This is an
  elaboration-failure rate, not a closure rate.

### Hand check: 20 certified pairs, read for vacuity

They are sampled with seed 0: the 8 above-τ gate pairs first, then from the
other certified pairs. **0/20 are vacuous.** Each is a genuine one-step
derivation:

- **One direction of an iff T:** #1 `isTree_of_minimal_connected`,
  #2 `LinearDisjoint.symm`, #4, #16, #20.
- **A specialization of T:**
  - #3 `A * ⅟B * B = A` from `mul_invOf_cancel_right` at `⅟B`, since
    `⅟⅟B` is definitionally `B`;
  - #6 at `e.symm`;
  - #9 Hahn–Banach over ℝ from the `RCLike` version;
  - #10 at `t := {x | p x}`.
- **A definitional restatement:**
  - #5 List from Multiset `mem_antidiagonal`;
  - #11, the `fun` variant;
  - #13 `mk''`/`mk`;
  - #14 `sumAddHom`/`sumZeroHom`;
  - #15 `isUnitSMul`/`unitsSMul`.
- **Primed or namespaced twins:** #7, #8, #12, #17, #18, #19.

They are exactly the pairs a human would call "equivalent or generalising".
There are simply very few of them.

### Run log and deviations during the run

The plumbing bugs below were fixed after the pre-registration and before the
final report. None changed an analysis definition.

1. **`resolve` unpack bug.** After Lean had written `facts.jsonl`, `resolve`
   unpacked three return values instead of four. The facts were complete
   (11,100/11,100 names, no errors) and were reused (aa86b1f).
2. **First elab run void.** Round-robin dealing split each head's
   `namespace`/`end` lines across the two batch files. It was re-run with
   one chunk per head (428d2be). The void run is in `mathgraph-data/kaudit/`
   (`elab-void/`, gitignored).
3. **Follow-up ids.**
   - The `followup` stage numbered null and reverse checks in load order,
     and `report` numbered them in gate order. That attached those results to
     the wrong units.
   - The first report, which I read, gave 6/394 and 48/2,608, also KILL, and
     every unit came out IMPLIES.
   - Ids are now canonical, with a test, and followup was re-run (1178aa1).
     The numbers above come from that run.
4. **Verbatim-oracle gate rates.** The pre-registration promised them, but
   the first `report` did not compute them. They were added afterwards.

Compute:

- **Check stage.** 3,845 real checks in two Lean processes, 29 min wall.
  Each check took a median of about 50 ms, p90 about 0.43 s, at most 76 s.
  The machine was less loaded than during the probe.
- **Follow-up.** 134 checks, about 1.5 min.
- **Elab.** About 3.5 min.
- **The full design** (fit halves too, a null per H) would need roughly
  three times the check stage at this load, about 1.5 h.

### Reproduce

```bash
export MATHGRAPH_DATA=/path/to/mathgraph-data   # hctz-timesplit/, mathlib4/ built at b44f89d
uv run python -m mathgraph.kaudit resolve       # facts.jsonl (names, simp, deprecation, to_additive)
uv run python -m mathgraph.kaudit check         # real checks, eval halves, gate first
uv run python -m mathgraph.kaudit followup      # nulls + reverse checks for closed pairs
uv run python -m mathgraph.kaudit elab          # time-arm heads at the pin
uv run python -m mathgraph.kaudit report        # results/kaudit.json
```

Working files go to `./mathgraph-data/kaudit` (gitignored). Pass
`--halves all` to include the fit halves.

### Unverified / open

- **The oracle is one step.** H's that follow from T only by rewriting with
  other lemmas, by `simp` with lemmas, or in several steps are not counted.
  So 2% is a lower bound on "real equivalents" in that sense. The gap test (b)
  is what says the bound is not hiding a confidence signal.
- **Fit halves are not run.**
- **Timeouts count as failures.** The 65 heartbeat timeouts would need a
  larger budget to rule out late closures.
- **The two-person audit of `results/timesplit-audit.csv`** (mathgraph-269)
  is still pending. This kernel audit does not replace it for the time arm,
  which the oracle cannot state at the pin.

## Test run

`MATHGRAPH_DATA=<data dir> uv run pytest -q` printed `99 passed in 392.98s`.
That is the 97 tests that passed before this change, plus the 2 in
`tests/test_kaudit.py` (the parser and certification self-check, and the
follow-up id check).
