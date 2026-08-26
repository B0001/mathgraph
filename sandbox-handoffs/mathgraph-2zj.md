# mathgraph-2zj handoff

## Bead

README.md's "The verification layer" section introduces a table ("175
statements × 5 proposal populations", correct / sibling / wrong-namespace /
hallucinated / random, two accept-rate columns). `verify.py:181`'s
`evaluate()` matches the table's row labels and docstring wording almost
verbatim, but had no caller anywhere in the repo — no CLI subcommand, no
test. So there was no command that regenerated the table, and given every
other "175" figure tied to the PFR present arm had already turned out to be
stale (176), the table's n and accept rates were a strong candidate for the
same drift.

## What I found on claim

The bead was already `in_progress`, claimed by a previous session. Its notes
were the description above; the working tree (uncommitted) already had a
`cmd_verify_bench` / `mathgraph verify-bench` subcommand wired into
`mathgraph/cli.py` (calls `verify.evaluate` over PFR present-arm gold pairs
built from the blueprint `.tex` sources, mirroring `bench_pfr`'s
`blueprint_blocks` pattern), but README.md's table itself still showed the
old n=175 / 34.9%,6.3%,... numbers unchanged, and the driver had apparently
never been run to completion and compared. I verified the driver was sound
by reading it, then ran it rather than trusting it was already correct.

## What I did

1. Set `UV_CACHE_DIR=/tmp/uv-cache`, `XDG_DATA_HOME=/tmp/xdg-data`,
   `XDG_CACHE_HOME=/tmp/xdg-cache` — the default cache/data dirs
   (`/home/node/.cache/uv`, `/home/node/.local/share/uv`) are owned by
   `root` and unwritable by the `node` user `uv` runs as in this container,
   so `uv run` fails outright without a redirect. Noting this since it will
   bite the next session too.
2. Ran the existing driver twice to confirm determinism (seed=0, fixed):

   ```
   MATHGRAPH_DATA=/workspace/mathgraph-data uv run mathgraph verify-bench
   ```

   Output (both runs identical):

   ```json
   {
     "n": 176,
     "permissive": {
       "correct":          {"n": 176, "accept_rate": 0.358, "caught_nonexistent": 0.0},
       "sibling":          {"n": 176, "accept_rate": 0.097, "caught_nonexistent": 0.0},
       "wrong_namespace":  {"n": 21,  "accept_rate": 0.381, "caught_nonexistent": 0.0},
       "hallucinated":     {"n": 176, "accept_rate": 0.0,   "caught_nonexistent": 1.0},
       "random":           {"n": 176, "accept_rate": 0.0,   "caught_nonexistent": 0.0}
     },
     "precise": {
       "correct":          {"n": 176, "accept_rate": 0.085, "caught_nonexistent": 0.0},
       "sibling":          {"n": 176, "accept_rate": 0.011, "caught_nonexistent": 0.0},
       "wrong_namespace":  {"n": 21,  "accept_rate": 0.0,   "caught_nonexistent": 0.0},
       "hallucinated":     {"n": 176, "accept_rate": 0.0,   "caught_nonexistent": 1.0},
       "random":           {"n": 176, "accept_rate": 0.0,   "caught_nonexistent": 0.0}
     }
   }
   ```

   `n=176` confirms the present arm has moved 175→176 here too, same as the
   arms fixed under mathgraph-3gu/etj.

3. Updated README.md's table (was line ~1082-1091, now ~1090-1103 after
   earlier unrelated edits in the same working tree shifted line numbers):

   | population | old (permissive/precise) | new (permissive/precise) |
   |---|---|---|
   | correct | 34.9% / 6.3% | **35.8% / 8.5%** |
   | sibling lemma, same module | 10.3% / 1.1% | **9.7% / 1.1%** |
   | same name, wrong namespace | 33.3% / 0.0% | **38.1% / 0.0%** |
   | hallucinated name | 0.0% / 0.0% | **0.0% / 0.0%** (unchanged) |
   | random declaration | 0.6% / 0.0% | **0.0% / 0.0%** |

   Justifying command: `MATHGRAPH_DATA=/workspace/mathgraph-data uv run
   mathgraph verify-bench` (output above). n changed 175→176 in the same
   edit. Not every row moved the same direction (sibling went down, correct
   and wrong-namespace went up), which is what a genuine re-measurement
   looks like rather than a scaling artifact.

4. Added to the README, next to the table:
   - The reproducing command itself (`uv run mathgraph verify-bench`), so
     this table no longer silently reads as a live claim.
   - A callout that the "wrong namespace" row's n is 21, not 176:
     `corrupt()`'s wrong-namespace mode requires another declaration sharing
     the gold's last name component, and only 21 of 176 gold names have
     one. This is real and visible directly in the driver's own JSON
     output's per-population `"n"` field, not something I inferred —
     worth flagging because presenting it as a flat percentage next to four
     176-sample rows without that context overstates its precision.
   - An explicit "this replaces a previously reported 175-statement table
     that no script reproduced" paragraph, matching the style already used
     elsewhere in this README for other re-measured figures.

