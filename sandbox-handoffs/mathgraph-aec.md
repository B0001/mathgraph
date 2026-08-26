# mathgraph-aec handoff

## Bead

README.md:16 & 280-281: combined-arm calibration-sweep figure ("3 answers out
of 349") has no reproducing command and 349 is arithmetically the old arm
sizes.

Resolution chosen: **(a)** — wrote the combined-arm sweep, re-ran it, and
updated both documented mentions with the fresh measurement. No prior
in-progress work existed on this bead; it was OPEN when claimed.

## What was wrong

No code in the repository combined the PFR present and absent arms into one
precision sweep. `bench_pfr.py`'s `arm_present`/`arm_absent` each computed
their own aggregate metrics (recall, abstention rate) but threw away the
per-statement `(coverage, margin)` records a sweep needs. `evaluate.py`'s
sweep functions (`sweep`, `sweep_zero_false`) operate on a completely
different corpus — the 439-statement non-PFR blueprint pairs, not PFR. There
was nothing to run that would produce "~67%, on 3 answers out of 349" from
current code.

349 was arithmetically 175 (the present arm's pre-scanner-fix count,
independently confirmed stale elsewhere — mathgraph-3gu/etj/1f3) + 174 (the
absent arm). The bead's hypothesis that the honest current denominator is
176 + 174 = 350 is correct — confirmed by measurement below, not assumed.

## What I changed

**`mathgraph/bench_pfr.py`**:
- `arm_present` / `arm_absent` now also return a `"records"` list:
  `(coverage, margin, correct)` for the present arm, `(coverage, margin)` for
  the absent arm (every absent-arm answer is wrong by construction, so no
  correctness flag is needed). `coverage`/`margin` are threshold-independent
  (only `Alignment.status` depends on the Aligner's configured
  `tau_cov`/`delta_margin`), so this is a free byproduct of the alignment
  call already being made — no extra `align()` calls.
- New `combined_precision_sweep(present, absent)`: pools both arms' records
  and does an exhaustive grid search over every observed
  `(coverage, margin)` pair as a candidate threshold, reporting the one that
  maximises precision (ties broken toward more answers). No target precision,
  no minimum-answer floor — "best achievable" means literally the peak,
  which is the plain reading of the README's own phrase.
- `main()` now includes `"combined_calibration"` in its output and strips the
  raw `"records"` lists before returning (they're large and not meant for the
  printed report).

**`README.md`**:
- Line 16 (top summary): `~67% on 3 answers out of 349` →
  `100% on 3 answers out of 350`, with an inline note that this is a
  re-measurement against the current scorer and that the old figure was
  stale on both the precision and the denominator.
- Lines 280-281 (`## Benchmarks` → "Calibration sweep over both arms
  combined"): replaced the bare claim with the new number, the exact
  reproducing command, an explanation of what "349 was stale" meant
  concretely, and an explicit statement that the scorer changed (twice)
  since the old figure was written, so this is a re-measurement, not a
  different methodology chosen to move the number. Kept — unchanged in
  substance — the hedge: **"There is still no operating point that is both
  useful and trustworthy"**, now grounded in the new number (3/350 = 0.9%
  coverage, too small a sample for 100% precision to mean anything).

## The number, and the command that produces it

```
uv run python -m mathgraph.bench_pfr \
  '{"deploy": "mathgraph-data/artifacts/idx_full", "mathlib_only": "mathgraph-data/artifacts/idx_mathlib", \
    "pattern": "mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex", \
    "len_pivot": 0.75, "mod_weight": 0.1, "typ_weight": 0.15, "prefix_weight": 0.85, "title_boost": 2.5}'
```

`combined_calibration` from the output (verified verbatim just before writing
this handoff):

```json
{
  "precision": 1.0,
  "answered": 3,
  "correct": 3,
  "tau_cov": 0.1708,
  "delta_margin": 0.1854,
  "n_present": 176,
  "n_absent": 174,
  "n_combined": 350
}
```

`n_present` (176) and `n_absent` (174) sum to 350, matching the bead's
prediction exactly. `deploy`/`mathlib_only` have to be pointed at `idx_full`
and `idx_mathlib` explicitly — the function's own defaults (`idx_deploy`,
`idx_mathlib_only`) are a pre-existing dead-entry-point issue documented in
the `run-mathgraph` skill (nothing in this environment builds those two
names); I did not touch those defaults, since fixing them is a separate,
already-known issue and not what this bead is about.

## Why the number moved from ~67% to 100% (and why that's not a problem)

I did not go looking for a way to make the number look better. I wrote one
principled sweep (max precision, ties broken by answer count, no floor) and
ran it once. It happened to land on 100%/3 rather than something near 67%.

I checked this wasn't a methodology artifact: I also computed (a) the
zero-false-match-on-absent-arm constrained optimum (what `GRAPH_THRESHOLDS`
itself was fit by) — that gives 75% on 4 answers, still above 67% — and (b)
confirmed neither the shipped `GRAPH_THRESHOLDS` (0.2526/0.2658) nor the
`Aligner` class defaults (0.2474/0.2671) answer *anything* on this combined
pool (0 answered at either), so the historical figure wasn't just "the
shipped thresholds, scored." There genuinely is a `(tau=0.089, delta=0.2473)`
point in the grid that gives exactly 2/3 = 66.7% — so "~67% on 3" was almost
certainly a real number produced by *some* version of this code at some
point — but it is not the maximum, and I am not going to report a
non-maximal point just because it matches old text better. The README's own
"Length normalisation was backwards" and "The type is a third indexed field"
sections document two scorer fixes since roughly that era, both described as
improving recall; a better peak precision on the same combined pool is
consistent with that history, not evidence of a bug in my sweep.

