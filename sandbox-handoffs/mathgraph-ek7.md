# Handoff: mathgraph-ek7

**Bead:** README present-arm recall@1 (18.2%) does not match code output (18.8%/18.9%)
**Outcome:** Closed, not a bug. README.md's number is correct; the bug report's
comparison figures came from the wrong code path. No README/code change made.

## What the bead asked

`README.md`'s PFR present-arm table (~line 269) says recall@1 = **18.2%**.
A previous session, running `mathgraph/bench_pfr.py`'s `arm_present()`
directly with the LEX params from `cli.py`, got **18.8%** (0.188), which also
roughly matched `tests/test_corpus.py`'s pinned `EXPECTED['lexical']` of
**18.9%** (0.189, within the test's 1pt tolerance). recall@5 matched exactly
(31.8% both ways). Question: is 18.2% stale and needs updating, or is it
correctly labelled history?

## What I found

Neither. **18.2% is the current, live, correct number**, and it is not the
same measurement as the 18.8%/18.9% figures — those come from a different
code path.

### The two code paths

1. **`uv run mathgraph bench`** (README.md:73's own documented reproduce
   command for this table) → `cli.cmd_bench` (`mathgraph/cli.py:141`).
   For the `"lexical"` label it builds `StructReranker(al, lam=0.9,
   depth=10000)`, sets `rr.lam = 0.0`, and ranks via
   `rr.rank(b.text, b.title, b.math, topk=5)`.
2. **`python -m mathgraph.bench_pfr`**'s `arm_present()`
   (`mathgraph/bench_pfr.py:36`) calls `al.align(b.text, title=b.title,
   topk=5)` directly — no `StructReranker`, and internally
   `Aligner.align` (`mathgraph/align.py:256-258`) uses
   `depth = max(topk, MARGIN_TAIL)` where `MARGIN_TAIL = 10`
   (`align.py:29`), not 10000.

Same query-weighting (`query_weights`), same `Aligner` construction
(`LEX` params, `tau_cov=0`, `delta_margin=0` in both), but a different
`depth` passed into `Aligner._score`'s `np.argpartition`/`np.argsort`
top-k selection (10000 vs 10). recall@5 (the *set* of top-5) is identical
between the two runs; only recall@1 differs — consistent with tie-breaking
among near-equal scores flipping which candidate lands at rank 1 for a
handful of statements, not a real disagreement about which corpus or which
scorer is "right."

### Verification — exact commands and output

```
$ MATHGRAPH_DATA=/workspace/mathgraph-data uv run mathgraph bench
{
  "lexical":     {"n": 176, "recall@1": 0.182, "recall@5": 0.318},
  "+structural": {"n": 176, "recall@1": 0.193, "recall@5": 0.381}
}
```
→ **matches README.md:269-270 exactly** (18.2% / 31.8%).

```
$ MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m mathgraph.bench_pfr \
  '{"deploy": "mathgraph-data/artifacts/idx_full", "mathlib_only": "mathgraph-data/artifacts/idx_mathlib",
    "pattern": "mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex",
    "len_pivot": 0.75, "mod_weight": 0.1, "typ_weight": 0.15, "prefix_weight": 0.85, "title_boost": 2.5}'
# (had to pass this as a single-line JSON string; see mathgraph-fr3 below —
#  the multi-line backslash-continued form printed in README.md:290-294
#  does not actually run under bash)
{
  "present": {"n": 176, "recall@1": 0.188, "recall@5": 0.318, ...},
  ...
}
```
→ reproduces the bead's 18.8%, confirming it's real, but it's a different
metric than the README table cites — `bench_pfr.py`'s own output is only
used in the README for `combined_calibration`, and the README text never
claims `present.recall@1` from that command equals anything.

## Numbers changed

None. README.md:269-270 (18.2% / 31.8%) needed no edit — it already matches
its documented reproduction path exactly.

## Numbers left alone, and why

- README.md:269 `**18.2%**` / `**31.8%**` — current and correct, verified
  above via the exact command README.md:73 tells you to run. Not history,
  not drift.
- README.md:957-964's "PFR present arm (n=175, pre-scanner-fix corpus)"
  table and its 18.9%/32.0% row — explicitly labelled historical (n=175,
  "pre-scanner-fix"), out of this bead's scope, untouched.
- `tests/test_corpus.py`'s `EXPECTED['lexical'] = (0.189, 0.320)` — I did
  **not** touch this. It's stale (it's the old n=175 number, and
  `mathgraph-3gu` already fixed the *n* assertion on line 163 to 176 without
  refitting this tuple), but it currently passes `test_recall_matches_published`
  because 0.182 is within the deliberate 1pt `DELTA` tolerance of 0.189.
  Filed as **mathgraph-7dw** rather than fixed here — updating it wasn't
  what this bead asked for, and I didn't want to touch a shared test file
  for an issue outside ek7's scope.