5. Found, while doing this, that the table's own old "34.9%" figure is
   *also* quoted two paragraphs earlier (`### One level deeper...
   Argument identity` section) as the baseline for a claim that wiring
   argument-pattern verification in as an independent accept path moves the
   verifier from 34.9%→**41.7%** accept on correct proposals, and that this
   is next to a "measured fire rates: 8.6%/0.6%/0.0%" claim for the same
   populations. Both numbers are tied to the pattern-augmented accept path
   (`Verifier.verify()`'s formula-pattern branch, only active when
   `math_segments` is passed), which `verify.evaluate()` / `verify-bench`
   deliberately does **not** exercise (matches the table's own pre-pattern
   framing). So I could not reproduce 41.7% or 8.6%/0.6%/0.0% with the tool
   this bead added — reproducing them needs a different driver (gold pairs
   with math segments attached, run through the pattern-augmented path).
   I did not build that here: **out of scope for this bead**, and I did not
   want to guess at new methodology under this bead's title. Filed as
   **mathgraph-g8x**.
   - Rather than leave the 34.9%/41.7%/8.6% figures silently contradicting
     the table I just updated (34.9%→35.8% for the same cell), I labeled
     both paragraphs in place as unverified this session, with a pointer to
     mathgraph-g8x. This is the "fix the document" branch of "fix the code
     or fix the document, never a third" — I did not touch the 41.7%/8.6%
     numbers themselves, since I have no measurement to replace them with.

## Numbers changed (old → new, command)

| location | old | new | command |
|---|---|---|---|
| README "verification layer" table, n | 175 | 176 | `uv run mathgraph verify-bench` |
| — correct, permissive | 34.9% | 35.8% | same |
| — correct, precise | 6.3% | 8.5% | same |
| — sibling, permissive | 10.3% | 9.7% | same |
| — sibling, precise | 1.1% | 1.1% (unchanged) | same |
| — wrong-namespace, permissive | 33.3% | 38.1% (n=21) | same |
| — wrong-namespace, precise | 0.0% | 0.0% (unchanged) | same |
| — hallucinated, both | 0.0% / 0.0% | 0.0% / 0.0% (unchanged) | same |
| — random, permissive | 0.6% | 0.0% | same |
| — random, precise | 0.0% | 0.0% (unchanged) | same |

## Numbers deliberately left alone (and why)

- README.md:983 `n=175, pre-scanner-fix corpus` table — explicitly labeled
  historical, describes the old scanner's output on purpose for a
  like-for-like comparison. Untouched.
- README.md:1054/1058-1059 ("34.9%... to **41.7%**") and the 8.6%/0.6%/0.0%
  argmatch fire rates — see above. Labeled as unverified-this-session rather
  than changed, with the reason (different code path, no current driver),
  and filed as mathgraph-g8x rather than guessed at.
- README.md:1096 ("e.g. 50% correct → ~76% correct among accepted") — an
  example Bayes-style mixed-stream calculation next to the table. I checked
  whether it falls out of the table's own permissive numbers by simple
  arithmetic (mixing correct against random, against wrong-namespace, etc.)
  and none of the obvious combinations reproduce 76% from either the old or
  new table values, so its provenance is unclear to me and I did not touch
  it — flagging as **unverified**, not fixed, since guessing at what mix it
  assumes and "fixing" it to match would be exactly the "third move" the
  standard for this repo forbids. Did not file a bead for this one specific
  line — noting it here so whoever looks at mathgraph-g8x sees it, since
  it's in the same paragraph cluster.

## Test suite

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

```
............................................................................
----------------------------------------------------------------------
Ran 76 tests in 89.353s

OK
```

76/76 passing — no failures at all. (The task prompt's documented baseline
of "one pre-existing failure" — `test_evaluated_on_the_documented_number_of_
statements`, 176 != 175 — was already fixed in this same uncommitted working
tree by a prior session's mathgraph-3gu, before I started. I did not need to
touch that test for this bead; I only confirmed the suite is still green
after my README-only changes.)

## What I did not do, and why

- Did not attempt to reproduce or update the 41.7%/8.6%/0.6%/0.0% argmatch
  pattern-accept figures — different code path, no driver exists, filed as
  mathgraph-g8x rather than improvised.
- Did not touch the "50% correct → ~76%" example — couldn't verify its
  derivation from either the old or new table; flagged rather than silently
  left implying it's still consistent.
- Did not touch any other file's "175" occurrences (bench_pfr.py,
  structmatch.py, QUICKSTART.md, .gitignore diffs already present in the
  working tree) — those are pre-existing uncommitted work from other closed
  beads (mathgraph-3gu, mathgraph-etj, mathgraph-7dw), not part of this
  bead, and I left them as I found them.
- Did not commit or push, per repo git policy.

## Unverified

- The `mathgraph verify-bench` driver's *methodology* (corrupt() modes,
  gold-pair construction from PFR blueprint blocks) was written by the
  prior session that claimed this bead, not by me. I read it, sanity-checked
  it against `verify.py`'s own `corrupt()`/`evaluate()` and confirmed the
  populations, matcher, and profiles it uses match `cli.py`'s
  `VERIFY_PROFILES` and the README's stated methodology ("corrupting gold
  proposals the ways proposers actually fail"), and confirmed its output is
  deterministic across two runs — but I did not independently re-derive the
  gold-pair extraction logic from scratch against the PFR blueprint source.
- The 76% mixed-stream figure's derivation, as above.

## Git status

Working tree has this bead's README.md changes plus pre-existing uncommitted
work from other already-closed beads (see `git diff --stat`). Nothing
committed or pushed, per policy. Suggested next commands (for a human):

```
git status
git diff -- README.md
git add README.md mathgraph/cli.py   # this bead's files; cli.py's
                                       # verify-bench was added by the prior
                                       # session and is exercised/verified here
git commit -m "..."
```
(Left as suggestions only — not run.)
