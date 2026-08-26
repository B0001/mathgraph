# Handoff: mathgraph-dgd

Same `idx_deploy`/`idx_mathlib_only` wrong-artifact-name bug as mathgraph-2pj,
in the three call sites mathgraph-2pj explicitly left out of scope:
`bench_pfr.py`, `adapt.py`, `bench_dense.py`.

**Status: closed.** Fixed all three, reproduced each end-to-end, evidence
attached below.

## What was wrong

Same two-bugs-stacked-together pattern as `freeze_bench.py` before
mathgraph-2pj:

1. Wrong artifact names — `idx_deploy`/`idx_mathlib_only` don't exist; the
   real names built by `setup_cmd.py` are `idx_full` and `idx_mathlib` (see
   `mathgraph/cli.py:67` `CORPORA`, and this container's actual
   `/workspace/mathgraph-data/artifacts/` contents).
2. No `MATHGRAPH_DATA/artifacts` path prefix — `load()` takes a directory and
   looks for `index.pkl.gz` directly inside it; every other caller
   (`cli.py`'s `_art()`, `tests/test_corpus.py`'s `idx()`, and now
   `freeze_bench.py`) joins the name onto
   `os.path.join(MATHGRAPH_DATA, "artifacts", name)` first.

Per-call-site reachability check (the open question mathgraph-2pj left for
this bead): none of these three functions is ever called from anywhere else
in the codebase with an explicit override — `grep -rn` for
`bench_pfr\.main\|adapt\.build\|bench_dense\.main` outside their own defining
files returns nothing. Each is only reachable via
`python -m mathgraph.<module>` (the `if __name__ == "__main__":` block),
which calls the function with no arguments, so the wrong defaults are live
bugs, not dead code — same situation `freeze_bench.py` was in.

## The fix

Same pattern as `freeze_bench.py`'s fix (mathgraph-2pj), applied to each site:

**`mathgraph/bench_pfr.py`** (added `import os`):
```diff
-def main(deploy="idx_deploy", mathlib_only="idx_mathlib_only",
+def main(deploy="idx_full", mathlib_only="idx_mathlib",
          pattern="/home/claude/pfr/blueprint/src/chapter/*.tex", **kw):
     blocks = blueprint_blocks(pattern)
     out = {"blocks_with_gold": len(blocks)}
-    al = Aligner(load(deploy), **kw)
+    art_dir = os.path.join(os.environ.get("MATHGRAPH_DATA", "./mathgraph-data"), "artifacts")
+    al = Aligner(load(os.path.join(art_dir, deploy)), **kw)
     out["present"] = arm_present(al, blocks)
     out["lexical_pool"] = lexical_pool_stats(al, blocks)
-    al2 = Aligner(load(mathlib_only), **kw)
+    al2 = Aligner(load(os.path.join(art_dir, mathlib_only)), **kw)
```

**`mathgraph/adapt.py`** (added `import os`):
```diff
-def build(idx_dir="idx_deploy", pairs_path="blueprint_pairs.jsonl",
+def build(idx_dir="idx_full", pairs_path="blueprint_pairs.jsonl",
           decls_path="blueprint_decls.jsonl", holdout_prefix="PFR.",
           upsample=25, dim=192, pre_epochs=10, ft_epochs=6, seed=0,
           n_augment=2):
-    art = load(idx_dir)
+    art_dir = os.path.join(os.environ.get("MATHGRAPH_DATA", "./mathgraph-data"), "artifacts")
+    art = load(os.path.join(art_dir, idx_dir))
     rows = art["rows"]
```

**`mathgraph/bench_dense.py`** (added `import os`; these were hardcoded
strings, not parameters):
```diff
     blocks = blueprint_blocks("/home/claude/pfr/blueprint/src/chapter/*.tex")
     enc = DualEncoder.load(encoder)
+    art_dir = os.path.join(os.environ.get("MATHGRAPH_DATA", "./mathgraph-data"), "artifacts")

-    art_d = load("idx_deploy")
+    art_d = load(os.path.join(art_dir, "idx_full"))
     ...
-    art_m = load("idx_mathlib_only")
+    art_m = load(os.path.join(art_dir, "idx_mathlib"))
```

## Evidence this closes the bead

Ran each fixed function against the real corpus at `/workspace/mathgraph-data`,
no symlinks, no monkeypatching of the artifact-loading code (only the
unrelated `/home/claude/pfr/...` default `pattern`/`encoder` paths, which
don't exist in this container and are a separate, still-open issue — see
"Left alone" below).

