# Handoff: mathgraph-7dw

Two PFR present-arm code paths give different recall@1 (0.182 vs 0.188);
test_corpus.py EXPECTED constant is stale but passes on tolerance.

## Disposition

Fixed via the "document" branch of the acceptance criteria, not the "unify"
branch. Reasoning below.

## What I verified before touching anything

Ran both pipelines against the live `idx_full` corpus (176 present-arm
statements), confirming the bead's own numbers reproduce exactly:

```
UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_INSTALL_DIR=/tmp/uv-python \
UV_TOOL_DIR=/tmp/uv-tool UV_DATA_DIR=/tmp/uv-data \
MATHGRAPH_DATA=/workspace/mathgraph-data uv run mathgraph bench
```
→ `{"lexical": {"n": 176, "recall@1": 0.182, "recall@5": 0.318}, "+structural": {"n": 176, "recall@1": 0.193, "recall@5": 0.381}}`

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m mathgraph.bench_pfr \
  '{"deploy": "mathgraph-data/artifacts/idx_full", "mathlib_only": "mathgraph-data/artifacts/idx_mathlib", "pattern": "mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex", "len_pivot": 0.75, "mod_weight": 0.1, "typ_weight": 0.15, "prefix_weight": 0.85, "title_boost": 2.5}'
```
→ `present.recall@1 = 0.188`, `present.recall@5 = 0.318` (n=176)

Both confirmed reproducible. recall@5 is identical (0.318) in both paths;
only recall@1 differs, by exactly one statement out of 176 — consistent with
the bead's hypothesis that this is `np.argpartition`/`argsort` tie-breaking
at the score-depth boundary flipping which of two near-tied candidates lands
at rank 1, not a real difference in ranking quality. `Aligner.align()` scores
at `depth=max(topk, MARGIN_TAIL)=10` (align.py:256-258); `cli.cmd_bench`'s
`StructReranker(lam=0.0, depth=10000)` scores at depth=10000. I did not go
further to pin down which exact statement flips or prove the tie-break
mechanism byte-for-byte — the observable symptom (identical recall@5,
one-statement recall@1 delta, both numbers independently reproducible) is
sufficient to justify "document, don't unify" without needing to prove the
numpy internals.

## Why "document" rather than "unify"

Unifying would mean either (a) making `Aligner.align()` default to a much
larger internal depth so its ranking is computed the same way
`StructReranker(depth=10000)` does, or (b) rewriting `bench_pfr.arm_present`
to route through `StructReranker` instead of `align()` directly.

Rejected (a): `align()` is the production entry point, used by every other
caller in this codebase, including `Abstention` and `CoverageIsAFraction` in
this same test file, and (already-closed) mathgraph-aec's
`combined_precision_sweep` in `bench_pfr.py`, which consumes `align()`'s
`coverage`/`margin` fields via `arm_present`/`arm_absent`'s `records`.
Changing the shared default depth risks perturbing coverage/margin values
those already-closed beads' numbers depend on, for a benchmarking-only
cosmetic fix. Out of proportion to a P3 bug about which of two already-honest
numbers is "the" number.

Rejected (b): `arm_present` and `arm_absent` exist specifically to feed
`combined_precision_sweep`, which needs `coverage`/`margin` per statement —
fields `StructReranker.rank` doesn't expose. Switching `arm_present`'s scoring
path would decouple its recall@1 from the coverage/margin records used
immediately afterward for the calibration sweep, which is a worse
inconsistency than the one being fixed.

Chosen: document, per the acceptance criteria's explicit alternative. Both
numbers are real, both reproduce, and the repo's own standard ("a number is
only allowed to exist if the code produces it or the document says where it
came from") is satisfied by saying which pipeline produced which number and
why they differ by one statement — not by picking a winner.

## Changes

1. **`mathgraph/bench_pfr.py`** — added a docstring to `arm_present` stating:
   this is a different measurement from README's published present-arm
   table (`cli.cmd_bench` / `mathgraph bench`), why (different internal
   `align()` depth vs `StructReranker(depth=10000)`), and the measured
   delta (0.188 vs 0.182 at recall@1, identical 0.318 at recall@5). No
   command output changed — this is comment-only.

2. **`README.md`**, combined-arm calibration-sweep section (~line 295) — added
   a paragraph immediately after the reproduce command warning that the same
   JSON blob prints `present.recall@1: 0.188`, not the 18.2% in the present-arm
   table above, and explains why (same reasoning as the docstring). This is
   the spot a reader would actually hit the discrepancy: they run the
   documented reproduce command, see `present` sitting right next to
   `combined_calibration` in the output, and could reasonably read 0.188 as
   contradicting the 18.2% published a few paragraphs earlier.

3. **`tests/test_corpus.py`** — `Benchmark.EXPECTED` changed from
   `{"lexical": (0.189, 0.320), "+structural": (0.200, 0.389)}` to
   `{"lexical": (0.182, 0.318), "+structural": (0.193, 0.381)}`.
   Justification: `Benchmark.setUpClass` (test_corpus.py:135-155) builds its
   own `StructReranker(al, lam=0.9, depth=10000)` and sweeps `lam` over
   `(0.0, 0.9)` for `("lexical", "+structural")` — this is the *same*
   depth-10000 pipeline as `cli.cmd_bench`, not `bench_pfr.arm_present`. So
   the correct refit target is the `uv run mathgraph bench` output above:
   `lexical (0.182, 0.318)`, `+structural (0.193, 0.381)` — exactly what I
   measured. The old `(0.189, 0.320)`/`(0.200, 0.389)` was in-band only by
   luck (DELTA=0.01 tolerance swallowing a ~0.007-0.01 drift); it no longer
   reflects a live measurement of anything in this repo.

   Old value provenance I could not verify: I don't know what produced
   `(0.189, 0.320)`/`(0.200, 0.389)` originally — it doesn't match either
   current pipeline's output today, which is exactly the bead's complaint
   (quietly stale, passing on tolerance). Not investigated further since the
   fix is to refit to a current measurement, not to explain the old one's
   origin.

## Left alone / out of scope

- The `test_evaluated_on_the_documented_number_of_statements` 175→176 fix at
  test_corpus.py:163 was already done by mathgraph-3gu (closed) before I
  started; I did not need to touch it, only the class docstring's
  parenthetical "~0.6pt that a single statement moves at n=175" text, which
  was *also* already updated to n=176 by the same prior work. Confirmed via
  `git diff` before editing — did not duplicate this.
- README's other present-arm tables (line ~269 "PFR present arm" 18.2%/31.8%,
  line ~366 "lexical, after 18.9%/32.0%" in the length-normalisation history
  section, line ~410 typ_weight sweep table) are outside this bead's
  acceptance criteria, which is scoped to the arm_present/cmd_bench
  discrepancy and test_corpus.py's EXPECTED. The line-366/410 tables read as
  historical snapshots from when each fix (length norm, third field) was
  made, not live-reproducing claims — did not verify or touch them. If they
  need auditing, that's a new bead, not this one.
- Did not investigate the exact numpy tie-breaking mechanism (which specific
  statement flips, whether it's `argpartition`'s pivot selection or
  `argsort`'s handling of the sliced array) — confirmed the *symptom*
  (identical recall@5, one-statement recall@1 delta, both reproducible) which
  is what the acceptance criteria needed, but a reader wanting the literal
  root-cause line of code would still need to dig.

## Test suite

Two full runs after all edits landed, both clean:

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
............................................................................
----------------------------------------------------------------------
Ran 76 tests in 110.647s

OK
```

