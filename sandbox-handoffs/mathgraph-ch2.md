# Handoff: mathgraph-ch2

**Status: closed.** Independently re-verified the uncommitted working-tree
diff this bead was tracking. Every number checks out against a fresh run.
Tree is ready to commit; this session did not commit (git policy).

## What this bead actually was

Not a code-change bead. A prior session had already made a batch of
re-measurement edits to `README.md`, `tests/test_corpus.py`,
`mathgraph/freeze_bench.py`, and `sandbox-prompt.md`, left them uncommitted,
and filed this bead in `in_progress` with a long self-written "I verified
this" report in the description, asking for a human (or a session with
commit authority) to review and commit. The parent task prompt told me
explicitly not to trust an in_progress bead's partial work at face value, so
I re-did the verification independently rather than reading the description
and closing on the strength of its own claims.

## What I actually ran, and what it produced

**Full suite** (`MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m
unittest discover tests`): `Ran 85 tests in 170.391s` / `OK`. Zero failures.
This is the known-good state described in the standing task prompt's "Known
baseline" section — except that baseline's one documented failure
(`test_evaluated_on_the_documented_number_of_statements`, 176 != 175) is
*already fixed*, and already **committed** at HEAD (591d4a9), not merely
present in the uncommitted tree as the bead's description claimed. Checked
this directly: `git show HEAD:tests/test_corpus.py` already asserts 176 at
that test. The bead's self-report was slightly wrong about where that fix
lives (uncommitted vs. committed) — doesn't change the verdict, since the
current tree (committed + uncommitted together) is what matters and it's
green either way, but I'm flagging the inaccuracy rather than silently
repeating it.

**`mathgraph.bench_pfr`**, run with the exact JSON blob README.md:297-299
now documents (`{"deploy": "idx_full", "mathlib_only": "idx_mathlib", ...}`
— note this is the *bare* index name, not `mathgraph-data/artifacts/idx_full`
as the old README said; that changed because `bench_pfr.main` now
unconditionally joins `MATHGRAPH_DATA/artifacts` onto whatever `deploy`
value it's given, a side effect of the unrelated fix in mathgraph-dgd. A
stale "mathgraph-data/artifacts/idx_full" value would double-join and 404 —
worth knowing if this bead's README diff is reviewed in isolation from
mathgraph-dgd's):

```
"absent": {"n": 174, "correct_abstention": 1.0, "false_match_rate": 0.0,
  "status": {"matched": 0, "ambiguous": 6, "unmatched": 168}}
"lexical_pool": {"n": 176, "reach_rate": 0.835, "median_rank": 42}
"combined_calibration": {"precision": 1.0, "answered": 3, "correct": 3,
  "n_present": 176, "n_absent": 174, "n_combined": 350}
"present": {"recall@1": 0.188, "recall@5": 0.318}
```

Matches the uncommitted README's claims exactly: the 168/6/0 status
breakdown (replacing a previously published 170/4/0), the 83.5%/rank-42
lexical pool figures, the 100%-on-3-of-350 calibration peak, and the raw
`0.188`/`0.318` that the README explicitly distinguishes from the rounded
18.2%/31.8% table entries (different code path — `arm_present` vs.
`cmd_bench`'s `StructReranker`, per README's own caveat).

**`mathgraph verify-bench`** and **`mathgraph verify-bench --patterns`**:

```
no-patterns:  permissive correct accept_rate 0.358, precise correct 0.085
              wrong_namespace n=21 (both profiles)
with patterns: permissive correct accept_rate 0.426, precise correct 0.165
```

Matches the README's verification-layer table (35.8%/42.6% permissive,
8.5%/16.5% precise) and the new `VerifyBenchAcceptRates` test class added to
`tests/test_corpus.py` in the same uncommitted diff — I ran the CLI
independently rather than just re-running the test, so this isn't the test
grading its own homework.

**`mathgraph.freeze_bench`** end to end, against a scratch dir
(`/tmp/bench_release_check`, cleaned up after):

