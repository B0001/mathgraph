# Handoff: mathgraph-y1e

## Task

README.md's "The shipped benchmark" section (was lines 1202-1209, now
1209-1220 after the edit) claimed `freeze_bench.py`'s data card is "a static
template whose text does not recompute from the corpus it's actually run
on -- its stated counts and baseline numbers can go stale independently of
`tasks.jsonl`." Commit 591d4a9 already fixed the counts half of that claim in
the code; the README hadn't caught up.

## Verification (read, not assumed)

Read `mathgraph/freeze_bench.py` in full (lines 77-187):

- `CARD` (line 77) is a `string.Template` with `$N_PRES`/`$N_ABS`
  placeholders (lines 84, 90, 92), and its own prose already says "These
  counts are computed from the corpus that generated this release's
  tasks.jsonl, not hardcoded" (lines 86-88).
- `main()` computes `n_pres`/`n_abs` (lines 160-177) while writing
  `tasks.jsonl`, then does
  `card = string.Template(CARD).substitute(N_PRES=n_pres, N_ABS=n_abs)`
  (line 179) using the *same* variables, before writing both `tasks.jsonl`
  and the card's `README.md` (lines 180-181).

So: the counts in a generated card cannot drift from that release's
`tasks.jsonl` -- they're substituted from the identical `n_pres`/`n_abs` used
to write it. They can still differ *across* releases/corpora (a card
generated last month vs. today, if the corpus changed), which is a real and
different caveat from "stale template."

The Baselines table's `lexical + calibrated abstention` row (lines 122-136)
is not computed by the script at all -- it's hardcoded to `see note †` with a
footnote (lines 128-136) explaining why and how to reproduce it via
`python -m mathgraph.bench_pfr`. That's "deliberately not computed," not
"goes stale from not recomputing." The bead's proposed reword was correct on
both counts; I applied it.

## Change made

**README.md**, "The shipped benchmark" section (git diff below). Old text
claimed the card's "stated counts and baseline numbers can go stale
independently of `tasks.jsonl`." New text:

- States the counts are templated via `string.Template(CARD).substitute(...)`
  from the same `n_pres`/`n_abs` as `tasks.jsonl`, so they can't drift apart
  *within one release* -- but still move with whatever corpus the generator
  was run against, so a count from an older release's card need not match a
  fresh one; check it against that release's own `tasks.jsonl`.
- States the Baselines abstention row is deliberately left as "see note"
  rather than computed, a different kind of caveat than staleness.
- Keeps the underlying caution: don't trust a number printed inside a
  generated `bench_release/README.md` without checking it against the
  release it came from.

```diff
 Row counts depend on the corpus the generator is run against, and are not
 reproduced here: the present arm has already drifted from 175 to **176**
-statements elsewhere in this document (see above), and `freeze_bench.py`'s
-data card is a static template whose text does not recompute from the corpus
-it's actually run on — its stated counts and baseline numbers can go stale
-independently of `tasks.jsonl`. Treat any counts printed inside a generated
-`bench_release/README.md` as unverified until that template interpolates its
-real numbers; check them against `tasks.jsonl` directly.
+statements elsewhere in this document (see above). `freeze_bench.py`'s data
+card templates its `$N_PRES`/`$N_ABS` counts via `string.Template(CARD)
+.substitute(N_PRES=n_pres, N_ABS=n_abs)`, using the same counts written to
+`tasks.jsonl`, so those two numbers can't drift apart from each other within
+one release — but they still move with whatever corpus the generator was run
+against, so a count quoted from an older `bench_release/README.md` need not
+match a freshly generated one; check it against that release's own
+`tasks.jsonl`. The Baselines table's `lexical + calibrated abstention` row is
+a different case: it is deliberately left as "see note" rather than computed
+by the script at all (with a footnote on how to reproduce it), not a value
+that has gone stale. Either way, don't trust a number printed inside a
+generated `bench_release/README.md` without checking it against the release
+it came from.
```

