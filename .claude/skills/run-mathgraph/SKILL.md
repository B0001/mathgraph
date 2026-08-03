---
name: run-mathgraph
description: Run, build, test, benchmark, or probe mathgraph — the LaTeX-paper-to-mathlib4 alignment tool. Use when asked to start it, query or verify an alignment, reproduce the PFR benchmark, extract a paper's dependency graph, rebuild an index, run the test suite, or check to_additive reconstruction behaviour.
---

# Running mathgraph

A Python CLI, no GUI and no server. Retrieval is numpy-only; the corpus is
~1 GB of pre-built indices under `mathgraph-data/`.

The cost that shapes everything: **loading an index takes 4s (`idx_mathlib`)
to 21s and 2.7 GB (`idx_elaborated`), and the CLI pays it per invocation.**
Five probes through `uv run mathgraph` is a minute of pickle. So the agent
path is `driver.py`, which loads once and reads probes from stdin.

Paths below are relative to the repo root.

## Prerequisites

`uv` and nothing else — it manages the Python and the venv.

```bash
uv sync          # ~0s once synced; numpy is the only dependency
```

Graphviz (`dot`) is **not** installed here; `--dot` still writes the file.

## Run (agent path)

The driver is `.claude/skills/run-mathgraph/driver.py`. Feed it a heredoc —
one command per line, one index load for all of them:

```bash
uv run python .claude/skills/run-mathgraph/driver.py <<'EOF'
load idx_mathlib
prov
row Finset.sum_congr
additive Finset.prod_congr
truth Filter.le_zero_iff
query the entropy of a sum is at most the log of the cardinality
verify the sum of two continuous functions is continuous || Continuous.add
EOF
```

Nine probes in 17.6s, of which 4.3s was the load. Commands:

| command | what it gives you |
|---|---|
| `load [corpus]` | load an index — **any directory under `artifacts/`**, not just the four the CLI allows |
| `query <text>` | ranked candidates, structural reranker on (what `mathgraph query` runs) |
| `lex <text>` | same with the reranker off — isolates the lexical scorer |
| `verify <text> \|\| <Decl>` | the verdict JSON, without the CLI's exit-code semantics |
| `row <Decl.Name>` | the raw index row: `provenance`, `typ_tokens`, `head`, `module` |
| `prov` | provenance histogram — the fastest way to tell a stale index from a rebuilt one |
| `additive <Decl.Name>` | `names.to_additive_name` alone, no index needed |
| `truth <Decl.Name>` | is the name in the elaborated environment? (the `to_additive` ground truth) |
| `graph <tex glob>` | dependency-graph summary at `GRAPH_THRESHOLDS`, not wide open |
| `smoke` | the checklist below |

Everything prints JSON; errors print `!! message` and do **not** drop the
loaded index.

### Smoke test

```bash
uv run python .claude/skills/run-mathgraph/driver.py --smoke
```

14s, exit 0. Checks `to_additive_name` translation and its `None` case, both
branches of `type_tokens`' `elaborated` flag, index size, the third field
being populated, a 5-candidate query, `nonexistent` on an absent name, and
that the PFR graph abstains rather than guessing. With no corpus it runs the
four pure-logic checks, prints `SKIP every corpus check`, and still exits 0.

## Direct invocation

Most commits on this branch touch internals, not the CLI. Import them:

```bash
uv run python -c "
from mathgraph.names import to_additive_name
from mathgraph.index import type_tokens, find_ground_truth, expand_to_additive
print(to_additive_name('Finset.prod_congr'))
print(type_tokens('[T2Space X] : IsCompact s -> IsClosed s'))
"
```

`Aligner` and `Verifier` need a loaded index — go through the driver for
those rather than paying the load twice.

## Run (human path)

```bash
uv run mathgraph query "the entropy of a sum is at most the log of the cardinality" \
  --math 'd[X;Y] \leq \bbH[X+Y]' --topk 5              # 4.8s
uv run mathgraph verify "the sum of two continuous functions is continuous" \
  Continuous.add --profile permissive                   # 7.2s, exit 1
uv run mathgraph graph mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex \
  --json g.json --dot g.dot                             # 5.2s
uv run mathgraph bench                                  # 18.5s
```

`bench` reproduces the documented numbers exactly on the corpus as it stands:

```json
{"lexical":     {"n": 175, "recall@1": 0.189, "recall@5": 0.32},
 "+structural": {"n": 175, "recall@1": 0.2,   "recall@5": 0.389}}
```

## Test

```bash
uv run python -m unittest discover tests
```

62 tests, 103s with the corpus present. Without it: 0.002s, 14 skipped, still
`OK`. **`python -m unittest discover tests` without `uv run` fails on this
machine** — the ambient miniconda python raises `ImportError: Error importing
numpy`. QUICKSTART.md gives the bare form; it does not work here.

## Rebuild an index

