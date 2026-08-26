# Handoff: mathgraph-etj

QUICKSTART.md:104-105 example bench output was the pre-scanner-fix numbers
(n=175), not what `uv run mathgraph bench` produces today (n=176). Fixed.

## What changed

**QUICKSTART.md:104-105** — replaced the "Expected, on the held-out PFR
blueprint" JSON block.

- Old: `{"lexical": {"n": 175, "recall@1": 0.189, "recall@5": 0.32}, "+structural": {"n": 175, "recall@1": 0.2, "recall@5": 0.389}}`
- New: `{"lexical": {"n": 176, "recall@1": 0.182, "recall@5": 0.318}, "+structural": {"n": 176, "recall@1": 0.193, "recall@5": 0.381}}`
- Justifying command (run in this container, `MATHGRAPH_DATA=/workspace/mathgraph-data`):

  ```
  uv run mathgraph bench
  ```

  Actual stdout:

  ```json
  {
    "lexical": {"n": 176, "recall@1": 0.182, "recall@5": 0.318},
    "+structural": {"n": 176, "recall@1": 0.193, "recall@5": 0.381}
  }
  ```

  This is a byte-for-byte match to the new QUICKSTART block (modulo JSON
  pretty-printing whitespace, which the doc already compresses onto two
  lines by convention). It also matches README.md:937's already-current
  "18.2 / 31.8 and 19.3 / 38.1" figures, which needed no change.

## What I left alone, and why

- `tests/test_corpus.py:163` — the one documented pre-existing failure
  (asserts 175, gets 176). Out of scope for this bead per the standing
  instructions; confirmed it's still the *only* failure after my change (see
  test run below), so I did not touch it.
- `README.md:930` — table explicitly labelled "n=175, pre-scanner-fix
  corpus". Correctly labelled history; left alone.
- `README.md:1030`, `README.md:1105` and other `175`/combined-arm/precision
  material, and the modified `mathgraph/bench_pfr.py` — these were already
  modified in the working tree (uncommitted) when I started this session,
  evidently from a prior/different session's work on the broader "stale-175
  sweep" objective, not from this bead. `mathgraph-etj` is scoped to
  QUICKSTART.md:104-105 only ("Do only this bead"), so I did not inspect,
  verify, or alter that pre-existing README/bench_pfr.py diff. Flagging it
  here so whoever picks up the broader sweep knows it's mid-flight and
  uncommitted, not mine.
- No other `175` occurrences remain in QUICKSTART.md (`grep -n "175"
  QUICKSTART.md` after the edit returns nothing).

## Hedges / claims I did not touch

None. This bead is a single number swap justified by direct command output;
no narrative hedge in README.md or QUICKSTART.md needed reconsideration for
this specific fix.

## Test suite — final run

```
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
Ran 76 tests in 90.792s

FAILED (failures=1)
```

Exactly the one documented pre-existing failure. Nothing else broke.

## What I could not verify

Nothing outstanding for this bead — the fix is a direct copy of live command
output into the doc, and the test suite confirms no regression. The
pre-existing README.md/bench_pfr.py working-tree diff (see above) is
unverified by me and out of scope; I did not run bench_pfr.py's new
`combined_precision_sweep` path or check its README claims.

## Environment note (not part of the bead, for whoever runs this next)

`uv run` failed initially in this container with permission errors against
`/home/node/.cache/uv` and `/home/node/.local/share/uv` (owned by root, not
writable by the `node` user running the session). Worked around locally with:

```
export UV_CACHE_DIR=/tmp/uv-cache UV_DATA_DIR=/tmp/uv-data UV_PYTHON_INSTALL_DIR=/tmp/uv-python
mkdir -p $UV_CACHE_DIR $UV_DATA_DIR $UV_PYTHON_INSTALL_DIR
```

Didn't touch the container's actual cache ownership since that's
infrastructure, not this bead.

## Git status — ready to commit, not committed

Per repo git policy, I did not commit or push. Changed by me:

- `QUICKSTART.md` (the fix above)

Pre-existing, not mine (see "What I left alone" above):

- `README.md`, `mathgraph/bench_pfr.py` (uncommitted from a prior session)
- `.beads/interactions.jsonl`, `.gitignore`, `.beads/issues.jsonl` (beads
  bookkeeping)
- deleted `.beads/embeddeddolt/...` files (pre-existing at session start)

Suggested commands for a human to run:

```bash
git add QUICKSTART.md
git commit -m "docs: fix stale n=175 bench output in QUICKSTART.md to current n=176"
# review the separate README.md / bench_pfr.py working-tree diff independently
# before deciding whether to commit it — it is not part of this bead
```

## Bead status

Closed `mathgraph-etj` — evidence above (command output diff, test suite at
known-good state) satisfies the bead's stated closing criteria.