No number was changed, softened, or deleted -- this was a wording-accuracy
fix, not a re-measurement. The "175 → 176 elsewhere in this document"
sentence was left untouched (still accurate, unrelated to this bead).

## Numbers deliberately left alone

None of the objective-section's 175-sweep items (test_corpus.py:163,
README.md:930/1030/1105, QUICKSTART.md:104-105) were touched -- they are out
of scope for this bead, which is specifically about the freeze_bench.py
staleness claim. Not evaluated this session.

## Pre-existing uncommitted changes in the tree (not mine, left alone)

`git status` at session start already showed `README.md`, `tests/test_corpus.py`,
`.beads/interactions.jsonl`, and `.beads/issues.jsonl` as modified before I
touched anything. Confirmed via `git diff README.md` after my edit: there is
a second, unrelated hunk changing the "present arm, mathlib alone" status
breakdown from "170 unmatched, 4 ambiguous, 0 matched" to "168 unmatched, 6
ambiguous, 0 matched" with a new paragraph citing `mathgraph-p14` and a
re-run methodology (repeated runs, different `PYTHONHASHSEED`, float64
rescoring). That is not part of this bead and I did not write it, verify it,
or touch it. Likewise `tests/test_corpus.py` already had ~138 lines of
changes updating expected counts from 175→176 before I started (this is what
made the "known baseline" pre-existing failure not reproduce -- see below).

## Test suite

```
UV_CACHE_DIR=/workspace/.uv-cache UV_PYTHON_INSTALL_DIR=/workspace/.uv-python \
  MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

```
Ran 85 tests in 200.079s

OK
```

No failures, no errors. This is *better* than the documented "known baseline"
of one pre-existing failure (`test_evaluated_on_the_documented_number_of_statements`,
176 != 175) and a different total test count (85 vs. the prompt's stated 76)
-- both are explained by the pre-existing uncommitted `tests/test_corpus.py`
changes already in the tree before this session started (see above), not by
anything I did. I did not investigate or touch those changes; they are
outside this bead's scope. Flagging here so a reviewer doesn't mistake the
85-vs-76 and 0-vs-1-failure deltas for something I introduced.

Note: `uv run` needed `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` pointed at
workspace-local directories -- the default `~/.cache/uv` and
`~/.local/share/uv` are owned by `root` and not writable by the `node` user
in this container. Using the repo's existing `.uv-cache` / `.uv-python`
directories worked. Not a code issue, just a container quirk worth noting for
the next session.

## What I did not do / could not verify

- Did not re-run `python -m mathgraph.freeze_bench` to generate a real
  `bench_release/` and eyeball the substituted card. The claim closed here
  rests on static reading of the substitution code (line 179) plus the
  matching corpus-write code (lines 160-177), which is direct and sufficient
  for the wording claim at issue (that counts are templated, not hardcoded),
  but I have not visually confirmed the generated file's rendered text.
  Marking this unverified-by-execution, verified-by-code-reading.
- Did not evaluate the 175-sweep or other README/QUICKSTART figures named in
  the standing objective -- out of scope for this bead.
- Did not investigate the pre-existing 170→168 / 4→6 change or the
  `mathgraph-p14` reference -- out of scope, flagged above for whoever owns
  that thread.

## Git state at handoff

```
On branch main, up to date with origin/main.
Changes not staged for commit:
	modified:   .beads/interactions.jsonl
	modified:   .beads/issues.jsonl
	modified:   README.md
	modified:   tests/test_corpus.py
Untracked:
	.claude/settings.local.json
```

Per git policy: did not commit, push, or run `bd dolt push`. Suggested
commands for a human to run, after reviewing the diff (including the
pre-existing hunks not written by this session):

```
git add README.md .beads/interactions.jsonl .beads/issues.jsonl tests/test_corpus.py
git commit -m "..."
git push
bd dolt push
```

## Bead status

`mathgraph-y1e` closed with `--reason` (not a bare close) since the fix was a
targeted reword, not new functionality: counts are now correctly described as
templated-and-verified rather than stale-prone; baseline numbers are now
correctly described as deliberately-not-computed rather than stale.