76/76 passing, 0 failures — better than the documented "one known
pre-existing failure" baseline, because that failure
(`test_evaluated_on_the_documented_number_of_statements`, 175 vs 176) was
already fixed by mathgraph-3gu before this session started. I did not
introduce or observe any other failure.

Environment note for whoever runs this next: `uv` needs `UV_CACHE_DIR`,
`UV_PYTHON_INSTALL_DIR`, `UV_TOOL_DIR`, `UV_DATA_DIR` pointed somewhere
writable (e.g. `/tmp/...`) in this container — the default
`~/.cache/uv`/`~/.local/share/uv` are root-owned and not writable by the
`node` user. Not a code issue, just a sandbox quirk; did not change any repo
file for this.

## Bead status

Closing `mathgraph-7dw` as done: acceptance criteria's "document" branch is
satisfied (bench_pfr.py docstring + README callout), and
`tests/test_corpus.py`'s `EXPECTED` reflects a current, verified measurement
in the same commit as this note.

## Git state — not committed, per policy

```
git status
```
shows (among other in-progress/closed-bead changes already in this working
tree from other sessions — not mine, left untouched):
 - modified: mathgraph/bench_pfr.py (docstring only, this bead)
 - modified: README.md (calibration-sweep paragraph, this bead)
 - modified: tests/test_corpus.py (EXPECTED tuple, this bead)

No commits made. Suggested commands for a human to run when ready:

```
git add mathgraph/bench_pfr.py README.md tests/test_corpus.py
git commit -m "mathgraph-7dw: document bench_pfr/cmd_bench recall@1 divergence, refit test_corpus EXPECTED"
```

(Other unstaged/untracked files in the tree belong to other beads'
in-progress or already-closed work and are not part of this commit.)
