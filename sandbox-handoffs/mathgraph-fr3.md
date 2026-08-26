# Handoff: mathgraph-fr3

## Bug

README.md's "Calibration sweep over both arms combined" reproduce command
(originally README.md:290-295) put a multi-line JSON object inside a single
pair of single quotes, with `\` at the end of each interior line. In
bash/sh, a trailing backslash is only a line-continuation *outside* quotes;
inside single quotes it's a literal backslash-newline, which lands inside the
JSON string and breaks `json.loads`.

## Confirmed before touching anything

Extracted the command exactly as it appeared in README.md and ran it verbatim:

```
uv run python -m mathgraph.bench_pfr \
  '{"deploy": "mathgraph-data/artifacts/idx_full", "mathlib_only": "mathgraph-data/artifacts/idx_mathlib", \
    "pattern": "mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex", \
    "len_pivot": 0.75, "mod_weight": 0.1, "typ_weight": 0.15, "prefix_weight": 0.85, "title_boost": 2.5}'
```

Result:

```
json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 105 (char 104)
```

Matches the bead's claim exactly — bug reproduced, not assumed.

## Fix

Collapsed the JSON argument onto a single line, keeping the single quoting
(so the whole thing is still one `sys.argv[1]`) and keeping the one legitimate
backslash-continuation (the line break between `bench_pfr \` and the quoted
JSON), which is outside the quotes and therefore a real shell continuation.

New command block (current README.md:290-293):

```
uv run python -m mathgraph.bench_pfr \
  '{"deploy": "mathgraph-data/artifacts/idx_full", "mathlib_only": "mathgraph-data/artifacts/idx_mathlib", "pattern": "mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex", "len_pivot": 0.75, "mod_weight": 0.1, "typ_weight": 0.15, "prefix_weight": 0.85, "title_boost": 2.5}'
```

No other README/QUICKSTART changes made — those numbers were already
modified in the working tree by earlier session(s) working the "stale-175
sweep" objective, which is out of this bead's scope. `git status` showed
README.md as already `M` (modified, uncommitted) before I made any edit; my
diff against that pre-existing state is exactly the one-line JSON collapse
shown above and nothing else.

## Verification (acceptance criteria)

Acceptance criteria: "Copy-pasting the exact fenced command block in
README.md, unmodified, from a clean shell reproduces the documented
combined_calibration output (100%, 3/350) without manual editing."

Extracted the exact current fenced block with `sed -n '291,292p' README.md`
into a script and ran it unmodified:

```bash
export MATHGRAPH_DATA=/workspace/mathgraph-data
bash /tmp/repro_cmd.sh    # contents == README.md:291-292, byte for byte
```

Tail of output:

```json
  "combined_calibration": {
    "precision": 1.0,
    "answered": 3,
    "correct": 3,
    "tau_cov": 0.1708,
    "delta_margin": 0.1854,
    "n_present": 176,
    "n_absent": 174,
    "n_combined": 350
  }
```

`precision: 1.0` = 100%, `answered: 3` / `n_combined: 350` = "3 answers out
of 350" — matches the documented figure exactly. Acceptance criteria met.

## Environment note (not part of the bug, but needed to run anything)

This container's `uv` defaults to cache/python-install dirs under
`/home/node/.local/share/uv` and `/home/node/.cache/uv`, both owned by
`root` with no write access for the `node` user — `uv run` fails outright
with permission errors until you redirect it:

```bash
export UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_INSTALL_DIR=/tmp/uv-python
mkdir -p /tmp/uv-cache /tmp/uv-python
uv sync
```

This is an environment quirk of this sandbox, not a repo bug — did not file
a bead for it since the run-mathgraph skill's documented invocations work
fine once `uv`'s cache dirs point somewhere writable, and a different
container/host may not have this problem at all. Mentioning it here only so
the next reader isn't confused by an unrelated permission error while trying
to reproduce the fix above.

## Test suite

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

```
Ran 76 tests in 98.326s

OK
```

All 76 pass, including `test_evaluated_on_the_documented_number_of_statements`
— the "one pre-existing failure" described in the standing task context is
not present in the current working tree (it was already fixed by whatever
prior session left README.md/tests/test_corpus.py in their current modified,
uncommitted state before this session started). No failures at all right
now, so the suite is at (better than) the known-good baseline.

## What I did not do

- Did not touch any other occurrence of `175`/`349` in README.md or
  QUICKSTART.md — that sweep was already underway in the uncommitted working
  tree from a prior session and is a different bead's scope
  (mathgraph-fr3 is only the shell-quoting bug in the combined-arm reproduce
  command).
- Did not commit or push, per the repo's git policy and this session's
  instructions.
- Did not file a bead for the `uv` cache/permissions issue — judged it an
  artifact of this specific sandbox container, not a repo defect worth
  tracking.

## What I could not verify

- Whether the pre-existing baseline failure
  (`test_evaluated_on_the_documented_number_of_statements: 176 != 175`)
  described in the standing task context was ever real in *this* checkout,
  or whether it was already resolved before this session began. The working
  tree already had `tests/test_corpus.py` modified (uncommitted) when I
  started, and it now asserts 176 and passes. I did not attempt to
  reconstruct the pre-modification state to check — out of scope for this
  bead, and doing so would risk disturbing another session's in-progress
  work.

## Git status at handoff

```
modified:   .beads/interactions.jsonl   (bd bookkeeping)
modified:   .gitignore
modified:   QUICKSTART.md
modified:   README.md                   <- includes this bead's fix, mixed with prior session's stale-175 sweep edits
modified:   mathgraph/bench_pfr.py
modified:   mathgraph/cli.py
modified:   tests/test_corpus.py
untracked:  .beads/issues.jsonl, .claude/settings.local.json, sandbox-prompt.md
```

Per git policy: no commit, no push, no `bd dolt push` performed. Suggested
next commands for a human:

```bash
git add README.md   # at minimum, for this bead's fix
git commit -m "Fix shell-quoting bug in combined-arm bench_pfr reproduce command"
```

(Note README.md's diff also carries the unrelated prior-session edits; a
human reviewer should decide whether to split that commit.)

## Bead status

`bd close mathgraph-fr3` — acceptance criteria verified directly (command
reproduces `combined_calibration` = 100%, 3/350, byte-for-byte from the
current README.md), test suite green (76/76, no failures).
