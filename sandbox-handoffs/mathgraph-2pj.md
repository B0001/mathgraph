# Handoff: mathgraph-2pj

`mathgraph/freeze_bench.py main()` crashes: hardcoded artifact names
`idx_deploy`/`idx_mathlib_only` don't exist.

**Status: closed.** Fixed, reproduced, evidence attached below.

## What was wrong

`freeze_bench.py:152-153` had two bugs stacked on top of each other:

1. Wrong artifact names. The real names built by `setup_cmd.py` are
   `idx_full` (mathlib4 + PFR, the present-arm reference corpus) and
   `idx_mathlib` (mathlib alone, the absent-arm reference corpus) — see
   `mathgraph/setup_cmd.py:181-197` and `mathgraph/cli.py:67`'s `CORPORA`
   list. `idx_deploy`/`idx_mathlib_only` appeared nowhere else in the
   codebase before this fix.
2. No path prefix. `load()` (`mathgraph/index.py:424`) takes a directory and
   looks for `index.pkl.gz` inside it directly. Every other caller
   (`cli.py:70` `_art()`, `tests/test_corpus.py:43` `idx()`) joins the name
   onto `os.path.join(MATHGRAPH_DATA, "artifacts", name)` first.
   `freeze_bench.py` passed the bare string, so it would only ever find an
   index if you happened to run it from inside a directory that itself
   contained an `idx_deploy/` subfolder.

This had already been hit and worked around, not fixed, by the closed bead
mathgraph-q3z (symlinking `idx_full` → `idx_deploy` and `idx_mathlib` →
`idx_mathlib_only` before calling `fb.main()` directly). No bead was filed at
the time to fix the underlying function, and README's "shipped benchmark"
section (~line 1198) kept describing `python -m mathgraph.freeze_bench` as
running standalone with no caveat — it did not.

## The fix

`mathgraph/freeze_bench.py:151-153`:

```python
art_dir = os.path.join(os.environ.get("MATHGRAPH_DATA", "./mathgraph-data"), "artifacts")
deploy = {r["name"] for r in load(os.path.join(art_dir, "idx_full"))["rows"]}
mathlib = {r["name"] for r in load(os.path.join(art_dir, "idx_mathlib"))["rows"]}
```

Mirrors the existing `MATHGRAPH_DATA` default-fallback pattern already used
a few lines above in the same function (for the blueprint glob pattern), and
the artifact-path-join convention used by `cli.py`'s `_art()` and
`tests/test_corpus.py`'s `idx()`.

## Evidence this closes the bead

Ran the exact reproduction command from the bead, with no symlinks and no
monkeypatching, against the real corpus at `/workspace/mathgraph-data`:

```
$ cd /tmp && MATHGRAPH_DATA=/workspace/mathgraph-data uv --project /workspace run python -m mathgraph.freeze_bench
{"present": 176, "absent": 174, "dir": "bench_release"}
```

It wrote `bench_release/{tasks.jsonl,scorer.py,README.md}`. Cross-checked the
printed counts against `tasks.jsonl`'s actual row counts (independent
`json.loads` count over the file, not the same code path that produced the
printed numbers):

```
present 176 absent 174
```

Matches. The generated `bench_release/README.md`'s data card also
substituted `176`/`174` correctly via `string.Template`.

Cleaned up `/tmp/bench_release` after verifying (it's a disposable generated
artifact, not committed to the repo either way — `bench_release/` is
gitignored / produced on demand per README:1199).

## Numbers changed

None in tracked files besides the code fix itself. This bead was a code bug,
not a documentation drift — the two artifact-name strings and the missing
`os.path.join` are the only change to `freeze_bench.py`'s logic:

```diff
-    deploy = {r["name"] for r in load("idx_deploy")["rows"]}
-    mathlib = {r["name"] for r in load("idx_mathlib_only")["rows"]}
+    art_dir = os.path.join(os.environ.get("MATHGRAPH_DATA", "./mathgraph-data"), "artifacts")
+    deploy = {r["name"] for r in load(os.path.join(art_dir, "idx_full"))["rows"]}
+    mathlib = {r["name"] for r in load(os.path.join(art_dir, "idx_mathlib"))["rows"]}
```

