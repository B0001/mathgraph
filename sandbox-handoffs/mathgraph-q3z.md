# Handoff: mathgraph-q3z

`mathgraph/freeze_bench.py` CARD template hardcodes stale '175 + 174' instead
of interpolating actual counts.

## Status: fixed, evidence attached, test suite clean. Ready to close.

## What was wrong

`freeze_bench.main()` computed real present/absent arm counts into
`n_pres`/`n_abs`, printed them, but wrote the **static** `CARD` string
literal to `bench_release/README.md` verbatim. The CARD hardcoded `"175"` /
`"174"` in three places, so any run against a corpus where the counts had
drifted (they have: the present arm is now 176, per README.md's own
"scanner fix" note) produced a data card that contradicted its own
`tasks.jsonl`.

Separately, `main()`'s default `pattern` argument
(`/home/claude/pfr/blueprint/src/chapter/*.tex`) was an absolute path that
only existed on the original author's machine, so the function couldn't be
run standalone in this container (or presumably anywhere else) without a
monkeypatch — exactly what the previous session that filed this bead had to
do to even test it.

## What I changed

`mathgraph/freeze_bench.py`:

1. **CARD interpolation.** Replaced the three hardcoded `"175"`/`"174"`
   occurrences in the "What it is" section with `$N_PRES`/`$N_ABS` template
   placeholders (`string.Template`, not `.format()` — the CARD body contains
   literal `{...}` in its JSON-format example, which `.format()` would choke
   on). `main()` now does
   `card = string.Template(CARD).substitute(N_PRES=n_pres, N_ABS=n_abs)`
   and writes `card`, not `CARD`, to `README.md`.

