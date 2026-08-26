# mathgraph-jvx handoff

## Bead

`bench_pfr.lexical_pool_stats`, `bench_pfr.combined_precision_sweep`, and
`verify.evaluate`'s `math_segments`/pattern-accept path (exercised via
`cli.cmd_verify_bench` / `mathgraph verify-bench [--patterns]`) had no
regression test. `tests/` (test_corpus.py, test_units.py) never called any of
them — confirmed by `grep -rln
'verify-bench|verify_bench|lexical_pool_stats|combined_precision_sweep|combined_calibration'
tests/ mathgraph/` before starting: all hits in `mathgraph/` source, none in
`tests/`. That gap is exactly how the sibling absent-arm 170/4 figure
(README:262, mathgraph-p14) went stale for hours unnoticed.

## Outcome: added the missing regression tests, numbers reproduce as published

No source code changed. Added two new test classes to
`tests/test_corpus.py`:

- `LexicalPoolAndCombinedCalibration` (`@needs("idx_full", "idx_mathlib")`) —
  calls `bench_pfr.arm_present`/`arm_absent`/`lexical_pool_stats`/
  `combined_precision_sweep` directly (same functions `bench_pfr.main` calls)
  and pins:
  - `lexical_pool["reach_rate"]` ≈ 0.835 (delta 0.01), `n` == 176
  - `lexical_pool["median_rank"]` == 42 (exact — deterministic, not a rate)
  - `combined_calibration`: `n_present`==176, `n_absent`==174,
    `n_combined`==350, `precision`≈1.0, `answered`==3, `correct`==3