**I left the hedge alone.** "Neither benchmark admits an operating point
where the alignment is trustworthy" is still true: 3 of 350 is 0.9%
coverage. 100% precision on a 3-item sample is not a claim you can act on —
if anything it's a *worse* demonstration of the point than 67% was, because
it's an even more obviously degenerate sample size. I was tempted to soften
"no operating point that is both useful and trustworthy" to something like
"barely" or add a caveat that precision "improved" — I did not, because
usefulness (coverage) is what's failing here, and that got worse in relative
terms if anything (100% precision invites more misplaced trust per answer
than 67% would). I added one clause making that explicit instead of
softening anything.

## What I deliberately left alone

- `README.md:930` (`n=175, pre-scanner-fix corpus` table) — explicitly
  labelled historical, not touched. Not in this bead's scope anyway.
- `README.md:1030`, `README.md:1105`, `QUICKSTART.md:104-105`, the
  `test_corpus.py` 175 assertion, `freeze_bench.py`'s `CARD` — all out of
  scope for mathgraph-aec specifically (the bead names these as coupled but
  tracked separately, e.g. mathgraph-q3z for the freeze_bench CARD). I did
  not touch them.
- The present-arm recall@1 figure in the README ("18.2%") vs. what my own
  run and `tests/test_corpus.py`'s pinned `EXPECTED` both show (18.8%/18.9%)
  — this is a real, small discrepancy I noticed while verifying my sweep
  script's recall numbers matched expectations, but it is **not** this
  bead's subject (line 16/280-281 are about the *combined-arm* figure only).
  I am flagging it here rather than silently fixing or ignoring it — see
  "what I could not verify" below.
- `bench_pfr.py`'s dead default index names (`idx_deploy`,
  `idx_mathlib_only`). Confirmed these are non-functional in this
  environment (see `run-mathgraph` skill gotchas) but fixing them is not what
  this bead asked for, and I didn't want to conflate "make the combined
  sweep exist and be reproducible" (this bead) with "fix bench_pfr's
  defaults" (a different, pre-existing issue). My README command works
  around it by passing explicit paths, same pattern the skill itself
  recommends for the `driver.py`/`load` gotcha.
- freeze_bench.py's `"175 + 174"` CARD text — left untouched, it's a frozen
  release description and the bead's own text attributes it to mathgraph-q3z.

## Filed as follow-up (not done here, out of scope)

I did not file a new bead. Everything I noticed that's out of scope was
already named in mathgraph-aec's own description as tracked elsewhere
(mathgraph-3gu, mathgraph-etj, mathgraph-1f3, mathgraph-q3z), except the
18.2%-vs-18.8%/18.9% present-arm recall@1 discrepancy noted above, which is
small, adjacent, and plausibly already known — I did not create a duplicate
bead for it without checking `bd list`/`bd search` first, and ran out of
scope-budget for this session to do that search. If nobody has filed it,
it should be.

## Test suite

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

```
Ran 76 tests in 105.526s
FAILED (failures=1)
```

The one failure is the documented pre-existing baseline
(`test_evaluated_on_the_documented_number_of_statements`, `176 != 175`,
`tests/test_corpus.py:163`) — present before my changes, not touched by
them, and the README already documents 176 as current. Nothing else failed;
`bench_pfr.py`'s changes are not exercised by any existing test (no test
imports `bench_pfr`), so there was nothing to regress there, and I ran the
module directly (above) as the verification instead.

## Environment note (not part of the bead, recorded so the next session
doesn't lose time on it)

`uv run` failed initially with permission errors on `/home/node/.cache/uv`
and `/home/node/.local/share/uv` (owned by `root`, session runs as `node`).
Worked around with `UV_CACHE_DIR=/tmp/uv-cache XDG_DATA_HOME=/tmp/xdg-data
XDG_CACHE_HOME=/tmp/xdg-cache` for every `uv run` invocation in this session.
Did not investigate or fix the underlying permissions — out of scope, and a
container/environment issue rather than a repo one.

## What I could not verify

- Whether the `(tau=0.089, delta=0.2473)` → 66.7%-on-3 point I found in the
  grid is *actually* how the original "~67% on 3 out of 349" was produced
  historically. I have no commit or script from that era to check against;
  I'm inferring it's plausible from the grid search alone, not confirming
  provenance. I did not claim provenance for the old number in the README
  text — I described it as stale/unreproduced, which is what I could
  actually verify.
- Whether the 18.2%-vs-18.8% present-arm recall@1 mismatch noted above is a
  known, already-filed issue. I did not run `bd search` for it before
  writing this handoff.

## Bead status

Claimed, worked, and evidence now exists: the script's output
(`combined_calibration`) matches the updated README text verbatim, verified
just before writing this handoff. Test suite is at its documented
known-good state (76 run, 1 pre-existing failure, nothing else). Closing
`mathgraph-aec`.

## Git — nothing committed, per policy

```
git status --short
 M README.md
 M mathgraph/bench_pfr.py
```

Suggested commands for a human to run (not run by me):

```
git add README.md mathgraph/bench_pfr.py
git commit -m "..."
```

(Plus whatever the untracked `.beads/issues.jsonl`, `.claude/settings.local.json`,
`sandbox-prompt.md`, and the deleted `.beads/embeddeddolt/...` files from
before this session need — those are pre-existing working-tree state, not
something I created or touched, and are outside this bead's scope to
resolve.)
