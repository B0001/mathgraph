# Handoff: mathgraph-3gu

## Bead
`test_corpus.py:163 asserts stale PFR present-arm n=175; actual is 176` — bug, P1.

## What was wrong
`tests/test_corpus.py::Benchmark.test_evaluated_on_the_documented_number_of_statements`
asserted `self.got["lexical"][2] == 175`. The present arm computed against
`idx_full` is actually 176 statements — this is the one pre-existing failure
documented as the known baseline, and README.md:269 already documents 176 as
current ("as of the scanner fix below, not the 175 every table before it
reports"). The test was the stale party, not the corpus.

## Changes made

| File | Line | Old | New | Justification |
|---|---|---|---|---|
| `tests/test_corpus.py` | 163 | `self.assertEqual(self.got["lexical"][2], 175)` | `..., 176)` | `MATHGRAPH_DATA=/workspace/mathgraph-data uv run mathgraph bench` prints `{"lexical": {"n": 176, ...}}` against the current corpus; matches README.md:269. |
| `tests/test_corpus.py` | 128 (class docstring) | "~0.6pt that a single statement moves at n=175" | "...at n=176" | Consistency with the corrected n. Sanity-checked: 1/176 ≈ 0.568%, still rounds to "~0.6pt", so the tolerance rationale in the docstring is unaffected by the n correction — only the cited n was stale. |

Nothing else in the file was touched. Per the bead's explicit instruction,
`tests/test_corpus.py:214` (the "439 blueprint pairs" reference) was left
alone — that's a different corpus (non-PFR blueprint pairs) and out of scope
for this bead.

## Numbers deliberately left alone (out of scope for this bead)
This bead was scoped to exactly this one assertion + its docstring reference.
The broader "stale-175 sweep" across README.md/QUICKSTART.md described in the
standing session context is a separate, larger effort not covered by
mathgraph-3gu, and I did not touch README.md or QUICKSTART.md. If that sweep
is still needed, it should be its own bead (check whether one already exists
before filing a new one).

## Verification

Environment note: `uv run` initially failed with
`error: Failed to initialize cache at /home/node/.cache/uv: Permission denied`
because `/home/node/.cache/uv` and `/home/node/.local/share/uv` are owned by
`root` and not writable by the `node` user in this container. Worked around
by pointing uv's cache/python-install dirs at `/tmp`:

```bash
export UV_CACHE_DIR=/tmp/uv-cache
export UV_PYTHON_INSTALL_DIR=/tmp/uv-python
export XDG_DATA_HOME=/tmp/uv-data
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

Final test-run line (verbatim):

```
Ran 76 tests in 91.407s

OK
```

Zero failures, including the previously-failing
`test_evaluated_on_the_documented_number_of_statements`. This matches the
bead's closing evidence requirement exactly.

## What I did not do / could not verify
- Did not investigate or fix the `/home/node/.cache/uv` permission issue
  itself (root-owned directories) — worked around it via env vars instead
  of touching filesystem permissions, since that's outside this bead's
  scope and not something to "fix" via sudo/chown without being asked.
- Did not re-run the broader README/QUICKSTART "175 sweep" — out of scope,
  see above.
- Did not commit or push, per git policy (conservative profile, no explicit
  authority granted).

## Git status / suggested next commands

```
 M tests/test_corpus.py
```

Suggested commands for a human to run (not executed by me):

```bash
git add tests/test_corpus.py
git commit -m "test_corpus: fix stale n=175 assertion, current present arm is 176"
```

## Bead status
Claimed and closed as `mathgraph-3gu` with the evidence above (76/76 tests
pass, only the target assertion changed).
