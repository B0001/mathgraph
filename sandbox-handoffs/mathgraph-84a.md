# Handoff: mathgraph-84a

QUICKSTART.md:27-28 setup-output numbers (~231k declarations, ~1,071 pairs) were stale.

## What changed

**QUICKSTART.md:26-30** (setup paragraph):

| Figure | Old | New | Justification |
|---|---|---|---|
| declarations scanned | `~231k` | `~242k` | `wc -l /workspace/mathgraph-data/artifacts/mathlib.jsonl` → `241703`. Also reproduced live via `MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -c "from mathgraph.leanscan import write_index; print(write_index('/workspace/mathgraph-data/mathlib4/Mathlib', '/tmp/x.jsonl'))"` → `241703`, matching exactly. |
| paper-prose/declaration pairs | `~1,071` | `~440` | `wc -l /workspace/mathgraph-data/artifacts/blueprint_pairs.jsonl` → `439` (this is the pinned artifact `mathgraph/setup_cmd.py` calibration is fit against — see its own comment "every threshold in cli.py is fitted against these 439"). A fresh harvest via `MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -c "from mathgraph.harvest import harvest; import glob, os; roots=[d for d in glob.glob('/workspace/mathgraph-data/blueprints/*') if os.path.isdir(d)]; pairs, decls = harvest(roots, exclude={'pfr'}); print(len(pairs))"` → `441` (small upstream drift from the pinned 439). Used the rounder "~440" since both 439 and 441 round to it and the paragraph explicitly says the count drifts. |

Also added a sentence pointing at `wc -l artifacts/mathlib.jsonl artifacts/blueprint_pairs.jsonl` as the way to check current counts, since both genuinely drift with upstream mathlib/blueprint commits — this was the bead's suggested fix, not just a static number swap, since a static number would go stale again on the next `mathgraph setup` run against updated upstreams.

## What I left alone, and why

- **README.md:887-893** (`| **total** | **1,071** | **38,897** |`) — untouched, as the bead explicitly instructs. This table is already correctly labeled "pre-length-normalisation-fix" historical and includes a 7th project (`lean4-ergodic-theory`) that isn't in the current `BLUEPRINTS` list in `mathgraph/setup_cmd.py`. It's a different historical experiment's number, not drift in the current pipeline's output — changing it would destroy a legitimately historical, correctly-labeled measurement.
- No other `231`/`1,071`/`1071` occurrences found in QUICKSTART.md after the edit (`grep -n "231\|1,071\|1071k\|175\b" QUICKSTART.md` → empty).
- Confirmed via `grep -rn "231\|1,071\|1071k\|harvest\|blueprint_pairs" tests/*.py` that no test pins either figure — only a skip-guard references `blueprint_pairs.jsonl`'s existence, nothing checks its count. Consistent with the bead's own finding; did not add a new test since the bead didn't ask for one and the fix scope is documentation only.

## Nothing to soften

This bead is a pure numbers-and-wording fix to a quickstart paragraph, not a claim about tool trustworthiness — there was no hedge to weigh softening.

## Test suite

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

```
Ran 85 tests in 170.688s

OK
```

All 85 tests pass — zero failures, including the previously-documented `test_evaluated_on_the_documented_number_of_statements` pre-existing failure. That test (and other numbers) were apparently already fixed by uncommitted work sitting in the working tree from a prior session (`tests/test_corpus.py`, `README.md`, `mathgraph/*.py` all show uncommitted diffs predating this session, under the commit message theme "Re-measure every published number, and say so where they moved" — HEAD is `591d4a9`). That prior work is out of scope for this bead; I did not touch it, only verified the suite is green with it present.

## What I could not verify

- I did not re-run `uv run mathgraph setup` end-to-end from scratch (would re-clone mathlib4 + 6 blueprint repos, several GB of network I/O, ~5-10 min per the doc itself) to confirm the exact printed console values match `241703`/`439` byte-for-byte from a live `setup` invocation. Instead I verified via direct calls to the same underlying functions (`leanscan.write_index`, `harvest.harvest`) that `setup_cmd.py` calls, plus `wc -l` on the artifacts those functions/the last real setup run produced — which is what the prior bead session (mathgraph-84a's author) also did, and is the same reproduction method the bead's own evidence bar was built on. Given `setup_cmd.py:126-154` just calls these functions and logs their return values / line counts directly, I'm confident this is equivalent, but flagging it as not a byte-identical rerun of the CLI command itself.

## What I decided not to do

- Did not touch the unrelated uncommitted changes already in the working tree (`.beads/*`, `.claude/skills/run-mathgraph/SKILL.md`, `README.md`, `mathgraph/adapt.py`, `mathgraph/bench_dense.py`, `mathgraph/bench_pfr.py`, `mathgraph/freeze_bench.py`, `sandbox-prompt.md`, `tests/test_corpus.py`, `.claude/settings.local.json`) — these predate this session (present in git status before I started), are outside mathgraph-84a's scope, and appear to be legitimate uncommitted work from a prior session's own numbers-audit. Not mine to commit, revert, or otherwise adjudicate.
- Did not file a new bead — nothing discovered here fell outside mathgraph-84a's stated scope.

## Git status at handoff

```
$ git status
Changes not staged for commit (relevant to this bead):
  modified:   QUICKSTART.md
(plus pre-existing unrelated uncommitted changes listed above, untouched)
```

Suggested commands for a human to run (not executed by me, per git policy):

```bash
git add QUICKSTART.md
git commit -m "QUICKSTART: update stale setup-output numbers (231k->242k declarations, 1,071->440 pairs)"
# The other uncommitted files are pre-existing, unrelated work from a prior session — review separately.
```

## Bead status

Closing `mathgraph-84a` with the evidence above: QUICKSTART.md's setup paragraph now states numbers matching current reproducible output (241,703 / 439-441, rounded to ~242k / ~440) and points at the exact `wc -l` commands to re-check them, and no longer implies "1,071" is what the documented six-project setup produces.