**`bench_pfr.py`** — explicit `pattern` pointing at the real blueprint dir,
everything else default:
```
$ MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m mathgraph.bench_pfr \
    '{"pattern": "/workspace/mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex"}'
```
Ran to completion, printed full JSON. Key figures: `lexical_pool.n: 176`,
`absent.n: 174` — matches `freeze_bench.py`'s `{"present": 176, "absent": 174}`
from mathgraph-2pj's evidence, as expected since both draw from the same
`idx_full`/`idx_mathlib` corpus and the same blueprint blocks.

**`adapt.py`** — first confirmed the artifact load succeeds with zero
arguments (fails later, on unrelated cwd-relative `pairs_path`/`decls_path`
defaults — same class of issue as the pattern path above, not this bug):
```
$ MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -c \
    "from mathgraph.adapt import build; build(pre_epochs=1, ft_epochs=1)"
FileNotFoundError: [Errno 2] No such file or directory: 'blueprint_decls.jsonl'
```
Then ran it fully end-to-end with explicit paths to the real files under
`$MATHGRAPH_DATA/artifacts/`:
```
$ MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -c "
from mathgraph.adapt import build
enc = build(pairs_path='/workspace/mathgraph-data/artifacts/blueprint_pairs.jsonl',
            decls_path='/workspace/mathgraph-data/artifacts/blueprint_decls.jsonl',
            pre_epochs=1, ft_epochs=1)
print('OK', type(enc))
"
docstring pairs 70076  blueprint pairs 439
  pre: pairs=69093 |Ve|=4338 |Vt|=13681 dim=192
  pre: epoch 1: loss 1.4432  in-batch top1 0.697
adaptation mixture 162102
  ft : pairs=150600 |Ve|=4338 |Vt|=13681 dim=192
  ft : epoch 1: loss 1.0092  in-batch top1 0.753
OK <class 'mathgraph.dense.DualEncoder'>
```
Trained a real `DualEncoder` on the real docstring + blueprint-pair corpora.

**`bench_dense.py`** — needs a `DualEncoder` file (default `dense_mathlib.pkl.gz`
doesn't exist anywhere in this container — separate issue, see "Left alone").
Trained a small one with `adapt.build` (`dim=32`, 1 epoch each stage, saved
to `/tmp/dense_test.pkl.gz`), then monkeypatched only `blueprint_blocks`
(again, the unrelated hardcoded `/home/claude/pfr` pattern) to point at the
real corpus, leaving the fixed `load(os.path.join(art_dir, ...))` calls
untouched:
```
$ MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -c "
import mathgraph.bench_dense as bd
from mathgraph.bench_pfr import blueprint_blocks as real_bb
bd.blueprint_blocks = lambda pattern: real_bb('/workspace/mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex')
out = bd.main(mode='dense', encoder='/tmp/dense_test.pkl.gz')
print(out['present']); print(out['absent'])
"
{'n': 176, 'recall@1': 0.028, 'recall@5': 0.034}
{'n': 174}
```
`n: 176`/`174` again matches the other two arms — confirms `idx_full` and
`idx_mathlib` both loaded correctly through the fixed path. (The low
recall numbers are expected and not a concern: 1-epoch, dim=32 toy encoder
trained only to prove the loading path works, not a real benchmark run.)

## SKILL.md gotcha revisited

`.claude/skills/run-mathgraph/SKILL.md`'s "Four modules are dead entry
points" gotcha (previously lines 183-194) described all four modules as
broken on `idx_deploy`/`idx_mathlib_only`. Rewrote it to say the bug is fixed
in all four (crediting mathgraph-2pj + mathgraph-dgd), while keeping the two
things that are **not** fixed and are still real:

- `bench_pfr.py`/`bench_dense.py`'s default `pattern` is
  `/home/claude/pfr/blueprint/src/chapter/*.tex`, which does not exist in
  this container (confirmed above — I had to override it in every test run).
- `bench_dense.py`'s default `encoder="dense_mathlib.pkl.gz"` is not produced
  by anything in this repo (confirmed — had to train a throwaway one).

Also rewrote the adjacent "`bench_release/` does not exist" gotcha, since
mathgraph-2pj made `freeze_bench.py` work — it's not a dead entry point
anymore, just not checked in.

Updated the troubleshooting table: removed the
`FileNotFoundError: 'idx_deploy/index.pkl.gz'` row (that failure mode no
longer occurs) and added two new rows for the pattern/encoder defaults above,
since those are now the actual failure modes an agent running these modules
directly will hit.

I did **not** touch the `freeze_bench.py` double-`def main`
(lines 34/144, second shadows first) mention in that same paragraph — still
true, still unrelated to this bug, left as a documented gotcha rather than
fixed.

## Left alone / out of scope, filed separately

Nothing new filed — both remaining issues (`/home/claude/pfr` default
pattern, `dense_mathlib.pkl.gz` default encoder) were already visible in
`SKILL.md`'s prior gotcha text before I started (implicitly, as part of the
same paragraph); I made them explicit troubleshooting/gotcha entries rather
than filing new beads, since they're documentation-only fixes (pointing at
the real failure) and don't need code changes to be "resolved" in the sense
this bead's acceptance criteria cares about. If someone wants those modules
runnable with zero arguments in this container, that would be new code-change
scope — did not do that, since it's outside "the same idx_deploy bug."