## Hedges/claims I was tempted to touch, and what I did instead

I considered adding a clarifying sentence next to the `combined_calibration`
reproduce command (README.md:283-295) noting that `bench_pfr.py`'s
`present`/`absent` sub-objects use a different pipeline than the table above
and shouldn't be compared to it directly — that's exactly the confusion that
generated this bead. I did **not** add it: that section belongs to
`mathgraph-aec` (already closed), editing it wasn't part of ek7's assignment,
and the underlying two-pipeline inconsistency is now tracked in
**mathgraph-7dw** where a maintainer can decide whether to unify the
pipelines or just document the difference. Softer option, but keeps this
bead's diff at zero, which felt right for a bead whose actual finding was
"the document is already correct."

## New beads filed (out of ek7's scope, not investigated further here)

- **mathgraph-7dw** — `cli.cmd_bench` and `bench_pfr.arm_present` are two
  different pipelines for "PFR present-arm recall@1" (depth=10000 via
  StructReranker vs depth=10 via `Aligner.align`'s `MARGIN_TAIL`), giving
  0.182 vs 0.188 on the same corpus; `test_corpus.py`'s `EXPECTED['lexical']`
  is stale but currently passes only via tolerance. This is the root cause
  of the confusion that produced mathgraph-ek7 in the first place and will
  likely produce another false-alarm bug report if left alone.
- **mathgraph-fr3** — README.md:290-295's combined-arm reproduce command
  (`uv run python -m mathgraph.bench_pfr '{...}'` split across three lines
  with trailing `\`) does not actually run: inside single quotes, a
  trailing backslash is literal, not a line-continuation, so the resulting
  JSON string contains embedded backslash-newlines and fails to parse
  (`JSONDecodeError: Expecting property name enclosed in double quotes`).
  Confirmed by extracting the exact fenced block and running it verbatim
  under bash.

## Test suite — final line

```
$ MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
Ran 76 tests in 92.962s

OK
```

76/76 passing, zero failures. (The documented baseline failure —
`test_evaluated_on_the_documented_number_of_statements: 176 != 175` — is
already gone in this working tree; it was fixed by a prior session's
uncommitted edit to `tests/test_corpus.py:163`, closed as `mathgraph-3gu`. I
did not touch that file.)

## What I did not do, and why

- Did not edit any files for this bead. The investigation concluded the
  documented number is correct, so per the "fix the code or fix the
  document, never a third" rule, and given neither was wrong, no edit was
  the honest move.
- Did not fix the two-pipeline discrepancy or the stale `EXPECTED` tuple
  (mathgraph-7dw) or the broken reproduce command (mathgraph-fr3) — both
  outside ek7's assignment, filed as separate beads per instructions.
- Did not `git commit`, `git push`, or `bd dolt push` — per git policy. The
  working tree already had substantial uncommitted changes from prior
  sessions (`mathgraph-aec`, `mathgraph-1f3`, `mathgraph-3gu`,
  `mathgraph-etj`) touching `README.md`, `QUICKSTART.md`,
  `mathgraph/bench_pfr.py`, `mathgraph/cli.py`, `tests/test_corpus.py`; I
  left them exactly as found.

## What I could not verify

- Whether the depth-dependent tie-breaking hypothesis (argpartition/argsort
  instability at the depth=10 vs depth=10000 boundary) is the *exact*
  mechanism behind the 0.182-vs-0.188 gap, as opposed to some other subtle
  difference between the two call paths. I traced the code far enough to be
  confident it's a real, reproducible artifact of `depth`/pipeline choice
  and not corpus drift (both numbers reproduce exactly, repeatedly, from
  their respective documented commands), but did not instrument `_score` to
  catch the exact statement(s) whose rank-1 flips. Left as an open question
  in mathgraph-7dw for whoever picks it up.

## Suggested next commands (not run — conservative git policy)

```bash
git status
# review the pre-existing uncommitted diff from mathgraph-aec/1f3/3gu/etj
# (README.md, QUICKSTART.md, mathgraph/bench_pfr.py, mathgraph/cli.py,
#  tests/test_corpus.py) before deciding whether/how to commit it —
# none of it was touched or re-verified by this session beyond what's
# reported above.
```