```
{"present": 176, "absent": 174}
tasks.jsonl: 350 rows
```

176 + 174 = 350, consistent. This confirms the `freeze_bench.py` fix in the
uncommitted diff (real artifact names `idx_full`/`idx_mathlib` resolved
through `MATHGRAPH_DATA/artifacts`, replacing the nonexistent
`idx_deploy`/`idx_mathlib_only`) actually works — I invoked it with the
plain positional `out_dir` argument the file's real `__main__` block expects
(`main(sys.argv[1] if len(sys.argv) > 1 else "bench_release")` at line 185),
having first tripped over the fact that `freeze_bench.py` defines `main`
twice (lines 34 and 144 — a known, separately-tracked, unrelated issue noted
in `SKILL.md`) and does *not* take a JSON-blob argument the way
`bench_pfr.main` does. Passing a JSON string as `out_dir` on the first
attempt silently created a garbage path instead of erroring — worth knowing
if anyone else tries to invoke it that way.

## What I did not need to touch

`mathgraph/adapt.py`, `mathgraph/bench_dense.py`, `mathgraph/bench_pfr.py`,
and `.claude/skills/run-mathgraph/SKILL.md` are also modified in the working
tree, but they belong to sibling beads **mathgraph-2pj** and **mathgraph-dgd**
(both already closed, with their own handoffs at
`sandbox-handoffs/mathgraph-dgd.md` etc.), not to mathgraph-ch2. I read their
diffs and closed-bead reports to confirm the README's changed `bench_pfr`
invocation (bare `idx_full` instead of a full path) is a real, intended
consequence of their fix and not drift — it is. I did not re-verify their
bug fixes beyond that cross-check; they're out of this bead's scope and
already closed on their own evidence.

`.beads/interactions.jsonl` and `.beads/issues.jsonl` diffs are `bd`'s own
tracked issue records (new/updated bead entries for mathgraph-2pj, -dgd, -p14,
-jvx, -ch2, etc.) — tracker bookkeeping, not measurement content, exactly as
the bead's own description flagged.

## What I deliberately did not do

- **Did not commit.** CLAUDE.md's git policy and the standing task prompt
  both say not to commit without explicit authority; this bead's own
  description agrees ("no session should commit it unilaterally"). The tree
  is verified and ready; a human (or an explicitly-authorized session) should
  run:
  ```
  git add README.md tests/test_corpus.py mathgraph/freeze_bench.py sandbox-prompt.md
  git commit -m "..."
  ```
  separately review and decide on `.beads/*.jsonl`,
  `.claude/skills/run-mathgraph/SKILL.md`, `mathgraph/adapt.py`,
  `mathgraph/bench_dense.py`, `mathgraph/bench_pfr.py` (sibling beads'
  work, also verified-closed, also uncommitted) since they're not this
  bead's evidence trail even though they sit in the same working tree.
- **Did not touch `mathgraph-84a`** (QUICKSTART.md stale setup numbers),
  the other currently in_progress bead — unrelated scope, left alone.
- **Did not re-verify mathgraph-2pj/mathgraph-dgd's fixes from scratch** —
  cross-checked their effect on this bead's README diff (see above) and
  otherwise trusted their own closed-with-evidence reports, consistent with
  how much verification this bead's scope actually calls for.

## Final test-run line

```
Ran 85 tests in 170.391s

OK
```

## What I could not verify

Nothing load-bearing. Everything the bead's own description claimed to have
checked, I re-checked independently and it reproduced. The one thing I did
*not* independently confirm is the "three different `PYTHONHASHSEED` values"
and "float64 rescoring" claims in README.md:266-268 about the 168/6 result's
stability — I only re-ran the command once (getting 168/6, matching), not
under varied hash seeds or a float64 rescore, since that specific robustness
claim was mathgraph-p14's evidence bar (already closed, with its own handoff
at `sandbox-handoffs/mathgraph-p14.md`), not this bead's.