I did not touch README.md's "shipped benchmark" section (~line 1197-1222):
it already describes `python -m mathgraph.freeze_bench` as producing
`bench_release/` on demand with no caveat about it being broken, and that
description is now literally true, so nothing there needed correcting. I
checked whether it should additionally document the `MATHGRAPH_DATA`
env var requirement — it doesn't currently, but neither does any other
command described in that README (grepped for `MATHGRAPH_DATA` and
`--data-dir` — no hits describing env-var setup anywhere in README.md), so
adding it here alone would be inconsistent with the doc's existing style and
out of scope for this bead. Left alone.

## Left alone / out of scope, filed separately

`grep -rn "idx_deploy|idx_mathlib_only"` (after my fix) still finds the same
wrong-name pattern in three more places:

- `mathgraph/bench_pfr.py:177` — `main(deploy="idx_deploy",
  mathlib_only="idx_mathlib_only", ...)` (default parameter values)
- `mathgraph/adapt.py:55` — `build(idx_dir="idx_deploy", ...)` (default
  parameter value)
- `mathgraph/bench_dense.py:125,131` — `load("idx_deploy")` /
  `load("idx_mathlib_only")` (hardcoded, not even a parameter)
- `.claude/skills/run-mathgraph/SKILL.md:185-208` documents the
  `idx_deploy`/`FileNotFoundError` failure as a known "gotcha" with a
  symlink workaround, rather than pointing at a fix.

This bead's description and evidence bar were scoped to `freeze_bench.py`
only. I did not touch these — filed **mathgraph-dgd** to track them
(same root cause, same fix pattern, needs a per-call-site check of whether
each default is ever reachable with defaults in normal use vs. always
overridden by a caller before deciding whether it's a live bug or dead code).

## Test suite

Ran the full documented command:

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

Final line, verbatim:

```
Ran 85 tests in 166.810s

OK
```

**85/85 passed, 0 failures.** This is *better* than the "known baseline" of
exactly one pre-existing failure
(`test_evaluated_on_the_documented_number_of_statements`, 176 != 175)
described in the standing session context. That failure is already gone —
not because of anything I did, but because of other uncommitted work already
sitting in the working tree when I started (`tests/test_corpus.py` has a
large uncommitted diff, referencing a different, already-closed bead
`mathgraph-jvx` in its new test docstrings, that updates the expected
statement count to 176 and adds new pinning tests). I did not make or need
to make any test-suite changes myself for this bead — I only verified the
suite is green after my one-file fix.

## What I did not do, and why

- Did not fix the `idx_deploy`/`idx_mathlib_only` pattern in `bench_pfr.py`,
  `adapt.py`, or `bench_dense.py` — out of this bead's stated scope, filed
  as mathgraph-dgd instead of doing it now, per the task instructions ("If
  you discover work outside this bead's scope, file it as a new bead. Do not
  do it now.").
- Did not touch the pre-existing uncommitted changes to `README.md`,
  `tests/test_corpus.py`, `sandbox-prompt.md`, `.beads/*.jsonl` that were
  already in the working tree when I claimed this bead — they belong to
  other work (at least one references bead mathgraph-jvx) and are not part
  of mathgraph-2pj. I left them exactly as I found them.
- Did not investigate or clean up `.claude/settings.local.json` (untracked,
  present before I started) — not related to this bead.
- Did not revisit the `SKILL.md` "gotcha" documentation for the
  `idx_deploy` workaround — rolled into mathgraph-dgd since it only makes
  sense to update once the other three call sites are actually fixed.

## What I could not verify

Nothing outstanding for this bead — reproduction, fix, and full-suite pass
are all directly observed above, not inferred.

## Git state at handoff

Not committed, per git policy (conservative profile, no explicit push/commit
authority granted). `git status --short`:

```
 M .beads/interactions.jsonl      (bd close/claim side effects on this bead + pre-existing)
 M .beads/issues.jsonl            (bd close/claim side effects on this bead + pre-existing)
 M README.md                      (pre-existing, not mine — see above)
 M mathgraph/freeze_bench.py      (mine — the fix described above)
 M sandbox-prompt.md              (pre-existing, not mine)
 M tests/test_corpus.py           (pre-existing, not mine — see above)
?? .claude/settings.local.json    (pre-existing, untracked, not mine)
```

Suggested next commands for a human, scoped to just this bead's change if
they want to commit narrowly:

```bash
git add mathgraph/freeze_bench.py
git commit -m "fix: freeze_bench.py loads idx_full/idx_mathlib via MATHGRAPH_DATA/artifacts, not nonexistent idx_deploy/idx_mathlib_only"
```

(Leaving the other pre-existing modified files for whoever owns that work to
commit separately.)
