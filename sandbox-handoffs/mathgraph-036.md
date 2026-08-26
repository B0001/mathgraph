# mathgraph-036 handoff

## Bead
README.md "The shipped benchmark" section (line ~1130-1133 at session start,
now 1130-1148) described `bench_release/` as an existing, already-frozen
artifact with fixed counts ("175 present-arm + 174 absent-arm statements").
No such directory exists anywhere in this checkout or its git history.

## What I verified before touching anything

- `find /workspace -iname "*bench_release*"` and `find / -maxdepth 4 -iname
  "*bench_release*"` — no hits. `bench_release/` is not a checked-in or
  otherwise-present artifact in this container.
- `git log --all -- bench_release/` — no hits (repeat of the prior session's
  check, confirmed again).
- `git diff mathgraph/freeze_bench.py` / `git status --short
  mathgraph/freeze_bench.py` — empty. The generator is untouched from the
  initial commit; mathgraph-q3z (the bug where its data-card template
  hardcodes "175 + 174" instead of interpolating the real `n_pres`/`n_abs` it
  computes) is confirmed still open and unfixed. I did not touch
  `freeze_bench.py` — that bug is q3z's scope, not this bead's.
- Read `mathgraph/freeze_bench.py` end to end: `main()` computes real
  `n_pres`/`n_abs` from whatever corpus it's pointed at and writes them to
  `tasks.jsonl` correctly, but writes the static `CARD` string (which
  hardcodes "175"/"174" and the "~0.67*" baseline) verbatim to
  `bench_release/README.md`. So even if someone runs the generator today,
  the data card it produces would still assert stale counts regardless of
  what's actually in the `tasks.jsonl` it just wrote.
- README.md:272 (already fixed by a prior session, uncommitted in this tree)
  states the present arm is now **176** statements, "not the 175 every table
  before it reports" — independent evidence that 175 has drifted repo-wide,
  reinforcing that hardcoding 175 in the shipped-benchmark section would be
  wrong today even setting the "artifact doesn't exist" problem aside.

Conclusion: option (a) from the bead (locate a real published
`bench_release/tasks.jsonl` and count its rows) is not available — no such
artifact exists anywhere I can find, and the bead's own investigation (a
prior session) had already reached the same conclusion. I went with option
(b): reword the README section instead of asserting fixed counts.

## Change made

`README.md`, "## The shipped benchmark" section — replaced:

> `bench_release/` is the frozen, standalone version: `tasks.jsonl` (175
> present-arm + 174 absent-arm statements, each naming its reference corpus),
> a stdlib-only `scorer.py`, and a data card. ...

with text that (1) states plainly it's not checked into the repo but
generated on demand by `python -m mathgraph.freeze_bench`, (2) drops the
specific "175 + 174" claim entirely rather than asserting a number that
can't be checked against any real file, and (3) adds an explicit caveat
that the generator's own data-card template doesn't recompute its stated
counts from the corpus it's run against (i.e., don't trust the numbers
printed inside a *generated* `bench_release/README.md` either, until
mathgraph-q3z's interpolation fix lands) and points the reader at
`tasks.jsonl` as the source of truth instead.

I did not fix `freeze_bench.py` itself (that's mathgraph-q3z, explicitly
out of scope per the task prompt: "If you discover work outside this
bead's scope, file it as a new bead" — q3z already exists and covers this,
so no new bead filed).

Old text → new text is a full paragraph rewrite; see `git diff README.md`
for the exact diff. No specific number was "changed" (no replacement
number substituted for 175/174) because no verifiable current number exists
to put in its place — the honest fix per the bead's own option (b) was to
stop asserting one, not to guess a replacement.

## Numbers left alone, and why

- README.md ~957: `| PFR present arm (n=175, pre-scanner-fix corpus) |` —
  explicitly labelled historical ("pre-scanner-fix corpus"), out of this
  bead's scope, left untouched.
- README.md ~272: already says present arm is 176 "not the 175 every table
  before it reports" — this was already fixed by a prior session (uncommitted
  in the working tree), not part of this bead, left as-is.
- `tests/test_corpus.py:163` and `QUICKSTART.md:104-105` — both already show
  176 in the working tree (uncommitted prior-session fixes), not part of this
  bead, left as-is.

## Test suite

Ran the full suite per the environment instructions. Had to work around a
container permission issue first: the default uv cache/python-install dirs
under `/home/node/.cache` and `/home/node/.local/share/uv` are owned by
`root` and not writable by the `node` user running this session, so plain
`uv run` failed with `Permission denied` before ever reaching the tests.
Worked around with:

```
export UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_INSTALL_DIR=/tmp/uv-python \
       XDG_DATA_HOME=/tmp/xdg-data XDG_CACHE_HOME=/tmp/uv-cache
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

Result (verbatim tail):

```
............................................................................
----------------------------------------------------------------------
Ran 76 tests in 91.758s

OK
```

All 76 tests pass, including `test_evaluated_on_the_documented_number_of_statements`
— it passes because a prior session already fixed the 175→176 expectation in
`tests/test_corpus.py` (uncommitted in this tree, not my change). Zero
failures, not just the one documented pre-existing failure — that pre-existing
failure has apparently already been fixed by other in-progress bead work in
this same working tree. This is a *better* state than the "known baseline"
described in the task prompt, not a regression — confirmed by reading the
diff on `tests/test_corpus.py` (`M`, uncommitted) rather than assuming.

I note the uv-cache permission issue here for visibility but did not file a
bead for it — it's an environment/container property, not a repo defect, and
future sessions in a fresh container may not hit it at all (root vs. node
ownership looks like an artifact of how this particular sandbox was
provisioned).

## What I did not do / could not verify

- Did not fix mathgraph-q3z (freeze_bench.py's hardcoded CARD text) — out of
  scope for this bead, already tracked separately.
- Did not run `freeze_bench.py` myself against a live corpus in this session
  (the prior session that filed q3z already did this and got present=176,
  absent=174 with a monkeypatched blueprint path — I relied on their
  documented repro rather than re-running it, since re-running it wouldn't
  change the conclusion for this bead: no real artifact exists to check
  README numbers against, regardless of what a fresh run produces).
- Could not find any external/published copy of `bench_release/` to ask a
  human about within this session (no network access, no such path anywhere
  on disk) — per the bead, asking a human was option (a)'s fallback; I
  applied option (b) instead per the bead's own guidance for "no such
  artifact exists yet."

## Bead status

Closed mathgraph-036: README text updated, no numbers asserted that can't be
backed by a real file, evidence recorded above and in the bead's close
message. Test suite green (76/76, better than documented baseline).

## Git status at handoff (not committed, per policy)

Modified/untracked files at handoff (mine + carried-over from prior
uncommitted sessions in this tree — I did not touch QUICKSTART.md,
tests/test_corpus.py, or mathgraph/bench_pfr.py this session):

```
 M README.md                  <- this session's change (+ prior session's earlier edits in the same file)
 M QUICKSTART.md               <- prior session, untouched by me
 M tests/test_corpus.py        <- prior session, untouched by me
 M mathgraph/bench_pfr.py      <- prior session, untouched by me
 M .beads/interactions.jsonl
 M .gitignore
?? .beads/issues.jsonl
?? .claude/settings.local.json
?? sandbox-prompt.md
```

Suggested next commands (not run — conservative git policy):

```
git add README.md
git commit -m "docs: stop asserting stale bench_release/ counts that can't be verified (mathgraph-036)"
```

(Leaving the other modified files for whichever bead owns them to commit
separately, or for a human to decide how to bundle.)