- `VerifyBenchAcceptRates` (`@needs("idx_full")`) — builds the same 176
  present-arm gold pairs `cmd_verify_bench` builds (3-tuple and 4-tuple with
  `math_segments`) and calls `verify.evaluate` directly for both `permissive`
  and `precise` profiles, pinning:
  - the 5-population accept-rate table without patterns (correct/sibling/
    wrong_namespace/hallucinated/random × permissive/precise)
  - `wrong_namespace` population size == 21 (not 176)
  - hallucinated proposals are 100% caught as `nonexistent`
  - with no `math_segments`, `pattern_fire_rate` is 0.0 everywhere (the
    pattern-accept path stays dark without the 4th tuple element — this is
    the thing mathgraph-g8x's driver made reachable but nothing pinned)
  - with `math_segments` wired in: permissive/precise `correct` and
    `sibling` accept rates lift to the published 42.6%/16.5%/11.9%/3.4%, and
    `pattern_fire_rate` on `correct`/`sibling`/others matches 8.5%/2.3%/0.0%
  - wrong_namespace/hallucinated/random accept rates are unchanged (within
    delta) between the patterned and unpatterned runs, matching README's
    "every other corrupted population... is unchanged" claim

9 new tests total (2 + 7).

## Numbers verified against the running code before writing assertions

Ran the exact reproduce commands the README cites, on the checked-in
`mathgraph-data` corpus, before picking any expected value or delta:

```
uv run python -m mathgraph.bench_pfr \
  '{"deploy": "mathgraph-data/artifacts/idx_full", "mathlib_only": "mathgraph-data/artifacts/idx_mathlib", "pattern": "mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex", "len_pivot": 0.75, "mod_weight": 0.1, "typ_weight": 0.15, "prefix_weight": 0.85, "title_boost": 2.5}'
```
→ `lexical_pool`: `{"n": 176, "depth": 10000, "reached": 147, "reach_rate": 0.835, "median_rank": 42}`
→ `combined_calibration`: `{"precision": 1.0, "answered": 3, "correct": 3, "n_present": 176, "n_absent": 174, "n_combined": 350}`

Both match README exactly (0.835, median rank 42, "100%, on 3 answers out of
350").

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m mathgraph.cli verify-bench
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m mathgraph.cli verify-bench --patterns
```
→ without patterns: permissive `35.8%/9.7%/38.1%(n=21)/0.0%/0.0%`, precise
`8.5%/1.1%/0.0%/0.0%/0.0%` — matches README's table exactly.
→ with patterns: permissive correct/sibling `42.6%/11.9%`, precise
`16.5%/3.4%`, `pattern_fire_rate` on correct/sibling `8.5%/2.3%`, all other
populations `0.0%` and unchanged from the no-pattern run — matches README's
"Argument identity" paragraph exactly.

Raw JSON saved during this session at `/tmp/bench_pfr_out.json`,
`/tmp/verify_bench_no_pat.json`, `/tmp/verify_bench_pat.json` (not checked
into the repo; rerun the commands above to reproduce).

Since every number reproduced exactly, the new tests assert the published
values (0.01 tolerance on rates, matching `Benchmark.DELTA`'s existing
precedent in this file; exact equality on integer counts like `n`,
`median_rank`, `answered`, `correct`, and the `n=21` wrong-namespace
population, which are deterministic given the corpus and not sampling
statistics).

## Environment note (not part of this bead, worked around)

`uv run` failed here with `Permission denied` on
`/home/node/.cache/uv`/`.local/share/uv` (owned by `root`, not writable by
the running user) — this is the pre-filed `mathgraph-rq3`. Worked around per-
command with `UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_INSTALL_DIR=/tmp/uv-python
UV_TOOL_DIR=/tmp/uv-tool UV_DATA_DIR=/tmp/uv-data`. Did not touch
`mathgraph-rq3` or attempt a permanent fix — out of this bead's scope.

Also noticed the pre-existing uncommitted `pyproject.toml`/`uv.lock` diff
(adds `pytest>=9.1.1` as a dependency) predates this session and is already
tracked as `mathgraph-1u7` ("contradicting stdlib-unittest policy"). Left
untouched; not this bead.

## Left alone / out of scope

- No production code changed — the bead is specifically "add tests," and
  every number the tests need already reproduces from checked-in code, so
  there was nothing to fix in `bench_pfr.py`, `cli.py`, or `verify.py`.
- Did not add a test for the `combined_calibration`'s exact `tau_cov`/
  `delta_margin` values (0.1708/0.1854) — README doesn't publish those, only
  precision/answered/correct/n; pinning unpublished internals would just add
  a brittle assertion nothing depends on.
- Did not touch `mathgraph-1u7` (pytest dependency) or `mathgraph-rq3` (uv
  cache permissions) — both pre-existing, both already filed, neither is
  this bead.
- Did not touch the other open README-precision beads (`mathgraph-y1e`,
  `mathgraph-c38`, `mathgraph-aeg`) — unrelated surface.

## Verification

Full suite, `MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m
unittest discover tests` (with the `UV_*` env workaround above):

```
.....................................................................................
----------------------------------------------------------------------
Ran 85 tests in 177.770s

OK
```

85 = the previous 76 + 9 new tests, zero failures. Also re-ran the baseline
suite *before* adding any test (to establish ground truth for this session):
`Ran 76 tests in 106.637s / OK` — notably, the "one documented pre-existing
failure" (`test_evaluated_on_the_documented_number_of_statements`, 176≠175)
described in this session's standing objectives **did not reproduce**: it
already passes, meaning a prior session (591d4a9, per `git log`) already
updated it to the current 176. So the actual baseline handed to this bead
was fully green, and it remains fully green with the 9 new tests added.

## What I did not do, and why

- Did not attempt to shrink the `DELTA` tolerance below 0.01 to make the
  tests tighter than `Benchmark`'s existing convention in this file — 0.01
  is this file's established band (see `Benchmark.DELTA`'s docstring
  rationale: wide enough to survive a legitimate scorer improvement, narrow
  enough to catch real drift); inventing a stricter one for the new classes
  only would be inconsistent with no stated reason.
- Did not soften or touch any README wording — nothing needed re-measuring
  or revising; every figure the bead's description named reproduced exactly.

## Unverified

- Nothing left unverified for this bead's own scope. One adjacent thing I
  did *not* independently re-derive: whether `median_rank`==42 is stable
  under `PYTHONHASHSEED` variation the way README:266-268 checked for the
  168/6 absent-arm split — `lexical_pool_stats` only touches `al._score`
  (float32 accumulator, argpartition/argsort), the same code path that
  README's own multi-seed check already covers for the closely related
  `arm_present`/`arm_absent` measurements, so I judged a second independent
  multi-seed check for this specific field to be redundant rather than
  skipped. Flagging in case a future session disagrees.

## Git status at handoff

Not committed, per instructions. File touched by this bead:
- `tests/test_corpus.py` (+138 lines, two new test classes, 9 new tests)

Other modified/untracked files in the tree (`.beads/*`, `README.md`,
`pyproject.toml`, `uv.lock`, `.claude/settings.local.json`) predate this
session — confirmed via `git status` before making any change — and are
unrelated to mathgraph-jvx. Not touched.

Suggested commands (do not run without review):
```
git add tests/test_corpus.py
git commit -m "test_corpus: pin bench_pfr lexical_pool/combined_calibration and verify.evaluate pattern-accept path (mathgraph-jvx)"
```

## Bead status

Claimed and closed as done: `tests/test_corpus.py` now calls
`lexical_pool_stats`, `combined_precision_sweep`, and `verify.evaluate` (both
with and without `math_segments`) and pins every published number the bead
named, all of which independently reproduced from checked-in code+data
before any assertion was written. Full suite green at 85/85, no regressions,
no pre-existing failures encountered.
