# mathgraph-p14 handoff

## Bead

README.md:262 (PFR absent-arm status breakdown) published `170 unmatched, 4
ambiguous, 0 matched`. Running the documented reproducer against the
unchanged `idx_mathlib` artifact gives `168 unmatched, 6 ambiguous, 0
matched`. Determine whether this is environment-dependent nondeterminism (fix
the code) or a bad number (fix the doc), then act accordingly.

## Reproducer

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m mathgraph.bench_pfr \
  '{"deploy": "mathgraph-data/artifacts/idx_full", "mathlib_only": "mathgraph-data/artifacts/idx_mathlib", "pattern": "mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex", "len_pivot": 0.75, "mod_weight": 0.1, "typ_weight": 0.15, "prefix_weight": 0.85, "title_boost": 2.5}'
```

`.absent.status` in the output: `{"matched": 0, "ambiguous": 6, "unmatched":
168}`.

(Environment note: `uv` needed `UV_CACHE_DIR=/tmp/uv-cache
UV_PYTHON_INSTALL_DIR=/workspace/.local/share/uv/python` in this container —
the default `~/.cache/uv` and `~/.local/share/uv` are owned by `root` and not
writable by the `node` user the agent runs as. Not part of this bead, not
touched.)

## What I checked before concluding this is not a code bug

1. **Determinism of repeated runs.** Ran the reproducer 4 times back-to-back
   in this session, on top of the 2 back-to-back + 3 `PYTHONHASHSEED` (0/1/42)
   runs the prior session (which filed this bead) already did. All 7 runs:
   identical `168/6/0`. Not run-to-run noise in this environment.

2. **Hash-seed / iteration-order dependence.** `align.py`'s scoring path
   (`Aligner.query_weights` / `_score`) builds its query-weight dict by
   iterating `doc_words(text)` (a list, deterministic order) and reads
   `self.idf` / `self.by_stem` / `self.by_prefix`, which are built once at
   `Aligner.__init__` from the artifact's own token order (JSON-preserved,
   not a `set`). No `set` iteration sits on the path from query text to score.
   Consistent with the prior session's finding that `PYTHONHASHSEED` doesn't
   move the number.

3. **float32 vs float64 accumulation.** `Aligner._score` accumulates the
   per-candidate numerator (`raw`, via `np.add.reduceat`) in `dtype=float32`
   (align.py:212/217/223), which was my leading hypothesis for
   architecture/numpy-build-dependent drift near a threshold. I reimplemented
   the same reduction path in float64 (`/tmp/probe6.py`, not committed) and
   diffed it against the shipped float32 path for the three absent-arm
   statements sitting nearest `tau_cov=0.2474`
   (`kl-div`, `phi-minimizer-zero-distance`, `de-prop-improv`). Deltas were
   ~1e-8 — six orders of magnitude below what would be needed to move any of
   these across the threshold. float32 vs float64 is not the source of the
   gap.

4. **Where the closest-to-threshold statement actually sits.** The nearest
   absent-arm statement to `tau_cov` is `kl-div`, coverage `0.24795515...`
   against threshold `0.2474` — 0.00055 above it, i.e. a real, stable 0.22%
   margin, not floating noise (per #3, noise at this path is ~1e-8). The next
   closest ambiguous-side statement (`phi-minimizer-zero-distance`) sits
   0.031 above threshold — far too large a gap for precision-level drift to
   explain. There is no near-threshold fragility in the current run that a
   plausible cross-architecture float difference could flip.

5. **Code and data are both unchanged since before the number was
   published.** `git log` shows `align.py` last changed in `07b801e` (Jul 30,
   before either the `167/7` or `170/4` figures existed in the README) and
   `bench_pfr.py`'s `arm_absent` loop (the exact call sequence:
   `al.align(b.text, title=b.title, topk=3)` → `status[a.status] += 1`) is
   byte-identical before and after commit `591d4a9` (the commit that changed
   the published number from `167/7/0` to `170/4/0`) — that commit only added
   a `records.append(...)` line for an unrelated downstream sweep. The
   `idx_mathlib`/`idx_full` artifacts are dated 2026-08-03, before `591d4a9`
   (2026-08-08). `uv.lock` (numpy pin) hasn't changed since the initial
   commit. So the exact same code, against the exact same data, in what
   should be the same environment (this sandbox's only architecture,
   `aarch64`, numpy `2.5.1`), is what both produced `170/4/0` when `591d4a9`
   was written and produces `168/6/0` now.

Given 1–5, I could not find a mechanism — hash seed, iteration order, float
precision, repeated-run nondeterminism — that explains a 168/6/0 vs 170/4/0
split with unchanged code and data. The classification logic (`align.py`'s
`align()`, threshold compare on `coverage`/`margin`) is not itself
nondeterministic: same inputs give the same output, robustly, across every
axis I could test in this environment. I did not find a code bug to fix.

**Conclusion: the published `170 unmatched, 4 ambiguous` figure does not
reproduce and I found no evidence it was ever a property of a real,
different-but-legitimate environment — the more likely explanation is a
transcription/paste error when `591d4a9` updated this line (that commit
touched many numbers across the README in one pass).** Per the bead's
instruction ("don't just edit the README number without first establishing
which of the two it is"), I'm treating this as the doc being wrong, not the
code, and correcting the README to the verified re-run.

## What changed

`README.md:262` — table row:
- Old: `170 unmatched, 4 ambiguous, 0 matched`
- New: `168 unmatched, 6 ambiguous, 0 matched`
- Justified by: the reproducer command above, run 7 times total across this
  and the prior session (identical output every time).

Added a short paragraph immediately after the table (README.md:264-269)
recording that this replaces a non-reproducing 170/4 figure and summarizing
points 1–3 above, in the same style as the existing footnote a few paragraphs
down about `present.recall@1` (0.188 vs the published 18.2%) disagreeing
between code paths — so a reader hits the same kind of "here's why this
number and the neighboring prose don't match verbatim, and here's what does
reproduce" note, not a silently changed table cell.

Both totals still sum to 174 (168+6=174, matches `n_absent` in
`combined_calibration`), and `correct_abstention`/`false_match_rate` are
unaffected (100% / 0%, unchanged either way) — the two headline claims this
table exists to support did not move.

## Left alone, and why

- `correct_abstention: 100%` / `false matches: 0` in the same table — these
  don't depend on the ambiguous/unmatched split (both are non-matched
  outcomes) and are unaffected regardless of which of 170/4 or 168/6 is
  correct. Reproduces as `1.0` / `0.0` in the same JSON output. Not touched.
- `combined_calibration` ("100% precision on 3 answers out of 350") and
  everything else in that section — `n_absent: 174` already matches
  (168+6=174), and the combined-precision-sweep result doesn't reference the
  ambiguous/unmatched split directly, only the per-statement
  `(coverage, margin)` records, which are what `arm_absent` already produces
  regardless of the classification label attached. Reproduces as published.
  Not touched.
- Every other absent-arm mention I found in README.md (lines ~400, ~473,
  ~533, ~591, ~717) is about `correct_abstention`/`false_match_rate` (the
  100%/0 headline) or about a *different* threshold pair (`GRAPH_THRESHOLDS`,
  currently `0.2526/0.2658` in `cli.py`, historically `0.2474/0.2671` — same
  numbers as `Aligner`'s class defaults by coincidence, but a genuinely
  different fitted threshold used for a different corpus/entry point). None
  of them cite the `170/4` or `168/6` split. Confirmed by grep across the
  whole file — the only occurrence of this specific breakdown is line 262.
  Not touched.
- I did not touch `align.py`'s float32 accumulator (align.py:212/217/223)
  despite float32 being my leading hypothesis going in. #3 above shows it
  isn't the source of this particular gap (deltas ~1e-8, six orders of
  magnitude too small), so changing it would be an unjustified code change
  with no measurement behind it. If a *future* session finds a statement
  whose coverage sits within ~1e-4 of `tau_cov` (unlike anything in the
  current absent arm — closest is `kl-div` at 5.5e-4), that would be worth
  revisiting; nothing here calls for it today.
- Did not touch `.beads/issues.jsonl`, `pyproject.toml`, `uv.lock` diffs
  already present in the working tree at session start (pytest added as a
  dependency) — pre-existing, unrelated to this bead, not mine to resolve.

## Test suite

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

```
............................................................................
----------------------------------------------------------------------
Ran 76 tests in 99.822s