2. **Fixed the hardcoded absolute path.** `main()` now takes an optional
   `pattern` argument; when not given, it derives the default from
   `$MATHGRAPH_DATA` (falling back to `./mathgraph-data`, matching the
   convention already used by `cli.py`'s `DEFAULT_DATA`):
   `os.path.join(MATHGRAPH_DATA, "blueprints/pfr/blueprint/src/chapter/*.tex")`.
   This means `main()` is now callable standalone in any environment with a
   `mathgraph-data` checkout, no monkeypatch required.

3. **The "~0.67\*, on 3 answers" baseline row** (the calibrated-abstention
   precision/recall/false-match numbers in the "Baselines" table). This
   number is a separate measured claim that `freeze_bench.py` does not
   compute anywhere in the file (unlike `n_pres`/`n_abs`, which come from the
   loop right above). I did not hardcode a replacement number for it. I
   found, while checking README.md for context, that this is the *exact*
   same figure README.md:304 already documents as having gone stale and
   unreproduced ("previously reported '~67%, on 3 answers out of 349' that
   no script in this repository reproduced"), replaced there by a
   reproducible 100%-on-3/350 figure. Hardcoding *any* specific number into
   this CARD template for a metric the file doesn't compute would just
   recreate the same bug with a new value — the next scorer revision would
   go stale here again with nothing to catch it. So I replaced the row with
   `see note †` and a footnote explaining why, naming the exact reproduction
   command (`python -m mathgraph.bench_pfr`, per README's "Calibration sweep
   over both arms combined" section) instead of asserting a number. The bead
   explicitly offered this as one of two acceptable resolutions
   ("interpolate it too or replace it with a provenance note") — I chose the
   note because computing the real combined-calibration sweep inside
   `freeze_bench.py` would mean importing `Aligner`, `cli.LEX`, and
   `bench_pfr.combined_precision_sweep`/`arm_present`/`arm_absent` and
   re-running the full alignment pass at freeze time, which is a real
   feature addition beyond "fix the CARD template," not a bug fix. Left as a
   candidate for a follow-up bead if wanted (see below).

I did **not** touch the `dense dual-encoder` and `always-answer lexical
top-1` baseline rows — the bead didn't flag them, and I didn't verify them
independently (see "Not verified" below).

## Evidence

Ran the generator for real, against the real corpus, with no monkeypatch
(the whole point of fix #2):

```
export MATHGRAPH_DATA=/workspace/mathgraph-data
mkdir -p /tmp/freeze_test && cd /tmp/freeze_test
ln -sf $MATHGRAPH_DATA/artifacts/idx_full idx_deploy
ln -sf $MATHGRAPH_DATA/artifacts/idx_mathlib idx_mathlib_only
uv run --project /workspace python -c "
import mathgraph.freeze_bench as fb
fb.main(out_dir='out2')
"
```

Output: `{"present": 176, "absent": 174, "dir": "out2"}`

Generated `out2/README.md` now reads:

```
176 + 174 statements from the blueprint of the Polynomial Freiman-Ruzsa
...
- **present arm** (176): ...
- **absent arm** (174): ...
```

Cross-checked against the actual rows written to `out2/tasks.jsonl`
independently of the printed summary (`grep -c` on the `"arm"` field, not
trusting `main()`'s own counters):

```
present rows: 176
absent rows:  174
```

176/174 in the README.md text == 176/174 actual rows in tasks.jsonl. The
mismatch this bead reported no longer exists.

## Test suite

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

```
............................................................................
----------------------------------------------------------------------
Ran 76 tests in 92.662s

OK
```

76/76 pass, 0 failures. Note: the standing instructions for this session
describe one *known* pre-existing failure
(`test_evaluated_on_the_documented_number_of_statements`, `176 != 175`) as
the expected baseline. That test is not failing in this run —
`tests/test_corpus.py` was already showing as modified in `git status`
before I started this bead (untouched by me), so a prior session evidently
already updated that assertion to expect 176. I did not touch
`tests/test_corpus.py`. Whatever fixed that test is outside this bead's
scope; I'm reporting the suite result I actually observed (clean) rather
than the baseline described in the standing prompt, per "a passing test with
a name is evidence."

No test file references `freeze_bench` (`grep -rl freeze_bench tests/`
returns nothing), so there was no existing test to update for this fix.

## What I decided not to do, and why

- Did not interpolate the `~0.67*`/"on 3 answers" baseline number. See #3
  above. Filing this as a follow-up is reasonable if someone wants
  `freeze_bench.py` to compute (not just generate metadata about) the
  combined-calibration sweep at freeze time — that's a real feature, and I
  didn't do it under a bug-fix bead without discussing scope.
- Did not fix the identical hardcoded absolute-path default in
  `bench_pfr.py:178` (`main()`) or `bench_dense.py:122`
  (`blueprint_blocks(...)` call). Same bug shape, but neither is this bead's
  file and neither blocks verifying this fix. Worth a follow-up bead for
  consistency.
- Did not touch the `dense dual-encoder` / `always-answer lexical top-1`
  baseline rows in the CARD table — not flagged by this bead, not verified
  by me either way.
- Did not investigate why `test_corpus.py`'s known failure is now passing —
  out of scope for this bead, noted above as observed fact, not claimed as
  my fix.

## Not verified

- Whether the `dense dual-encoder (docstring-trained)` and `always-answer
  lexical top-1` baseline numbers in the CARD table are current or stale —
  out of this bead's scope, not checked.
- Whether `tests/test_corpus.py`'s modification (present before I started)
  is itself correct — I didn't review it, only observed that with it in
  place the full suite is green.

## Git status (unchanged by me except freeze_bench.py)

`mathgraph/freeze_bench.py` is the only file I edited. Everything else in
`git status` (README.md, QUICKSTART.md, cli.py, bench_pfr.py, structmatch.py,
verify.py, tests/test_corpus.py, etc.) was already modified in the working
tree before I claimed this bead — not my work, not reviewed by me, left
alone.

Per repo git policy: no commit, no push, no `bd dolt push`. Suggested next
commands for a human:

```
git add mathgraph/freeze_bench.py
git commit -m "freeze_bench: interpolate CARD statement counts instead of hardcoding 175/174"
```

(then decide separately what to do with the other pre-existing uncommitted
changes in the tree, which are not part of this bead).

## Bead resolution

Closing `mathgraph-q3z` as fixed: CARD now interpolates real counts, the
counts match generated tasks.jsonl, the previously-hardcoded default path is
fixed so the generator runs without a monkeypatch, and the stale
non-reproducible baseline number is replaced with a provenance note rather
than a new hardcoded value.