## Test suite

```
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```
Final line, verbatim:
```
Ran 85 tests in 179.825s

OK
```
**85/85 passed, 0 failures.** Matches the "known-good" state described in
standing session context — the documented `176 != 175` pre-existing failure
is not present because it was already resolved by other uncommitted work
already sitting in the tree before I started (same pre-existing diff to
`tests/test_corpus.py`/`README.md`/`sandbox-prompt.md` that mathgraph-2pj's
handoff also found and left untouched — not mine, not part of this bead).

## What I did not do, and why

- Did not fix the `/home/claude/pfr` hardcoded default `pattern` in
  `bench_pfr.py`/`bench_dense.py`, or the `dense_mathlib.pkl.gz` default
  `encoder` in `bench_dense.py` — different bug (wrong/missing default file,
  not wrong artifact *name*), outside "the same idx_deploy/idx_mathlib_only
  bug" this bead is scoped to. Documented both in SKILL.md instead so the
  next agent doesn't have to rediscover them by trial and error.
- Did not touch `freeze_bench.py`'s double-`def main` — unrelated, already
  known, already documented, not this bug.
- Did not touch the pre-existing uncommitted diffs to `README.md`,
  `tests/test_corpus.py`, `sandbox-prompt.md`, `.beads/*.jsonl` that were
  already in the working tree when I claimed this bead (same state
  mathgraph-2pj's handoff describes) — not part of this bead, left exactly
  as found.
- Did not investigate `.claude/settings.local.json` (untracked, pre-existing)
  — unrelated to this bead.
- Did not commit or push, per git policy (conservative profile, no explicit
  authority granted).

## What I could not verify

Nothing outstanding for this bead's own scope — every artifact-loading fix
was exercised against the real corpus and produced consistent `n=176`/`174`
counts across all three modules plus `freeze_bench.py`, which is stronger
cross-checking than mathgraph-2pj alone had available. I did not attempt a
full, unmodified `python -m mathgraph.bench_pfr` / `bench_dense` /
`adapt` invocation with zero CLI overrides end-to-end, because those still
hit the separate, pre-existing `/home/claude/pfr` / `dense_mathlib.pkl.gz`
default-path problems described above — that's expected given this bead's
scope, not something left unverified within scope.

## Git state at handoff

Not committed, per git policy. `git status --short`:

```
 M .beads/interactions.jsonl      (bd claim/close side effects, this bead + pre-existing)
 M .beads/issues.jsonl            (bd claim/close side effects, this bead + pre-existing)
 M .claude/skills/run-mathgraph/SKILL.md   (mine — gotcha/troubleshooting rewrite)
 M README.md                      (pre-existing, not mine)
 M mathgraph/adapt.py             (mine — the fix)
 M mathgraph/bench_dense.py       (mine — the fix)
 M mathgraph/bench_pfr.py         (mine — the fix)
 M mathgraph/freeze_bench.py      (pre-existing, from mathgraph-2pj, not mine)
 M sandbox-prompt.md              (pre-existing, not mine)
 M tests/test_corpus.py           (pre-existing, not mine)
?? .claude/settings.local.json    (pre-existing, untracked, not mine)
```

Suggested next commands for a human, scoped to just this bead's changes:

```bash
git add mathgraph/bench_pfr.py mathgraph/adapt.py mathgraph/bench_dense.py \
        .claude/skills/run-mathgraph/SKILL.md
git commit -m "fix: bench_pfr.py, adapt.py, bench_dense.py load idx_full/idx_mathlib via MATHGRAPH_DATA/artifacts, not nonexistent idx_deploy/idx_mathlib_only

Same bug and fix pattern as freeze_bench.py (mathgraph-2pj). Also updates
SKILL.md's gotcha/troubleshooting sections to match: the idx_deploy bug is
gone, but bench_pfr.py/bench_dense.py's default blueprint pattern
(/home/claude/pfr/...) and bench_dense.py's default encoder
(dense_mathlib.pkl.gz) still don't exist in this container -- documented as
separate, still-open issues."
```

(Leaving the other pre-existing modified files, which belong to unrelated
work, for whoever owns that to commit separately — same as mathgraph-2pj's
handoff.)