OK
```

76/76 passing, zero failures. Note: the standing context for this repo
describes a known pre-existing failure
(`test_evaluated_on_the_documented_number_of_statements`, 176 != 175) as the
expected baseline — that test now asserts `176` (tests/test_corpus.py:162)
and passes; it was fixed as part of commit `591d4a9` (already in the tree
before this session started, per `git show 591d4a9 --stat` showing
`tests/test_corpus.py | 6 +-`). Not something I changed. Current baseline is
fully green, which is at least as good as the documented known-good state.

## Not verified / could not check

- Whether `591d4a9`'s `170/4` figure really was a transcription slip (as
  opposed to some environment difference I couldn't reproduce, e.g. a
  different numpy build than what `uv.lock` currently pins, if the author's
  environment resolved dependencies before the lock was written — but
  `uv.lock` has been unchanged since the *initial* commit, before either
  `167/7` or `170/4` existed, so this seems unlikely). I cannot access
  whatever environment authored `591d4a9`, so this is inference from
  elimination, not direct proof. Flagging as the honest gap rather than
  overclaiming certainty.

## Git status at handoff

```
M .beads/issues.jsonl        # bd claim/close bookkeeping
M README.md                  # this bead's fix
M pyproject.toml             # pre-existing at session start, not mine
M uv.lock                    # pre-existing at session start, not mine
?? .claude/settings.local.json  # pre-existing at session start, not mine
```

Suggested commands for a human (not run by me per git policy):

```
git add README.md .beads/issues.jsonl
git commit -m "README: correct PFR absent-arm status breakdown to reproducing 168/6/0"
```

(`pyproject.toml`, `uv.lock`, `.claude/settings.local.json` are pre-existing,
unrelated changes from before this session — left for the human to decide
on separately.)

## Bead status

Claimed and closed as fixed: README corrected to the verified, repeatedly-
reproducing number, with provenance recorded inline. Evidence is in this
file and in the README diff itself.
