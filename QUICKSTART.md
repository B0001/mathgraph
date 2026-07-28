# Running mathgraph on a laptop

Two commands to a working install, one long-running command to a working
corpus.

## Install

```bash
git clone <your-fork> mathgraph && cd mathgraph
uv sync                       # creates .venv, installs mathgraph + numpy
```

If you don't have uv:
`curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or
`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows).

Everything runs through `uv run mathgraph ...`, or activate the venv once
(`source .venv/bin/activate`) and call `mathgraph` directly.

## Bootstrap the corpus

```bash
uv run mathgraph setup
```

Clones mathlib4 (sparse + blobless, so ~150 MB rather than several GB) and
six blueprint projects, scans ~231k declarations, harvests ~1,071
paper-prose/declaration pairs, and builds three indices. **~5-10 minutes,
~600 MB on disk**, dominated by the clone. Resumable: every stage skips if
its output already exists, so an interrupted run costs nothing to repeat.

Put the data somewhere deliberate if you like:

```bash
export MATHGRAPH_DATA=~/corpora/mathgraph
uv run mathgraph setup
```

## The three things it does

**Rank candidate declarations for an informal statement.** Pass the formulas
too — they carry more signal than the prose does, and the structural
reranker is worth about +40% recall@5 over lexical alone.

```bash
uv run mathgraph query \
  "the entropy of a sum is at most the log of the cardinality" \
  --math 'd[X;Y] \leq \bbH[X+Y]' --topk 5
```

**Audit a proposed alignment.** This is the part that works well. Point it
at whatever produced the proposal — an LLM, a colleague, an old `\lean{}`
annotation you no longer trust:

```bash
uv run mathgraph verify "the sum of two continuous functions is continuous" \
  Continuous.add --profile permissive
```

Exit code is 0 for `verified`, 1 otherwise, so it drops into a shell
pipeline. `nonexistent` is an exact verdict — the name is not in the library,
including the ~10k declarations `@[to_additive]` generates and never writes
to source. `rejected` and `verified` are calibrated, not exact, and the
`reasons` field says which threshold decided it.

**Extract a paper's dependency graph.** Exact, no inference: `\label`,
`\ref`, and `\uses` are authored edges.

```bash
uv run mathgraph graph paper/*.tex --json g.json --dot g.dot
dot -Tsvg g.dot -o g.svg
```

## Reproduce the benchmark

```bash
uv run mathgraph bench
```

Expected, on the held-out PFR blueprint:

```json
{"lexical":     {"n": 175, "recall@1": 0.177, "recall@5": 0.291},
 "+structural": {"n": 175, "recall@1": 0.206, "recall@5": 0.366}}
```

If those numbers don't reproduce exactly, the corpora have moved on since
this was measured — mathlib changes daily. That is worth knowing and is
partly why the benchmark ships frozen in `bench_release/`, which does not
depend on a live checkout.

## Optional: real elaborated types

Everything above scrapes types out of Lean source with regexes, because it
has to run without a toolchain. With a built mathlib you can do better:

```bash
# in your mathlib4 checkout, once:
elan toolchain install $(cat mathlib4/lean-toolchain)
cd mathlib4 && lake exe cache get && lake build      # ~1 hour, ~15 GB

uv run mathgraph elaborate --mathlib /path/to/mathlib4
uv run mathgraph query --corpus idx_elaborated "..." --math '...'
```

This replaces scraped type text with pretty-printed, typeclass-resolved,
notation-expanded statements. The structural matchers read types as text, so
they consume the better input with no code changes — that interface was the
reason to shape them that way.

**Caveat, stated plainly:** the Lean side of this path (`lean/DumpDecls.lean`)
was written without a toolchain available to run it. The Python ingest is
tested against synthetic elaborated input and the matchers verified to
consume it; the Lean dumper itself is unrun. Expect to fix an API detail or
two against your mathlib version. Nothing else depends on it.

## Layout

```
mathgraph-data/
  mathlib4/            sparse checkout
  blueprints/          six projects, PFR held out for evaluation
  artifacts/
    mathlib.jsonl      scanned declarations
    blueprint_pairs.jsonl
    idx_mathlib/       absent-arm reference corpus
    idx_full/          + PFR, present-arm corpus
    idx_blueprint/     + blueprints, validation corpus
```

Delete `artifacts/` to rebuild indices without re-cloning; delete the whole
directory to start over.
