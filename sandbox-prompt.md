You are working autonomously in the mathgraph repo. Make aggressive, real
progress. Do not stop to ask permission; do not stop early because you are
unsure whether there is work left.

## The standard everything is held to

This repo's `README.md` publishes **negative results with hard numbers** —
100% correct abstention, 18.2% recall@1, "best achievable precision ~67% on 3
answers out of 349", "neither benchmark admits an operating point where the
alignment is trustworthy". Someone deciding whether to trust this tool reads
those numbers and asks: *does the code actually produce this?*

**A number in a document is only allowed to exist if the code produces it or
the document says where it came from.** When a documented figure and the code
disagree, you have two honest moves — fix the code, or fix the document. Never
a third. Do not quietly delete a number, do not round it into vagueness, and
do not mark anything "verified" on your own reasoning. A passing test with a
name is evidence; reasoning is not.

**The negative framing is load-bearing and must survive you.** The README says
the results are "largely negative", that "the usable output of this tool is
the exact internal graph plus a flagged, ranked candidate list for a human to
check — not an assertion layer", and that a tool of this shape "trusted at
face value is worse than no tool." These are the honest conclusions of a
measurement, not pessimism to be engineered away. If you improve retrieval,
**re-measure and report the new number — do not upgrade the conclusion.**
Softening "neither benchmark admits a trustworthy operating point" because a
metric moved is the single worst outcome of this session. If you think a hedge
is now overstated, leave it and argue for the change in your handoff with the
measurement attached.

## Known baseline — do not mistake this for your own breakage

The suite currently has **exactly one pre-existing failure**:

```
FAIL: test_evaluated_on_the_documented_number_of_statements
AssertionError: 176 != 175   (tests/test_corpus.py:163)
```

It fails identically inside this container and on the host, so it is real
drift, not an environment artifact. The README at line ~269 already says the
present arm is **176** statements "as of the scanner fix below, not the 175
every table before it reports" — so the *test* is the stale party here, not
the corpus. Confirm that before acting on it.

**Any failure other than this one is yours and must be fixed before you close
a bead.**

## First objective — the stale-175 sweep

`175` appears in several places and they are **not all wrong**. Some are
correctly labelled history and must be left alone:

- `tests/test_corpus.py:163` — the assertion above.
- `README.md:930` — a table explicitly labelled "n=175, pre-scanner-fix
  corpus". Legitimately historical.
- `README.md:1030`, `README.md:1105` — "175 statements × 5 proposal
  populations" and the frozen `bench_release/` description. Check whether each
  describes current output or a frozen past artifact.
- `QUICKSTART.md:104-105` — `{"n": 175, ...}` in sample output. Does the
  command shown actually print that today?

The work is to determine, per occurrence, whether it is current-output-that-
drifted or correctly-labelled-history, and fix only the first kind. **Changing
a correctly-labelled historical number is a regression**, because it destroys
the like-for-like comparison the README is careful to preserve. Where a number
is historical but not clearly labelled as such, the fix is to label it.

When that is done, keep going: sweep the rest of the documented figures in
`README.md` and `QUICKSTART.md` the same way — for each, either point at the
command that regenerates it, or mark it as a frozen measurement with its
provenance.

## Environment

- **The test runner is stdlib `unittest`, not pytest** — pytest is not
  installed and is not a dependency. The suite is:

  ```
  MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
  ```

  76 tests, roughly two minutes. `MATHGRAPH_DATA` is required; corpus tests
  silently skip without it, which will make a broken run look green.
- `bd` is the tracker. File a bead per work item with `bd create` before
  writing code, `bd update <id> --claim`, and close only when the evidence
  exists. An empty `bd ready` means file new beads, not that you are done.
- The MCP server in `.mcp.json` points at a host path that is not mounted
  here. It will fail to start. Ignore it; it is not needed.

## Git policy

Do the work, get the suite to its known-good state, leave the tree **ready to
commit**. Do not `git commit`, do not `git push`, do not `bd dolt push`. Put
the exact commands in your handoff and let a human run them.

## What to hand back

**Write this to the handoff path named at the end of this prompt before you
finish, and print it as your final message.** The file is the part that
survives; this container is disposable.

A report a reviewer can check, not a summary of effort:

- Each number you changed: old value, new value, and the command whose output
  justifies the new one.
- Each number you deliberately **left alone**, and why it is history rather
  than drift.
- Any claim or hedge you were tempted to soften, with the measurement, and
  what you did instead.
- The final test-run line verbatim, with the pass/fail count.
- What you decided not to do, and why. Empty means you did not look hard.
- What you could not verify. An honest "unverified" beats a confident claim.
