# Handoff: mathgraph-zzq

## Bead
`README.md:1117 'Index scale: 242,550 declarations, 5,609 name tokens, ~3 ms per
lexical query' has drifted (currently 251,236 / 5,399 / ~7ms)`

(By the time I picked this up, prior unrelated edits had shifted this line to
`README.md:1162` — it is the last line of the file, a standalone sentence not
under any specific section header, sitting after the `## The shipped
benchmark` section.)

## What I did

Re-ran the bead's own reproduction script:

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -c "
from mathgraph.index import load
import os, time
ART = os.path.join(os.environ['MATHGRAPH_DATA'], 'artifacts')
art = load(os.path.join(ART, 'idx_full'))
print('rows (declarations):', len(art['rows']))
print('postings (name tokens):', len(art['postings']))
from mathgraph.align import Aligner
from mathgraph.cli import LEX
al = Aligner(art, **{**LEX,'tau_cov':0.0,'delta_margin':0.0})
t0=time.time()
for _ in range(50):
    al.align('a compact subset of a Hausdorff space is closed', topk=5)
print(f'avg query time: {(time.time()-t0)/50*1000:.2f} ms')
"
```

Output in this container (2026-08-08):
```
rows (declarations): 251236
postings (name tokens): 5399
avg query time: 9.04 ms
```

This matches the bead's own reported measurement (251,236 / 5,399 / ~7.4ms in
its container) to the declaration/token count, confirming the drift is real
and reproducible, not a one-off. Query time varied 7.4ms → 9.0ms across two
runs in two different environments, which supports the bead's own read that
per-query timing is not a reproducible figure worth pinning to a hard number.

### Number changed

**`README.md:1162`** (was `README.md:1117` before unrelated prior edits):

- Old: `Index scale: 242,550 declarations, 5,609 name tokens, ~3 ms per lexical query.`
- New:
  ```
  Index scale, measured directly against `idx_full` (`len(art['rows'])`,
  `len(art['postings'])`, and 50 timed `Aligner.align` calls) as of 2026-08-08:
  **251,236** declarations, **5,399** name tokens. These move with mathlib and
  are not frozen; re-run the measurement rather than trusting this line. Per-
  query latency is hardware- and container-dependent and not a reproducible
  figure across environments, so it is omitted here rather than reported as a
  false constant.
  ```
- Justified by: the script above, run in this container on 2026-08-08.

I did **not** try to explain *why* name tokens went down (5,609 → 5,399) while
declarations went up (242,550 → 251,236). The bead flagged this as
"worth a second look... could be a real vocabulary/tokenization change, not
just mathlib grew" but that's a separate investigation (would mean reading
`mathgraph/index.py`'s tokenizer and diffing vocab, not just re-measuring),
and doing it wasn't necessary to fix the documented number — I noted the
caveat language instead of chasing the mechanism. If someone wants that
investigated, it should be its own bead.

### Query time: deliberately not pinned to a new number

Per the bead's own reasoning (which I agree with): per-query timing is
hardware/container-dependent, observed 7.4ms in the bead's run and 9.04ms in
mine on the same code and same-ish corpus. Publishing a new hard "~9ms" would
just be the next stale number. I reworded the sentence to state what varies
and why it's omitted, rather than replace one misleading constant with
another.

## What I left alone, and why

- **`README.md:326`** — `"places it at median rank ~250 of 242,550"`. This
  also references the old 242,550 declaration count, but it's embedded in a
  specific PFR present-arm benchmark result (recall@1 18.2%, recall@5 31.8%,
  97%-reach, median rank ~250) that is reproduced as a unit via
  `uv run python -m mathgraph.bench_pfr ...` (README.md:288-293), not a
  standalone "current index scale" fact like the line this bead targets.
  Whether it's drifted requires re-running that whole benchmark and checking
  if the entire present-arm table moved together — a different, bigger task
  than swapping one number, and out of this bead's scope (which names only
  the `README.md:1117` Index scale line). I filed **mathgraph-5hi** for this
  rather than touching it here.
- **`tests/test_corpus.py`, `README.md` 175→176 sweep** — already fixed by a
  prior session before I started (visible in `git diff tests/test_corpus.py`:
  `EXPECTED` values and the `176` assertion are already in place). Not part
  of my bead; I verified it's consistent with the current green test run but
  made no changes to it.

## Test suite

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

```
............................................................................
----------------------------------------------------------------------
Ran 76 tests in 106.343s

OK
```

All 76 tests pass — 0 failures. (The repo's documented "one known
pre-existing failure," `test_evaluated_on_the_documented_number_of_statements`
asserting 176, was already fixed by prior session work present in the working
tree before I started; my bead did not touch that test or need to.)

## What I could not verify

- Whether the 5,609 → 5,399 name-token drop is pure corpus growth or a real
  tokenizer/vocabulary change. Flagged above as future work, not resolved.
- Whether `README.md:326`'s 242,550/median-rank/97% figures have also
  drifted — filed as mathgraph-5hi instead of checking, per scope.

## What I decided not to do

- Did not touch `QUICKSTART.md` — grepped for the old numbers (242,550,
  5,609, 251,236, 5,399) and none appear there.
- Did not attempt to explain the token-count anomaly mechanistically (see
  above) — out of scope for "fix the drifted number."
- Did not re-run the PFR benchmark to check `README.md:326` — filed as a
  separate bead (mathgraph-5hi) instead, per the instruction not to expand
  scope mid-bead.

## Bead status

Closed `mathgraph-zzq` — evidence above (reproduction script output matching
the bead's own numbers, README updated with sourced/caveated figures, full
green test suite) satisfies the bead's stated closing criterion.

Filed `mathgraph-5hi` (P3) for the adjacent, out-of-scope `README.md:326`
question.

## Git state — NOT committed, per policy

```
$ git status
```
shows `README.md` modified (this bead's edit) plus pre-existing unstaged
changes from earlier sessions (`.gitignore`, `QUICKSTART.md`,
`mathgraph/bench_pfr.py`, `mathgraph/cli.py`, `tests/test_corpus.py`,
`.beads/interactions.jsonl`) and untracked files (`.beads/issues.jsonl`,
`.claude/settings.local.json`, `sandbox-prompt.md`) that predate my session
and were not touched by me.

Suggested commands for a human to run (not executed by me):

```
git add README.md
git commit -m "docs: re-measure and caveat idx_full index-scale numbers (mathgraph-zzq)"
```

The other pending changes in the tree are pre-existing and not mine to
commit/describe here.
