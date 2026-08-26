# Handoff: mathgraph-c38

## Bead
mathgraph-c38 — "mathgraph/freeze_bench.py CARD template has a duplicated
paragraph about per-statement corpus"

## What was wrong
`CARD` in `mathgraph/freeze_bench.py` (the data-card template written to
`bench_release/README.md`'s `## Format` section) repeated the same sentence
twice back-to-back with a one-word variation:

```
Each statement names its reference `corpus` — the absent arm must be run
against mathlib alone, with the PFR formalization withheld, or its abstention
labels are meaningless. Each statement names its reference `corpus` — the absent arm must be run
against mathlib alone (PFR formalization withheld) or its abstention labels
are meaningless. Math is flattened to `MATH` in `text` ...
```

Confirmed by reading the file directly (as the bead's author also did);
`git blame` traces the duplication to `d64d368`, the repo's first commit, and
`591d4a9` (the most recent commit touching this file) does not touch this
paragraph. Pure pre-existing documentation drift, unrelated to the 175-sweep.

## Fix
Deleted the first (looser) phrasing, kept the second (tighter) one, per the
bead's own recommendation ("PFR formalization withheld" parenthetical is
tighter than "with the PFR formalization withheld, or"):

```diff
 Each statement names its reference `corpus` — the absent arm must be run
-against mathlib alone, with the PFR formalization withheld, or its abstention
-labels are meaningless. Each statement names its reference `corpus` — the absent arm must be run
 against mathlib alone (PFR formalization withheld) or its abstention labels
 are meaningless. Math is flattened to `MATH` in `text` (this benchmark is deliberately hard;
 formula-aware systems should recover the math from the arXiv source).
```

File: `mathgraph/freeze_bench.py` (single hunk, 2 lines removed). No other
occurrences of the sentence exist in the file (`grep -c "the absent arm must
be run" mathgraph/freeze_bench.py` → `1` after the fix).

## Verification

The bead asked to "re-run `python -m mathgraph.freeze_bench` ... and confirm
the generated README.md's Format section reads cleanly once, not twice."

**Could not do this literally** — `python -m mathgraph.freeze_bench` cannot
complete end-to-end in this environment. It calls
`load("idx_deploy")`/`load("idx_mathlib_only")`, and those index directories
don't exist and nothing in this repo builds them under those names. This is
a separate, already-documented, pre-existing issue —
`.claude/skills/run-mathgraph/SKILL.md` lists `freeze_bench.py` as one of
"four dead entry points" whose default index names "nothing builds," with
the exact `FileNotFoundError: 'idx_deploy/index.pkl.gz'` reproduced here:

```
FileNotFoundError: [Errno 2] No such file or directory: 'idx_deploy/index.pkl.gz'
```

That is out of scope for this bead (it's a benchmark-pipeline wiring bug, not
a documentation-text bug) and I did not touch it. Filed as a separate
observation only — no new bead opened, since the SKILL.md gotcha already
documents it and nothing here changes its status.

**What I verified instead**: rendered the `CARD` template directly via
`string.Template(CARD).substitute(...)` (bypassing the index-loading path,
which is orthogonal to the text fix):

```
uv run python -c "
import string
from mathgraph.freeze_bench import CARD
print(string.Template(CARD).substitute(N_PRES=1, N_ABS=1))
"
```

Output's `## Format` section now reads the sentence exactly once:

```
Each statement names its reference `corpus` — the absent arm must be run
against mathlib alone (PFR formalization withheld) or its abstention labels
are meaningless. Math is flattened to `MATH` in `text` (this benchmark is deliberately hard;
formula-aware systems should recover the math from the arXiv source).
```

This confirms the template itself is fixed; it does not confirm the full
`freeze_bench.main()` pipeline runs (it can't, independently of this fix, for
the reason above).

## Test suite
```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```
Final line (verbatim):
```
Ran 85 tests in 223.684s

OK
```
All tests passed — 0 failures, 0 errors. (Note: the task brief described one
known pre-existing failure, `test_evaluated_on_the_documented_number_of_statements`
expecting 176 vs 175. That test is not failing in the current working tree —
`git status` shows `tests/test_corpus.py` as already modified/uncommitted
from a prior session's 175-sweep work, which appears to have already applied
the fix. That sweep is not this bead's scope and was not touched here beyond
running the suite to confirm the baseline.)

## What I left alone / did not do
- Did not touch the `idx_deploy`/`idx_mathlib_only` dead-entry-point issue —
  out of scope, already documented in SKILL.md's gotchas table.
- Did not touch the "`freeze_bench.py` defines `main` twice (lines 34 and
  144); the second shadows the first" issue also called out in SKILL.md —
  unrelated to the duplicated-paragraph bug this bead is about, and touching
  it risks changing scorer behavior (`main(tasks_path, preds_path)` at line
  34 vs `main(out_dir, pattern)` at line 144), which is a correctness change,
  not a doc-text change. Left for a separate bead if someone wants it.
- Did not modify `tests/test_corpus.py`, README.md, or QUICKSTART.md — none
  of the 175-sweep work is this bead's scope, and the suite is green as-is.

## Unverified
- Whether a *fully built* `bench_release/README.md` (i.e., the actual file
  the CARD template produces once `idx_deploy`/`idx_mathlib_only` exist) also
  reads cleanly — not verifiable in this environment since those indices
  can't be built here. The template-level render above is the closest
  available substitute and is byte-for-byte what `freeze_bench.main()` would
  write into that file's `## Format` section.

## Git status
Single uncommitted change relevant to this bead:
```
M mathgraph/freeze_bench.py
```
(Other pre-existing uncommitted changes in the tree — `.beads/*.jsonl`,
`README.md`, `sandbox-prompt.md`, `tests/test_corpus.py` — predate this
session and were not touched.)

Per git policy: not committing, not pushing. Suggested command for a human
to run:
```
git add mathgraph/freeze_bench.py
git commit -m "freeze_bench: remove duplicated corpus paragraph from CARD template"
```

## Bead status
Closed `mathgraph-c38` — evidence above (template-render check + full green
test suite) satisfies what the bead asked for, modulo the one documented
inability to run the full CLI pipeline in this environment (pre-existing,
out of scope, already tracked in SKILL.md).
