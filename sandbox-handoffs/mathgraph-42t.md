# Handoff: mathgraph-42t

## Bead
`mathgraph-42t` — QUICKSTART.md:43 "+22% recall@5" structural-reranker claim
uses pre-scanner-fix numbers. Claimed, worked, closed in this session.

## What was wrong

QUICKSTART.md:43 said "the structural reranker is worth about +22% recall@5
over lexical alone." That figure was computed from the pre-scanner-fix
corpus (n=175, README.md:930's historical table: lexical 0.320, structural
0.389 → (0.389-0.320)/0.320 = 21.6%, rounds to "22%"). The current corpus is
n=176 and produces different numbers.

## What I verified

Ran the actual benchmark command against the live corpus:

```
UV_CACHE_DIR=/workspace/.uv-cache UV_DATA_DIR=/workspace/.uv-data \
UV_PYTHON_INSTALL_DIR=/workspace/.uv-python \
MATHGRAPH_DATA=/workspace/mathgraph-data uv run mathgraph bench
```

Output:

```json
{
  "lexical": {"n": 176, "recall@1": 0.182, "recall@5": 0.318},
  "+structural": {"n": 176, "recall@1": 0.193, "recall@5": 0.381}
}
```

This matches what's already documented at README/QUICKSTART's bench-output
block exactly (that block, and tests/test_corpus.py's n=176 assertion, had
already been fixed by an earlier session — not this bead's work; I only
confirmed they're still correct by re-running the real command).

Relative recall@5 gain: `(0.381-0.318)/0.318 = 0.19811... = 19.8%`, computed
with `uv run python -c "print((0.381-0.318)/0.318*100)"`. Not 22%.

## Change made

**QUICKSTART.md:43** — old value **+22%**, new value **+20%** (19.8%
rounded), command that justifies it: `uv run mathgraph bench`, formula
`(structural.recall@5 - lexical.recall@5) / lexical.recall@5`.

Chose the bead's second option (rephrase, don't just swap the constant): the
sentence now states the formula and the exact currently-computed value
inline, so the next person who sees this drift again can recompute in one
command instead of having to first figure out where "+22%" came from. Diff:

```diff
 **Rank candidate declarations for an informal statement.** Pass the formulas
 too — they carry more signal than the prose does, and the structural
-reranker is worth about +22% recall@5 over lexical alone.
+reranker is worth about +20% recall@5 over lexical alone (recompute with
+`uv run mathgraph bench`: `(structural.recall@5 - lexical.recall@5) /
+lexical.recall@5`; currently (0.381-0.318)/0.318 = 19.8%).
```

## Numbers left alone, and why

- **README.md:930's n=175 table** — untouched. It's explicitly labelled
  "pre-scanner-fix corpus" and exists for a like-for-like historical
  comparison; changing it would destroy that comparison. Not this bead's
  concern anyway (bead scope was QUICKSTART.md:43 specifically).
- **QUICKSTART.md's bench-output JSON block (n=176, recall figures)** — I
  did not touch this; it was already correct/consistent going into this
  session (part of a prior session's fix, per the modified-but-uncommitted
  tree I found at start). I re-ran the actual bench command and confirmed
  it still reproduces those exact numbers today, so it's live-verified, not
  just assumed.
- I did not go sweep the rest of README.md/QUICKSTART.md for other stale
  figures — the prompt's "objectives" section describes that broader sweep
  as standing context for the repo, not this session's assignment. This
  bead was scoped to the single +22% sentence. If other stale numbers exist
  they should be filed as separate beads (the wider sweep bead(s) appear to
  already be in flight per the git status showing README.md/mathgraph/*.py
  as modified — not investigated by me).

## Hedges/claims I did not touch

None applicable here — this bead is a single numeric claim, not a
directional hedge. I did not soften or alter "neither benchmark admits a
trustworthy operating point" or any other qualitative claim; out of scope
and untouched.

## Test suite

```
UV_CACHE_DIR=/workspace/.uv-cache UV_DATA_DIR=/workspace/.uv-data \
UV_PYTHON_INSTALL_DIR=/workspace/.uv-python \
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

```
Ran 76 tests in 98.412s

OK
```

76/76 pass, including `test_evaluated_on_the_documented_number_of_statements`
— that test's expected value was already changed from 175→176 by a prior
session (visible in `git diff tests/test_corpus.py`), so the previously
documented "one known pre-existing failure" is not present in this run. I
did not touch tests/test_corpus.py myself; I only ran the suite to confirm
the tree is in a clean, all-green state before closing.

Note on environment: `uv run` failed initially with permission errors on
the default cache paths under `/home/node/.cache` and `/home/node/.local`
(owned by root, not writable by the `node` user running this session). I
worked around it by setting `UV_CACHE_DIR`, `UV_DATA_DIR`, and
`UV_PYTHON_INSTALL_DIR` to writable paths under `/workspace/`. This is an
environment quirk, not a code issue — did not change any project config for
it, just exported env vars for my own commands. Future sessions may hit the
same thing.

## What I did not do / could not verify

- Did not investigate why tests/test_corpus.py, README.md, mathgraph/cli.py,
  mathgraph/bench_pfr.py, and .gitignore already show as modified in git
  status at session start — that's other sessions' in-flight work (visible
  in .beads/interactions.jsonl history), not mine, and out of scope for this
  bead. Left as-is.
- Did not verify the deleted `.beads/embeddeddolt/...` Dolt files in git
  status — pre-existing state at session start, not something I touched or
  investigated further, out of scope for this bead.

## Git state at handoff

```
$ git status --short
D  .beads/embeddeddolt/.lock
D  .beads/embeddeddolt/mathgraph/.dolt/config.json
D  .beads/embeddeddolt/mathgraph/.dolt/noms/LOCK
D  .beads/embeddeddolt/mathgraph/.dolt/noms/journal.idx
D  .beads/embeddeddolt/mathgraph/.dolt/noms/manifest
D  .beads/embeddeddolt/mathgraph/.dolt/noms/vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
D  .beads/embeddeddolt/mathgraph/.dolt/repo_state.json
 M .beads/interactions.jsonl
 M .gitignore
 M QUICKSTART.md          <- my change (the +22%->+20% sentence)
 M README.md
 M mathgraph/bench_pfr.py
 M mathgraph/cli.py
 M tests/test_corpus.py
?? .beads/issues.jsonl
?? .claude/settings.local.json
?? sandbox-prompt.md
```

Only `QUICKSTART.md` was modified by me in this session. All other modified/
untracked paths predate this session's work.

Per git policy: not committing, not pushing, not running `bd dolt push`.
Suggested commands for a human to run after review:

```bash
git add QUICKSTART.md
git commit -m "Fix stale +22% recall@5 claim in QUICKSTART.md (mathgraph-42t)"
```

(Leave the other pre-existing modified files for whoever owns that work —
they weren't part of this bead.)

## Bead status

`mathgraph-42t` closed with `--reason` summarizing the fix and verification.
