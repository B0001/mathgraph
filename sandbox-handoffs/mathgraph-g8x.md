# mathgraph-g8x handoff

## Bead
README.md verify-layer argmatch fire-rate table (8.6%/0.6%/0.0%) and
34.9%→41.7% pattern-augmented accept rate had no reproducing driver.

## Outcome: fixed the code, then fixed the document to match

Picked option (a) from the bead: extended `mathgraph/cli.py`'s `verify-bench`
with a `--patterns` flag that builds gold pairs carrying `math_segments`
(`b.math`, the same LaTeX-formula extraction `cmd_bench` already uses) and
calls `verify.evaluate()` with them, so `Verifier.verify`'s formula-pattern
accept path actually fires. Re-measured the real numbers and rewrote the
README paragraph to match — the real numbers are **not** the old ones.

## Code changes

- `mathgraph/verify.py::evaluate()` — now accepts 4-tuple gold pairs
  `(text, title, gold, math_segments)` in addition to the existing 3-tuple
  form (backward compatible: the plain `verify-bench` path still passes
  3-tuples and is byte-for-byte unaffected). Passes `math_segments` through
  to `Verifier.verify()` and adds a `pattern_fire_rate` field per population,
  computed from `Verdict.reasons` containing `"formula pattern match"`.
- `mathgraph/cli.py::cmd_verify_bench()` — added `--patterns` flag. Without
  it, behavior and output are unchanged (verified below). With it, gold pairs
  carry `b.math` and the pattern-accept path is live.
- `mathgraph/cli.py::main()` — registered `--patterns` on the `verify-bench`
  subparser.

No other caller of `verify.evaluate()` exists in the repo (`grep -rn
"evaluate("` confirms), so the signature widening is safe.

## Numbers changed in README.md (~line 1045-1074, "Argument identity")

Command that now regenerates this section:
`MATHGRAPH_DATA=/workspace/mathgraph-data uv run mathgraph verify-bench --patterns`
(raw output saved in this session at `/tmp/verify_bench_patterns.json`
during the session; rerun to reproduce — not checked into the repo).

| claim | old (unreproducible) | new (measured, `verify-bench --patterns`, seed=0) |
|---|---|---|
| fire rate, correct | 8.6% | **8.5%** |
| fire rate, sibling | 0.6% | **2.3%** |
| fire rate, wrong-namespace/hallucinated/random | 0.0% each | 0.0% each (unchanged) |
| fire-rate ratio (correct : hardest corruption) | ~14:1 | **~3.7:1** |
| permissive accept, correct: baseline → patterns | 34.9% → 41.7% | 35.8% → **42.6%** |
| precise accept, correct: baseline → patterns | (not stated) | 8.5% → **16.5%** |
| permissive accept, sibling: baseline → patterns | "unchanged" | 9.7% → **11.9%** (moves) |
| precise accept, sibling: baseline → patterns | (not stated) | 1.1% → **3.4%** (moves) |
| "free recall at held precision" | claimed | **false on current data** — sibling false-accept rises; text now says "not free" |
| ladder-summary line (~line 1074) | "+7pts of verification recall for free" | "+7pts of verification recall at a real but smaller sibling-false-accept cost" |

The permissive `correct` baseline (35.8%, not 34.9%) and its delta magnitude
(+6.8pts either way) match what mathgraph-2zj already established for that
cell — i.e. the *lift* the pattern path buys was directionally right in the
old text, but the *ratio* claim (14:1) and the *"unchanged"* claim on sibling
were not, and neither reproduces on the current 176-statement corpus. I did
not soften this to look better: the sibling fire rate is genuinely ~4x higher
than previously claimed, and "every corrupted population unchanged" is
genuinely false (sibling moves in both profiles). This is a case where a
number wired to look purely positive turned out weaker under a real driver —
reported it exactly as measured, per this repo's standard.

## Left alone (out of scope / already correct)

- The 5-population accept-rate table itself (~line 1097-1104, 35.8%/9.7%/
  38.1%/0.0%/0.0% etc.) — this is the pre-pattern baseline `verify-bench`
  (no flag) already reproduces; confirmed it still matches exactly
  (`mathgraph verify-bench` output checked before touching anything).
  Untouched.
- `mathgraph-2zj`'s provenance note directly above that table ("this driver
  did not exist before mathgraph-2zj...") — still accurate, left as-is.
- Everything else the standing objectives mention (175→176 sweep elsewhere
  in README/QUICKSTART, `bench_pfr.py`, `structmatch.py`) — those are other
  sessions' work already present in the uncommitted tree (`git status` showed
  them modified before I started); not this bead's scope, not touched by me.

## Verification

- `MATHGRAPH_DATA=/workspace/mathgraph-data uv run mathgraph verify-bench`
  (no flag) reproduces 35.8%/9.7%/38.1%/0.0%/0.0% (permissive) and
  8.5%/1.1%/0.0%/0.0%/0.0% (precise) — matches the existing table exactly,
  confirming the `--patterns` addition didn't disturb the existing path.
- `MATHGRAPH_DATA=/workspace/mathgraph-data uv run mathgraph verify-bench --patterns`
  run twice, identical output both times (seed=0, deterministic) — the exact
  numbers now in the README.
- Full suite: `MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m
  unittest discover tests` → **`Ran 76 tests in 90.835s / OK`** — all pass,
  including `test_evaluated_on_the_documented_number_of_statements`, which
  the standing objectives' doc described as the one known pre-existing
  failure (176≠175). That fix was already present in the uncommitted tree
  from a prior session (`tests/test_corpus.py` EXPECTED/175→176 already
  edited) before I made any change; I did not touch that test. Current state
  is fully green, better than the documented baseline of "one known failure."

## What I did not do, and why

- Did not touch the 5-population table or its surrounding provenance note —
  correct and already reproducible, not this bead's concern.
- Did not attempt to restore the old 14:1 ratio or "unchanged" framing by
  tuning `tau_pat` or anything else — the bead asks for a reproducing driver
  and honest numbers, not for the old numbers to come true. Changing
  thresholds to chase a stale figure would be exactly the kind of "quietly
  update the document to keep the number" move the repo's standard forbids.
- Did not add a `--patterns` default-on behavior to plain `verify-bench` —
  that would silently change the existing, already-verified (mathgraph-2zj)
  pre-pattern baseline table's meaning. Kept it opt-in via flag so both
  measurements stay independently reproducible from one command.

## Unverified

- Nothing left unverified in-scope. The one thing I did not independently
  re-derive is `pattern_score`'s/`tau_pat`'s calibration justification
  (`tau_pat=0.25` in `Verifier.__init__`) — that predates this bead and
  isn't part of what mathgraph-g8x asked to reproduce; flagging in case a
  future session wants to check *that* number's provenance too.

## Git status at handoff

Not committed, per instructions. Files touched by this bead:
- `mathgraph/verify.py`
- `mathgraph/cli.py`
- `README.md`

Other modified/untracked files in the tree predate this session (see
"Left alone" above) and are unrelated to mathgraph-g8x.

Suggested commands (do not run without review):
```
git add mathgraph/verify.py mathgraph/cli.py README.md
git commit -m "verify-bench: add --patterns driver, reproduce argmatch fire-rate table (mathgraph-g8x)"
```

## Bead status

Claimed and closing as done: the missing driver now exists
(`mathgraph verify-bench --patterns`), the README paragraph reflects real
measured numbers with the command that produces them, and the full test
suite is green (76/76).
