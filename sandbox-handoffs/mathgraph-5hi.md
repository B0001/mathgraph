# Handoff: mathgraph-5hi

README.md:326 stated, as part of the PFR present-arm "Why" analysis: "the
first stage reaches the gold declaration **97%** of the time — but places it
at **median rank ~250** of 242,550." The bead asked whether this had drifted
along with the corpus (idx_full grew from 242,550 to 251,236 declarations,
per the sibling bead mathgraph-zzq), and whether it needed re-measuring
together with the rest of the present-arm table rather than as an isolated
swap.

## What I found before changing anything

`mathgraph/bench_pfr.py` had **no code that computed this stat at all** —
neither the 97%-reach figure nor the median-rank figure. It existed only as
prose, in two places: README.md's "Why" section and README.md's "Structural
matching" section (a near-identical restatement), plus a third, code-level
copy in `mathgraph/structmatch.py`'s module docstring (not touched by this
bead — see "What I deliberately left alone" below). None of the three was
backed by a reproducing command. That is itself a violation of "a number in
a document is only allowed to exist if the code produces it or the document
says where it came from" independent of whether 97%/250 happened to still be
numerically correct — there was no way to check.

## What I changed

**Added `mathgraph/bench_pfr.py:lexical_pool_stats()`** (and wired it into
`main()`'s output as the `lexical_pool` field), so the claim is now
code-produced. It measures, at `StructReranker`'s shipped `depth=10000` (the
same depth `cmd_bench`/`uv run mathgraph bench` uses — i.e. the pool
structural reranking actually gets to work on), what fraction of present-arm
statements have gold anywhere in that pool, and gold's median rank among
those that do.

Reproduce with the same command already documented in README.md for the
combined-arm sweep:

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m mathgraph.bench_pfr \
  '{"deploy": "mathgraph-data/artifacts/idx_full", "mathlib_only": "mathgraph-data/artifacts/idx_mathlib", "pattern": "mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex", "len_pivot": 0.75, "mod_weight": 0.1, "typ_weight": 0.15, "prefix_weight": 0.85, "title_boost": 2.5}'