`mathgraph setup` re-clones everything. To rebuild *only* the indices from
the already-scanned `mathlib.jsonl` — 22s, no network. Build beside the old
one rather than over it, so you can `prov` both:

```bash
uv run mathgraph index mathgraph-data/artifacts/mathlib.jsonl \
                       mathgraph-data/artifacts/idx_mathlib_new
```

It picks up `artifacts/mathlib_elab.jsonl` as ground truth automatically
(`index.find_ground_truth`). Output on this corpus:

```json
{"n_decls": 238592,
 "provenance": {"source": 230742,
                "to_additive:inferred:validated": 6986,
                "to_additive:explicit:validated": 864},
 "to_additive": {"inferred:dropped": 2863, "explicit:dropped": 153,
                 "inferred:untranslatable": 2819},
 "ground_truth_decls": 464208}
```

## Docker

Builds and reproduces `bench` identically (19s):

```bash
docker build -t mathgraph:0.1.0 .
docker run --rm -v "$PWD/mathgraph-data:/data" mathgraph:0.1.0 bench
```

`kubectl kustomize k8s/overlays/dev` renders. Nothing here was applied to a
cluster.

## Gotchas

- **The checked-in corpus is stale relative to HEAD, and it is stale in
  exactly the way this branch is about.** `prov` on the shipped `idx_mathlib`
  returns two-component provenance (`to_additive:inferred`, 9847 rows) and
  contains `Filter.le_zero_iff` — a name mathlib never generates. After the
  22s rebuild above: three-component (`to_additive:inferred:validated`, 6986),
  `Filter.le_zero_iff` gone, 3,016 inventions dropped. Also `Finset.sum_congr`
  goes from `typ_tokens: []` to populated. **Run `prov` before drawing any
  conclusion about `to_additive` or the third field**, or you will measure the
  July index against August code.
- **`--corpus` is a hardcoded `choices=` list** (`mathgraph/cli.py:54`). A
  freshly built index under any other name cannot be passed to the CLI at
  all — `invalid choice`. The driver's `load` takes any directory name, which
  is how you A/B a rebuild against the old one.
- **`verify` exits 1 for everything except `verified`.** QUICKSTART's own
  showcase example (`Continuous.add`) returns `rejected` and exits 1 — that is
  the calibration working, not a broken install. Do not wrap it in `set -e`.
- **`graph` on PFR reports no `matched` at all** — 184 unmatched, 23
  not_attempted, 11 ambiguous out of 218 claims. That is the abstention this
  tool exists for. A build that starts reporting `matched` here has had its
  thresholds loosened.
- **`idx_elaborated` costs 21s and 2.7 GB resident per load** (464,208 rows).
  It is the corpus where `"a compact set in a Hausdorff space is closed"`
  actually returns `IsCompact.isClosed` at rank 1, so it is worth the load —
  once, through the driver, not per CLI call.
- **Four modules are dead entry points.** `freeze_bench.py`, `bench_pfr.py`,
  `bench_dense.py` and `adapt.py` default to index names nothing builds
  (`idx_deploy`, `idx_mathlib_only`, `dense_mathlib.pkl.gz`), so
  `python -m mathgraph.freeze_bench` and `python -m mathgraph.bench_pfr` both
  die with `FileNotFoundError: 'idx_deploy/index.pkl.gz'`. `mathgraph bench`
  is unaffected — `cli.cmd_bench` reimplements the PFR benchmark against
  `idx_full` rather than calling `bench_pfr`. Related: `freeze_bench.py`
  defines `main` twice (lines 33 and 137); the second shadows the first.
- **`bench_release/` does not exist** and cannot currently be produced, though
  README.md and QUICKSTART.md both say the benchmark "ships frozen" there.
  Its generator is `freeze_bench.py`, which is one of the dead entry points
  above.
- **The Docker image contains only `mathgraph/`** — no `tests/`, no
  `.claude/`. The driver and the test suite run on the host.
- Repo sources are mode 0600; the Dockerfile's `chmod -R a+rX` exists for that
  reason. Don't drop it when editing the image.

## Troubleshooting

| symptom | fix |
|---|---|
| `ImportError: Error importing numpy: you should not try to import numpy from its source directory` | you ran bare `python`. Prefix `uv run`. |
| `missing index .../idx_mathlib` (CLI) or `!! no index at ...` (driver) | corpus absent — `uv run mathgraph setup` (~5-10 min, ~600 MB), or set `MATHGRAPH_DATA` to a populated one. |
| `argument --corpus: invalid choice` | see the hardcoded-choices gotcha — use the driver, or add the name to `CORPORA` in `cli.py`. |
| `bench` numbers drift from those above | the corpora moved; mathlib changes daily. There is no frozen fallback — see the `bench_release` gotcha. |
| `FileNotFoundError: 'idx_deploy/index.pkl.gz'` | you ran a module directly instead of the CLI — see the `idx_deploy` gotcha. |
| `dot: command not found` | graphviz isn't installed; the `.dot` file was still written. |
