# Handoff: mathgraph-0a1

structmatch.py:14's module docstring still asserted the old, unreproduced
"97% / median rank ~250" claim after README.md's "Why" section was already
updated (by mathgraph-5hi) to the re-measured 83.5%/42. Fixed the docstring
to match.

## What changed

`mathgraph/structmatch.py` lines 12-14 (module docstring):

- **Old**: "Reranking rather than first-stage retrieval, because the
  measured bottleneck is ranking: the lexical stage reaches the gold
  declaration 97% of the time and puts it at median rank ~250."
- **New**: "Reranking rather than first-stage retrieval -- though as of the
  2026-08-08 re-measurement (176-statement present arm, StructReranker's
  shipped depth=10000), the lexical stage's pre-rerank pool reaches the gold
  declaration only 83.5% of the time (147/176) and puts it at median rank 42
  when it does, so this is now partly a retrieval problem too, not purely a
  ranking one. See README.md's "Why" section and
  `bench_pfr.lexical_pool_stats` (the function that produces these numbers)
  for detail and reproduction."

**Justifying command** (re-ran it myself rather than trusting the README's
prior transcription of the number):

```
UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_INSTALL_DIR=/tmp/uv-python \
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m mathgraph.bench_pfr \
  '{"deploy": "mathgraph-data/artifacts/idx_full", "mathlib_only": "mathgraph-data/artifacts/idx_mathlib", "pattern": "mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex", "len_pivot": 0.75, "mod_weight": 0.1, "typ_weight": 0.15, "prefix_weight": 0.85, "title_boost": 2.5}'
```

Output's `lexical_pool` field:

```json
{"n": 176, "depth": 10000, "reached": 147, "reach_rate": 0.835, "median_rank": 42}
```

147/176 = 0.835 = 83.5%, median_rank 42, depth 10000 — matches README.md
lines 325-329 exactly. This confirms the number is current, reproducible
output (via `bench_pfr.lexical_pool_stats`), not a copy of an unverified
figure.

I did not carry a date into the code from thin air: 2026-08-08 is both
today's date and the date on mathgraph-5hi (the bead that performed and
recorded this re-measurement, closed today), so it's consistent with the
provenance already established for this number, not a new claim.

## Numbers left alone

None relevant to this bead — the only occurrence in scope was
structmatch.py:14, and it's now fixed. I did not touch README.md (already
correct per mathgraph-5hi) or any other file.

## Hedges considered

None needed softening. The new docstring text preserves the "partly a
retrieval problem too, not purely a ranking one" hedge verbatim from
README.md's own phrasing (README.md:340-343) rather than inventing a
different framing in code that could drift from the doc's language over
time.

## Test suite — final run

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

```
............................................................................
----------------------------------------------------------------------
Ran 76 tests in 102.250s

OK
```

All 76 tests pass — 0 failures, 0 errors. Note: the task's standing context
described one pre-existing failure
(`test_evaluated_on_the_documented_number_of_statements`, expecting 176 but
getting 175). That test's assertion already reads `self.assertEqual(...,
176)` in this tree (tests/test_corpus.py:163) and passes — the corpus/test
were already reconciled by earlier session work before this bead started.
Nothing in this bead's scope touched that test or the corpus size.

## What I did not do, and why

- Did not touch README.md, QUICKSTART.md, or any file outside
  `mathgraph/structmatch.py` — out of scope for mathgraph-0a1, which is
  specifically about the structmatch.py:14 docstring per its acceptance
  criteria. The broader "stale-175 sweep" objective in the standing context
  is background, not this bead's assignment, and prior beads (mathgraph-5hi,
  mathgraph-zzq) already appear to have covered the README occurrences this
  bead references.
- Did not create a new bead for further work — I found no additional
  drifted numbers while making this change; the fix was narrowly scoped to
  one docstring.

## What I could not verify

Nothing left unverified. The number was re-derived from a live run of
`bench_pfr` against the current corpus/index in this container, not taken
on faith from the README or the bead description.

## Git state — ready to commit, not committed

```
$ git status --short mathgraph/structmatch.py
 M mathgraph/structmatch.py
```

Suggested commands (not run, per conservative git policy):

```bash
git add mathgraph/structmatch.py
git commit -m "structmatch.py: update module docstring's lexical-stage stat to match README's re-measured 83.5%/42 (was stale 97%/~250)"
```

`bd close mathgraph-0a1` was run after this handoff was written and the test
suite confirmed at 76/76 passing.