```

and read the `lexical_pool` field. Output as of 2026-08-08:

```json
"lexical_pool": {
  "n": 176,
  "depth": 10000,
  "reached": 147,
  "reach_rate": 0.835,
  "median_rank": 42
}
```

| figure | old (README) | new (measured) | command |
|---|---|---|---|
| reach rate | 97% | **83.5%** (147/176) | `bench_pfr` → `lexical_pool.reach_rate`, above |
| median rank | ~250 | **42** | `bench_pfr` → `lexical_pool.median_rank`, above |
| index size (context for the rank number) | 242,550 | **251,236** | already fixed by mathgraph-zzq; `len(load('idx_full')['rows'])` |

Updated **both** README.md occurrences of the claim (not piecemeal):

1. "Why" section (~line 325-343): replaced the two bullet points and added a
   paragraph explaining the reproducing command, that no prior script backed
   the old figures, and — the substantive part — that **the drift changes
   the conclusion of this specific sub-claim**: at 83.5% reach, 16.5% of
   present-arm statements never put gold in front of the structural
   reranker at all, so this is now *partly* a retrieval problem, not purely
   a ranking problem as the section previously asserted outright. I did
   **not** touch the overall negative framing (recall@5 is still weak, the
   linear reranker still gave no measurable lift) — only this one sub-claim,
   which the new measurement directly contradicts.
2. "Structural matching" section (~line 941-959): the identical restatement
   ("the measured bottleneck was always ranking: ... 97% ... median rank
   ~250") is now reworded to say the bottleneck *looked like* ranking at the
   time this was built, points at the "Why" section for current numbers, and
   notes the design still stands on its own current results (recall@5
   31.8%→38.1% from reranking) rather than on the stale motivating numbers.

## Claim I was tempted to soften, and what I did instead

The temptation: leave "So it is a ranking problem, not a retrieval problem"
as-is, since the *overall* recall numbers (18.2%/31.8%) didn't move and
weren't the subject of this bead. I did not do that. The 97%→83.5% reach-rate
drop is a real, measured change to a load-bearing sub-claim in the same
paragraph I was asked to fix, and leaving it unqualified while updating the
number next to it would have been exactly the "quietly delete/round into
vagueness" failure mode the standing instructions warn against. I reworded
the conclusion from "a ranking problem, not a retrieval problem" (absolute)
to "partly a retrieval problem, not purely a ranking one" (measured: 16.5%
never reach the pool) — a correction to match the new measurement, not a
softening or a strengthening of the tool's overall trustworthiness
conclusion, which is untouched.

## What I deliberately left alone

- **`mathgraph/structmatch.py:14`** — the module docstring has the identical
  historical claim ("the lexical stage reaches the gold declaration 97% of
  the time and puts it at median rank ~250") inline in code. This bead's
  acceptance criteria and title were scoped to README.md:326. Fixing a
  different file's docstring is adjacent work, not this bead — filed as
  **mathgraph-0a1** or handoff to a human, with the current measured numbers
  attached so whoever picks it up doesn't need to re-derive them. It is now
  the one place in the repo still stating the stale 97%/~250 figures.
- **`README.md:930`** (the n=175 pre-scanner-fix table) and the
  `bench_release/` frozen-artifact description — untouched; these were
  already correctly labelled as history or already fixed by prior
  sessions (mathgraph-zzq / other beads visible in the working tree before I
  started). Not part of this bead's scope, and I did not re-verify them since
  the task instructions said "do only this bead."
- **`QUICKSTART.md`** — not touched. Not part of mathgraph-5hi's scope (that
  file's `{"n": 175, ...}` sample output is a different bead's concern per
  the standing sweep objective, which explicitly says "do only this bead"
  for this session).

## Unverified / could not fully confirm

- **Original methodology for the 97%/~250 figures is unknown.** I assumed
  they were measured at the same `depth=10000` `StructReranker` consumes in
  production (the phrase "lexical top-K" / "lexical stage" in both README
  and `structmatch.py` strongly suggests this), since that is the only depth
  actually shipped and referenced elsewhere in the codebase. If the original
  measurement instead used an unbounded search (I also measured that:
  99.4% reach, median rank 193 — also far from 250, for what it's worth), the
  "drift" characterization would change in magnitude but not in direction
  (both alternate methodologies I tried show reach dropping and/or median
  rank not matching 250). I could not resolve this ambiguity because no code
  or comment in the pre-session repo state specifies which depth the
  original 97%/250 measurement used — flagging as unverified rather than
  asserting a specific origin.
- I did not attempt to determine *why* median rank improved so much (250→42)
  beyond noting the scorer bug fixes documented later in the same README
  section ("Length normalisation was backwards") as the most likely cause.
  Confirming that causally (e.g. by re-running against a pre-fix scorer
  checkout) was out of scope for a P3 documentation-drift bead.

## Test suite

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

```
Ran 76 tests in 101.321s

OK
```

76/76 pass, 0 failures — this is *better* than the documented known-good
baseline (which expected exactly one pre-existing failure,
`test_evaluated_on_the_documented_number_of_statements`, 176 != 175). That
failure was already fixed in the working tree before I started (an earlier,
uncommitted session's edit to `tests/test_corpus.py` changed the expected
count to 176 and refreshed `EXPECTED` recall tuples — see git diff, not my
work, pre-existing in the tree when I claimed this bead). I verified the
suite is green both before and after my edits; my changes (adding
`lexical_pool_stats` and wiring it into `bench_pfr.main()`) are additive and
don't touch any code path a test exercises directly (no test imports
`bench_pfr`).

## Files changed by this bead specifically

- `mathgraph/bench_pfr.py` — added `lexical_pool_stats()`, wired into
  `main()`'s output dict, added `import statistics`.
- `README.md` — updated the two "97%/median rank ~250/242,550" occurrences
  (lines ~325-343 and ~954-959 in the post-edit file).
- `bd`: closed mathgraph-5hi with evidence in notes; filed mathgraph-0a1 for
  the leftover `structmatch.py` docstring.

Note: the working tree also carries substantial **pre-existing, uncommitted**
changes from earlier sessions (`.gitignore`, `QUICKSTART.md`, `mathgraph/
cli.py`, `tests/test_corpus.py`, most of `README.md`'s other diffs) — those
are not part of this handoff; see `git diff` / other beads
(mathgraph-zzq, mathgraph-7dw, mathgraph-3gu, mathgraph-ek7) for their
provenance. I did not commit anything, per git policy.

## Suggested next commands (not run — conservative git policy)

```
git status
git diff README.md mathgraph/bench_pfr.py   # this bead's changes
git add README.md mathgraph/bench_pfr.py mathgraph/cli.py tests/test_corpus.py QUICKSTART.md .gitignore
git commit -m "..."   # human to write/approve message covering all pending work, not just this bead
```
