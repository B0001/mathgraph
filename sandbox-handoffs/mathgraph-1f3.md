# Handoff: mathgraph-1f3

## Bead
README.md:250-259 PFR absent-arm section: "174 of 175" internally inconsistent
AND stale; status breakdown (167/7/0) no longer matched current run (170/4/0).

## What was wrong

Two independent problems in the "Absent arm" block (README.md, PFR blueprint
section):

1. **Internal arithmetic inconsistency**, visible from the text alone: the
   prose said "174 of 175 statements have no correct answer" (denominator
   175, implying 1 statement already answerable from mathlib alone), but the
   status-breakdown row two lines below summed 167 + 7 + 0 = 174, not 175.
2. **Drift from current code**: even the internally-consistent total (174)
   didn't match what the code produces today.

## Reproduction command (run verbatim from the bead)

```bash
export UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_INSTALL_DIR=/tmp/uv-python \
       UV_DATA_HOME=/tmp/uv-data XDG_DATA_HOME=/tmp/uv-data XDG_CACHE_HOME=/tmp/uv-cache
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -c "
from mathgraph.bench_pfr import blueprint_blocks, arm_absent
from mathgraph.align import Aligner
from mathgraph.index import load
from mathgraph.cli import GRAPH_THRESHOLDS
import os
ART = os.path.join(os.environ['MATHGRAPH_DATA'], 'artifacts')
blocks = blueprint_blocks('/workspace/mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex')
al = Aligner(load(os.path.join(ART,'idx_mathlib')), **GRAPH_THRESHOLDS)
out = arm_absent(al, blocks)
print('total annotated blocks:', len(blocks))
print('absent-arm n:', out['n'], 'status:', out['status'])
print('already answerable from mathlib alone:', len(blocks) - out['n'])
print('correct_abstention:', out['correct_abstention'], 'false_match_rate:', out['false_match_rate'])
"
```

Output (this run, this container):

```
total annotated blocks: 179
absent-arm n: 174 status: {'matched': 0, 'ambiguous': 4, 'unmatched': 170}
already answerable from mathlib alone: 5
correct_abstention: 1.0 false_match_rate: 0.0
```

This exactly matches the numbers the bead predicted (170/4/0, denominator
179, 5 already-answerable) — confirmed independently, not taken on the
bead's word.

Note: `uv run` failed at first with `Permission denied` writing to
`/home/node/.cache/uv` and `/home/node/.local/share/uv` (both owned by
`root`, not writable by `node`). Fixed by redirecting `UV_CACHE_DIR`,
`UV_PYTHON_INSTALL_DIR`, `UV_DATA_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME` to
`/tmp/...`. This is an environment/container issue, not a code issue — noting
it here in case it recurs for the next session, but it's out of this bead's
scope and I did not file a bead for it (container-specific, not repo state).

## Change made

`README.md`, the "Absent arm" paragraph and its table (previously lines
254-261, now 254-262 after the edit added one line):

| | old | new |
|---|---|---|
| prose denominator | "174 of 175 statements" | "174 of the 179 statements" |
| prose parenthetical | (none — this was the source of the inconsistency) | "(5 already have an answer in mathlib alone)" |
| status breakdown | "167 unmatched, 7 ambiguous, 0 matched" | "170 unmatched, 4 ambiguous, 0 matched" |

`correct_abstention` (100%) and `false_match_rate` (0%, shown as "false
matches: 0") were confirmed unchanged by the same run and left alone, per the
bead.

Diff:

```diff
-**Absent arm** — only mathlib indexed, so 174 of 175 statements have no
-correct answer anywhere in the index:
+**Absent arm** — only mathlib indexed, so 174 of the 179 statements have no
+correct answer anywhere in the index (5 already have an answer in mathlib
+alone):
 
 | metric | value |
 |---|---|
 | correct abstention | **100%** |
 | false matches | **0** |
-| status breakdown | 167 unmatched, 7 ambiguous, 0 matched |
+| status breakdown | 170 unmatched, 4 ambiguous, 0 matched |
```

I did not adopt the bead's suggestion to say "179 annotated statements is the
pool" as a rewritten opening sentence — the existing sentence just above the
block ("179 annotated statements, split into two arms.", README.md:252)
already states that pool size and wasn't touched, so restating it inside the
Absent-arm sentence would be redundant. Chose to fold "179" into the existing
sentence structure and add a parenthetical for the 5-count instead, which
delivers the same information the bead asked for with a smaller diff.

## What I deliberately left alone

- `tests/test_corpus.py:163` (`assertEqual(... , 175)`, actual 176) — this is
  the repo's documented one known-good pre-existing failure, not in scope for
  this bead, and not touched.
- The "combined-arm calibration sweep" text (README.md ~lines 16, 283-311)
  and the `mathgraph/bench_pfr.py` `combined_precision_sweep` addition — these
  were **already present, uncommitted, in the working tree** when I started
  (not something I wrote). `git log`/`bd list --status=closed` show they're
  the finished output of a separate, already-closed bead
  (`mathgraph-aec`, "combined-arm calibration-sweep figure ('3 answers out of
  349') has no reproducing command..."). Out of scope for mathgraph-1f3; I
  did not touch, re-verify, or take credit for that diff. It's still sitting
  uncommitted in the tree for a human to review/commit alongside this change.
- Every other `175`/`174`/`167`/`7` occurrence in README.md and QUICKSTART.md
  — each one is already covered by its own filed bead (mathgraph-3gu, -etj,
  -036, -2zj, -42t, -q3z, -ek7, -zzq per `bd list --status=open`). Not this
  bead's job; did not touch them.

## Verification

Full suite, run after the edit:

```bash
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

```
...F........................................................................
======================================================================
FAIL: test_evaluated_on_the_documented_number_of_statements (test_corpus.Benchmark.test_evaluated_on_the_documented_number_of_statements)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/tests/test_corpus.py", line 163, in test_evaluated_on_the_documented_number_of_statements
    self.assertEqual(self.got["lexical"][2], 175)
AssertionError: 176 != 175

----------------------------------------------------------------------
Ran 76 tests in 91.767s

FAILED (failures=1)
```

76 tests, exactly the one documented pre-existing failure (176 != 175, a
different stale-175 site tracked by mathgraph-3gu), nothing else. Known-good
state confirmed — no regression introduced by this change.

## What I could not verify

Nothing outstanding. The reproduction command in the bead was run verbatim
(modulo the `UV_CACHE_DIR` environment fix above) and its output matches the
new README text exactly, digit for digit.

## Bead status

Claimed and closed as `mathgraph-1f3` — evidence above satisfies the bead's
stated closing criterion ("re-run the script above and confirm every number
in the updated paragraph matches its output").

## Git state — NOT committed, per policy

```
 M README.md   (this change, plus the pre-existing uncommitted mathgraph-aec diff described above)
 M mathgraph/bench_pfr.py   (pre-existing, mathgraph-aec, not mine)
 M .gitignore   (pre-existing, not mine)
 M .beads/interactions.jsonl
 D  .beads/embeddeddolt/...   (pre-existing deletions, not mine)
?? .beads/issues.jsonl
?? .claude/settings.local.json
?? sandbox-prompt.md
?? sandbox-handoffs/mathgraph-1f3.md
```

Suggested commands for a human to run (not executed by me):

```bash
git add README.md
git commit -m "docs: fix stale/inconsistent PFR absent-arm numbers (mathgraph-1f3)"
# The mathgraph-aec diff (bench_pfr.py, other README.md hunks, .gitignore)
# is separate completed work from a prior closed bead and can be committed
# independently — review it on its own before combining.
```
