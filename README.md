# mathgraph

Takes a LaTeX paper, recovers its dependency graph, and tries to align each
statement against a formal library (mathlib4). Statements it cannot place are
flagged as unmatched rather than attached to the nearest plausible lemma.

The abstention is the feature. Everything downstream of an alignment layer
inherits its errors silently — a wrong lemma reference looks exactly like a
right one — so the layer has to be able to say nothing, and the rate at which
it wrongly says something has to be measured rather than assumed.

It was measured, on two benchmarks with genuine negative arms. The result is
in [Benchmarks](#benchmarks) and it is largely negative: abstention is perfect
on real paper text, retrieval is weak, and **neither benchmark admits an
operating point where the alignment is trustworthy**. Maximum achievable
precision is ~15% on the library benchmark and 100% on 3 answers out of 350 on
the paper benchmark (re-measured against the current scorer; see the
[combined-arm sweep](#benchmarks) below — the previously reported ~67% on 349
was stale on both counts).

So the usable output of this tool is the exact internal graph plus a *flagged,
ranked candidate list for a human to check* — not an assertion layer. That
conclusion is stated here rather than buried, because a tool of this shape
that is trusted at face value is worse than no tool.

---

## Pipeline

```
Lean source ──▶ leanscan ──▶ index ──▶ align ──▶ graph
LaTeX paper ──▶ latex   ─────────────────┘
```

| module | what it does |
|---|---|
| `leanscan.py` | line-oriented Lean 4 scanner: declarations, namespaces, docstrings, attributes. No toolchain needed. |
| `names.py` | name tokenization; reconstruction of `@[to_additive]`-generated declarations |
| `index.py` | inverted index, IDF, and the learned English→mathlib translation table |
| `align.py` | three-valued scorer: `matched` / `ambiguous` / `unmatched` |
| `dense.py` | dual encoder trained contrastively on the docstring corpus |
| `bench_dense.py` | scores the dense and hybrid retrievers on the same two arms |
| `harvest.py` | mines paper-prose/declaration pairs from public blueprint projects |
| `adapt.py` | domain adaptation of the encoder onto paper prose |
| `freeze_bench.py` | packages the PFR benchmark as a standalone dataset + stdlib scorer |
| `verify.py` | verification layer: audits an externally proposed alignment |
| `mathsym.py` | formula symbol extraction; the bag-of-symbols negative result |
| `structmatch.py` | flat formula skeletons; the reranker that first beat lexical |
| `treematch.py` | side-aware operator trees |
| `argmatch.py` | alpha-canonical argument patterns (feeds the verifier) |
| `setup_cmd.py` | `mathgraph setup`: resumable corpus bootstrap |
| `leanast.py` | ingest for real elaborated Lean types (optional path) |
| `latex.py` | theorem environments, `\label`/`\ref`, and `leanblueprint` `\uses`/`\lean` markup |
| `graph.py` | assembles the DAG; keeps authored edges distinguishable from inferred ones |
| `evaluate.py` | docstring benchmark with a genuine negative arm |
| `bench_pfr.py` | real-paper benchmark against Tao's PFR blueprint |

## Usage

Install and bootstrap (see [QUICKSTART.md](QUICKSTART.md) for detail):

```bash
uv sync                  # .venv + numpy, nothing else
uv run mathgraph setup   # clone corpora, build indices (~5-10 min, ~600 MB)
```

Then:

```bash
uv run mathgraph query  "<informal statement>" --math '<latex>' --topk 5
uv run mathgraph verify "<informal statement>" Some.Declaration
uv run mathgraph graph  paper/*.tex --json g.json --dot g.dot
uv run mathgraph bench                       # reproduce the PFR numbers
uv run mathgraph elaborate --mathlib ...     # optional: real Lean types
```

`verify` exits 0 on `verified`, 1 otherwise, so it composes in a shell
pipeline. Runtime dependency is numpy alone; the corpora are fetched locally
and never packaged.

---

## Three things worth stealing even if the rest is discarded

### 1. `to_additive` declarations do not exist in source

About 14,000 mathlib declarations are generated at elaboration time by
`@[to_additive]` and never appear as text. `Finset.sum_congr` is one of them.
Any index built by scanning source silently lacks them, and lacking a
declaration is indistinguishable from a paper using something novel — which
corrupts exactly the signal this tool exists to produce.

`names.py` implements the multiplicative→additive name translation and
recovers **11,043** of them. Each carries `provenance: to_additive:inferred`
or `:explicit`, so a match can always be traced to how the name got here.
**2,819** remain untranslatable and are reported as a known gap.

**The reconstruction is a guess, and its error rate is now measured.** Checked
against a real elaborated environment — the ground truth, since `to_additive`
runs at elaboration time — **29.1%** of the inferred names (2,863 of 9,847) do
not exist: `Filter.le_zero_iff`, `Filter.NeBot.le_zero_iff` and
`Filter.EventuallyEq.mulIndicator_zero` are not declarations. The dictionary
in `names.py` is applied unconditionally, and mathlib's real naming has
exceptions it does not encode.

The explicitly named twins are a different story, and used to be a worse one.
They were 11.9% wrong (117 of 981) when this was first audited, for a reason
that turned out to be a plain bug rather than dictionary coverage — see
[the explicit names](#the-explicit-names-were-resolved-in-the-wrong-namespace)
below. Resolving them the way mathlib does takes them to **2.8%** (34 of
1,196).

**The ground truth is now wired in, and it is optional by construction.** If
`mathgraph elaborate` has been run, `index.build` checks every reconstruction
against the elaborated environment and drops the ones it contradicts. If it
has not — the laptop path, with no Lean toolchain — every reconstruction is
kept and says so. The provenance carries the answer as a third component:

| provenance | meaning |
|---|---|
| `to_additive:inferred:validated` | reconstructed, and the environment confirms it exists |
| `to_additive:inferred:unvalidated` | reconstructed, nothing checked it |
| `to_additive:explicit:validated` / `:unvalidated` | same, for an explicitly named twin |

Absence is only read as evidence inside a module the environment covers. A PFR
or blueprint declaration is missing from a mathlib environment because mathlib
does not contain it, not because it does not exist, so outside those modules
the reconstruction stands and is marked `:unvalidated`. Rebuilding the shipped
corpora against a 464,208-declaration environment drops **2,897** names
(2,863 inferred + 34 explicit) and validates 8,148. Each index reports its own
counts in `meta.json`.

### The explicit names were resolved in the wrong namespace

The explicit drops used to be 153, and four of them said what was wrong.
`@[to_additive prod]` on `Submonoid.FG.prod` was reconstructing a **root-level
`prod`** — not a declaration, which is why the environment dropped it. (In
`idx_full` those four were dropped only 149 times, because PFR declares a
`prod` of its own and they collided with a name already present. A count that
moves with the corpus is usually a bug wearing a disguise.)

The rule mathlib implements is in `Mathlib/Tactic/Translate/Core.lean`, in
`targetName`, and it is not guessable: an explicit argument names the twin's
**last components**, and the namespace it lands in is the source's,
*additively translated*. So `@[to_additive prod]` on `Submonoid.FG.prod` is
`AddSubmonoid.FG.prod`. The twin keeps the depth of the source — the
translated namespace gives up one trailing component per component the
explicit name has beyond its first — and a `_root_` prefix opts out and names
the twin absolutely. `names.py` was instead appending the explicit name to the
*scraped* `namespace` field: untranslated, and empty for 432 of the 1,011
short-name cases, which is how a root-level `prod` gets invented.

Ported in `explicit_additive_name`, and scored against the environment over
all 1,228 explicit reconstructions:

| | in the environment |
|---|---|
| appending to the scraped namespace | 1,075 / 1,228 (87.5%) |
| **mathlib's rule** | **1,194 / 1,228 (97.2%)** |

Errors fall from 153 to 34 and `explicit:validated` rises from 864 to 1,162 —
larger than the 119 net correction, because a wrong name that happened to
already exist in the scraped source was silently skipped rather than added at
all.

**And it moved a threshold, on the arm that is easy to forget.** On the
validated corpus `GRAPH_THRESHOLDS` was unaffected — still 16 answered, 11
correct, zero false. On the *unvalidated* one, where 1,196 explicit
reconstructions are now kept under different names and nothing filters them,
`0.2525/0.2649` picked up one false match. Refitting against both arms again
gives `0.2525/0.2650`: one ten-thousandth, no change in yield, clean on both.
That is twice now that this operating point has moved by the last digit under
a corpus change, which is the honest measure of how much slack it has. The
verifier profiles moved by at most 0.5pt on one arm and were left alone.

Two of the 34 survivors are worth naming, because they are a *third* bug and
not this one. `Left.one_lt_mul` carries the attrs string
`@[to_additive add_pos_of_left] alias one_lt_mul_of_left := ...` — the scraper
has swallowed an attribute belonging to a neighbouring `alias`, so the
explicit name is being read off the wrong declaration entirely. The old rule
happened to get those two right by being wrong in a compensating direction.
`leanscan.py`'s attribute capture is the thing to fix, and it is not fixed
here.

This is what it does to `nonexistent`, which is the verdict that motivated the
work. On a validated mathlib-only index every surviving reconstruction is
confirmed, so `nonexistent` is exact in **both** directions. On `idx_full` and
`idx_blueprint` it is not: 48 and 78 reconstructions respectively sit in PFR
and blueprint modules the mathlib environment does not cover, and those remain
unvalidated. Without an elaborated corpus nothing is validated and the old
caveat stands in full — `nonexistent` is sound, and its absence merely
probable. Read `provenance`; it is the only signal that distinguishes the
three cases.

Retrieval barely moves, and the direction it moves is worth stating precisely.
`bench` is unchanged on the lexical arm (18.9/32.0) and gains one statement on
`+structural` r@1 (20.0 → 20.6). On the 439 blueprint pairs the abstention arm
goes from 14 answered / 9 correct to 16 answered / 11 correct. But both new
answers crossed `tau_cov` on **coverage** (0.238 → 0.257 and 0.243 → 0.269)
while their margins did not move, so the gain is an IDF side-effect of a corpus
3,012 declarations smaller, not better matching. Two statements sitting within
0.02 of a fitted threshold is not a robust improvement.

That paragraph used to end "with zero false matches in both", and it was
wrong: at the old `0.2474/0.2671` the validated corpus admits **three** false
matches on that arm. The thresholds have been refitted and the claim now
holds — see "Refitting against a validated corpus" below.

### 2. The English→mathlib dictionary is learned, not written

Papers say "commutative"; mathlib says `comm`. Papers say "converges";
mathlib says `tendsto`. The ~67,000 declarations carrying docstrings are a
parallel corpus between the two vocabularies, sitting unused in the
repository.

PMI over that corpus, shrunk by `c/(c+25)` to suppress rare-pair coincidences,
yields 2,930 translations. A sample, none of them hand-authored:

| paper word | top mathlib tokens |
|---|---|
| convergence | `tendsto`, `uniform`, `series` |
| homomorphism | `hom`, `monoid`, `ring` |
| isomorphism | `iso`, `equiv` |
| commutative | `comm`, `ring`, `monoid` |
| injective | `injective`, `inj` |
| bounded | `bounded`, `bdd`, `bound` |
| derivative | `deriv`, `iterated`, `within` |

Mathlib also abbreviates aggressively (`symm`, `assoc`, `bdd`), so a prefix
index sits alongside the PMI table and catches those without a hand-written
abbreviation list.

### 3. Authored edges and inferred edges are different objects

`graph.py` emits `depends_on` edges read directly off `\label`/`\ref`/`\uses`
— exact, no inference — and `aligns_to` edges that are retrieval guesses
carrying status and score. They are never merged. A consumer that cannot tell
them apart will eventually treat a guess as a fact, which is the failure mode
this whole design is arranged to prevent.

---

## Benchmarks

### The real one: PFR blueprint

Terence Tao's Polynomial Freiman-Ruzsa blueprint is ordinary research prose
carrying author-written `\lean{...}` annotations — a gold alignment over
real paper text, which is the actual task. Docstring retrieval only
approximates it, and flatters it.

179 annotated statements, split into two arms.

**Absent arm** — only mathlib indexed, so 174 of the 179 statements have no
correct answer anywhere in the index (5 already have an answer in mathlib
alone):

| metric | value |
|---|---|
| correct abstention | **100%** |
| false matches | **0** |
| status breakdown | 170 unmatched, 4 ambiguous, 0 matched |

**Present arm** — the paper's own formalization added to the index, so every
statement has a correct answer:

| metric | value | before the length-normalisation fix |
|---|---|---|
| recall@1 | **18.2%** | 7.4% |
| recall@5 | **31.8%** | 20.0% |

The present arm is **176** statements as of the scanner fix below, not the 175
every table before it reports, and recall is measured against a corpus ~11k
declarations larger. Both effects are that fix, and comparisons across it are
not like-for-like — see [what the scanner was
dropping](#the-scanner-was-dropping-11000-declarations).

Both arms re-measured on the same corpus after the scoring fix described in
[Length normalisation](#length-normalisation-was-backwards); the "before"
column is the old scorer on that same corpus, so the delta is a like-for-like
comparison. Abstention is unaffected — still zero false matches.

**Calibration sweep over both arms combined.** Best achievable precision is
**100%, on 3 answers out of 350** (`176` present + `174` absent — an
exhaustive threshold sweep treating both PFR arms as one pool, an "answer" is
any statement clearing the threshold, and it is correct only if it's a
present-arm statement whose rank-1 candidate is gold; every absent-arm answer
is wrong by construction). Reproduce with:

```
uv run python -m mathgraph.bench_pfr \
  '{"deploy": "mathgraph-data/artifacts/idx_full", "mathlib_only": "mathgraph-data/artifacts/idx_mathlib", "pattern": "mathgraph-data/blueprints/pfr/blueprint/src/chapter/*.tex", "len_pivot": 0.75, "mod_weight": 0.1, "typ_weight": 0.15, "prefix_weight": 0.85, "title_boost": 2.5}'
```

and read `combined_calibration` off the output. That same JSON also prints
`present.recall@1` as **0.188**, not the 18.2% above — `bench_pfr.py`'s
`arm_present` scores present-arm recall through `Aligner.align` directly,
which is a different code path from `cmd_bench`'s `StructReranker` used for
the published present-arm table, and the two disagree by one statement at the
rank-1 boundary (recall@5 matches exactly, at 31.8%/0.318 either way). Both
numbers are real and reproduce; the 18.2% table above is the canonical one.
See mathgraph-7dw and `arm_present`'s docstring.

This replaces a previously reported "~67%, on 3 answers out of 349" that no
script in this repository reproduced: 349 was arithmetically 175 (the present
arm's pre-scanner-fix
count) + 174 (the absent arm), and no combined-arm sweep existed in code to
produce the 67% either. The scorer has changed twice since that figure was
written (length normalisation, the type field) and the peak the current
scorer reaches is higher, not lower — this is a re-measurement, not a
different methodology chosen to move the number.

There is still no operating point that is both useful and trustworthy: 3
answers out of 350 is 0.9% coverage, too small a sample for 100% precision to
mean anything, and the coverage and margin statistics do not separate correct
matches from incorrect ones on this input at any threshold that answers more
than a handful.

### Why

Median statement: **13 English words against 4 formula blocks**. Lexical
matching has an intrinsic ceiling on formula-dense prose, and ~29% recall@5 is
approximately where it sits. The failure is not in the plumbing:

- the lexical stage's pre-rerank pool (`StructReranker`'s shipped `depth=10000`)
  contains the gold declaration **83.5%** of the time (147 of 176 present-arm
  statements)
- when it does, gold sits at **median rank 42** within that pool, out of
  **251,236** declarations in the index overall

Reproduce with `bench_pfr`'s `lexical_pool` field (same command as the
[combined-arm sweep](#benchmarks) above). This replaces a previously reported
"97% / median rank ~250 of 242,550" that no script in this repository
reproduced — no code computed this stat at all before this measurement was
added, so there is no way to confirm whether 97%/250 held under the
then-current scorer and corpus or was already stale when written. Both the
scorer (see "Length normalisation was backwards" below) and the corpus
(176 vs the old 175, 251,236 vs the old 242,550 declarations) have changed
since, and the shift is not a small drift: reach dropped 97%→83.5% while
median rank improved 250→42. So this is now **partly** a retrieval problem,
not purely a ranking one — 16.5% of present-arm statements never put gold in
front of the reranker at all, a revision from the "ranking problem, not a
retrieval problem" framing this section previously asserted outright.

For what does reach the pool, a linear reranker trained listwise on ~7,000
groups produced **no measurable lift** once a training-population bug was
fixed. Token-overlap features do not contain enough to rank with. That
reranker is *not* in this repository: it was described here as retained, but
the module never existed in the tree, and the only trace was a dead `from
.rerank import featurize` inside a branch nothing could reach. Both have been
removed rather than left to imply a component that is not there. The negative
result is recorded here, which is the part that was actually worth keeping.

### Length normalisation was backwards

Some of that "intrinsic ceiling" was not intrinsic. Two bugs in the lexical
scorer were found by querying it with a statement whose answer is not in
doubt — *a compact subset of a Hausdorff space is closed*, which is
`IsCompact.isClosed` — and reading what came back instead:

```
TopologicalSpace.Compacts.isCompact_subsets_of_isCompact
TopologicalSpace.Compacts.isClosed_subsets_of_isClosed
TopologicalSpace.Compacts.subset_of_mem_compactNhds
```

**1. Dividing by the L2 norm rewards long names.** The score was
`raw / max(‖doc‖₂, 3)`. Nothing normalises the query side, so this is not a
cosine — and for a declaration whose *k* name tokens all match, raw grows like
*k* while ‖doc‖₂ grows like √*k*, so the score grows like √*k*. Longer name,
higher score, mechanically. That is exactly backwards for mathlib, where the
short name is the general lemma and the long one is a corner case of it:
`IsCompact.isClosed` (4 tokens, matched 3) scored 1.49 against
`…isCompact_subsets_of_isCompact` (9 tokens, matched 7) at 2.07.

Replaced with BM25-style pivoted length normalisation over the declaration's
own IDF mass, `(1-p) + p·len/avg_len` at `p = 0.75`, chosen on the blueprint
validation corpus with PFR untouched.

**2. Query expansion could outweigh the query.** A word is expanded by stem,
by shared prefix, and through the PMI table, and each expansion's downstream
contribution is `weight × IDF(expansion)` — with nothing bounding the IDF of
what it lands on. So `compact` (IDF 5.0) reached `companion` (IDF 11.3) via the
4-character prefix bucket and, at weight 0.85, `companion` became the single
heaviest term in a query about compact sets. Ahead of `compact` itself.

An expansion is a *hypothesis* about what mathlib calls a word; it cannot be
better evidence than the word actually written. Capping each expansion's IDF at
its source word's fixes it without a hand-written stoplist.

| PFR present arm | r@1 | r@5 | r@10 |
|---|---|---|---|
| lexical, before | 9.1% | 20.0% | 25.1% |
| lexical, after | **18.9%** | **32.0%** | — |
| + skeleton, before | 11.4% | 27.4% | 32.0% |
| + skeleton, after | **20.0%** | **38.9%** | — |

Roughly a doubling of recall@1 on the held-out paper benchmark, and the
library benchmark moved by a similar factor independently. **Abstention is
unchanged: still zero false matches on the absent arm.** The conclusion of
this README does not change — the numbers are better and still nowhere near
trustworthy — but a good deal less of the gap was a property of the task than
this document previously claimed.

The general lesson is the transferable part: **`raw / ‖doc‖₂` is only a
length correction when the query side is normalised too.** Where it is not,
it is a length *bonus*, and it is invisible because the ranking still looks
plausible — every result here was a topology lemma about compact sets.

### The type is a third indexed field

`DumpDecls.lean` had never been run. Running it against a built mathlib
produces **480,883 declarations with elaborated types** — typeclass-resolved,
notation-expanded — and immediately shows what a name index cannot see:

```
IsCompact.isClosed
  ∀ {X} [TopologicalSpace X] [T2Space X] {s : Set X}, IsCompact s → IsClosed s
```

`[T2Space X]` is the Hausdorff hypothesis. It is in the type and **nowhere in
the name**, so no amount of name-token matching reaches it from the word
"Hausdorff". 1,574 declarations carry it.

Building the elaborated corpus alone changed nothing, because `index.build`
tokenized only `name` and `module`; the type sat in `head`, read exclusively
by the structural rerankers, which need `--math` to fire. The corpus knew
`T2Space` and the retriever could not see it. So the type's identifiers are
now a third indexed field alongside name and module tokens, at `typ_weight`,
excluding whatever the name already says.

| typ_weight | BP r@1/r@5 | PFR r@1/r@5 |
|---|---|---|
| 0.0 (names + modules only) | 20.3 / 29.8 | 17.7 / 29.7 |
| **0.15** | **21.0 / 30.3** | **18.9 / 32.0** |
| 0.3 | 20.3 / 30.8 | 14.9 / 32.6 |
| 0.5 | 17.1 / 29.8 | 13.1 / 31.4 |
| 1.0 | 8.7 / 21.0 | 7.4 / 20.0 |

**The weight had to be fitted, and fitting it to the motivating query would
have been a disaster.** At `typ_weight=0.5` the compact-Hausdorff query ranks
its answer first — and PFR r@1 collapses from 18.9% to 13.1%. The blueprint
optimum is 0.15, where that query reaches rank 3 instead of rank 1. One query
is not a benchmark, and this is the clearest demonstration in this repository
of why.

Source-scanned indices benefit too: the regex-scraped `head` carries type text
of lower quality, and `idx_mathlib` moves the same query from unranked to
rank 3 without any Lean toolchain at all.

Three latent bugs surfaced, all because the script had never been executed:
`lean/DumpDecls.lean` was at the repository root while `leanast.dump()` and
this README both looked for it under `lean/`; `mathgraph setup` makes a
shallow *sparse* clone containing only `Mathlib/`, so `Cache/` and everything
lake needs was missing; and the dumper called `Options.setNat`, which no
longer exists now that `Options` is a structure rather than an alias for
`KVMap`.

### Recalibration after the fix

Changing a scorer silently invalidates every constant fitted against it, so
all three sets were re-derived on the 439 non-PFR blueprint pairs — against a
genuine negative arm, built by running the same statements at a mathlib-only
index where their answer does not exist — and then transferred to PFR
untouched. Only two constants actually moved:

**Abstention (`graph`).** The old `tau_cov=0.35 / delta_margin=0.08` answered
**1 of 439** statements, with 1 false match: in practice the alignment layer
was switched off. Refitting alone took that to 13 answered / 10 correct with
**zero** false matches; refitting *and* fixing the margin statistic (below)
takes it to `0.2347 / 0.2722`, **17 answered / 12 correct, still zero false
matches**. On PFR the same shift takes the answer rate from 1.7% to 5.7% at
unchanged r@1, with the absent arm still at **0 false matches**.

**Verifier `balanced`.** Tested by asking, for each profile, whether any
threshold accepts strictly more correct proposals at no worse false-accept
rate on *every* negative population. `precise` and `permissive` are still on
that frontier and were left alone — the best alternative to `permissive`
gained one statement out of 439, which is noise, and adopting it would have
been fitting sampling error. `balanced` was genuinely dominated and moved to
`0.0451 / 0.9268`: **26.2%** of correct proposals accepted instead of 23.5%,
at an identical rate on the hardest negative and a better one on
wrong-namespace proposals.

### The margin was measured against the wrong thing

Abstention rests on two statistics, and the second one was malformed:

```python
margin = (scores[0] - scores[1]) / scores[0]      # rank 1 vs rank 2
```

Two failures, one of them severe:

1. **It cannot count.** One close rival and nine close rivals are very
   different amounts of evidence and produce an identical value.
2. **A single near-duplicate destroys it.** mathlib is full of primed variants
   (`foo` / `foo'`) and `@[to_additive]` twins that score identically. Any one
   of them pins the statistic at ~0 and forces a spurious `ambiguous` — the
   tool refusing to answer because it found the same fact twice. The very
   first query in this README returns `Metric.closedBall_subset_ball` and
   `Metric.closedBall_subset_ball'` adjacent, tied at 0.8995.

Replaced by separation from the *mean of the tail* rather than from rank 2:

```python
margin = (scores[0] - mean(scores[1:10])) / scores[0]
```

which fixes both at once and, importantly, fixes (2) **without** an
equivalence relation over names: a lone duplicate is one of nine competitors,
so it moves the mean by about a ninth instead of collapsing the statistic. On
a `[1.0, 1.0, 0.1×8]` score vector the old margin reads 0.0 and the new one
reads 0.80; on a genuine nine-way tie the new one reads 0.0, which is the
correct refusal — the statistic rescues a lone duplicate, not a real tie.

Collapsing duplicates explicitly was measured as an alternative and is
**not** worth it: an apostrophe-strip rescues 9 correct retrievals but is
worth nothing at the zero-false-match operating point, and collapsing
`to_additive` twins is actively harmful — it lifted the margin on 8
statements, of which **zero** had a correct top-1, because multiplicative and
additive twins are genuinely different facts.

The tail-mean statistic beats rank-1-vs-2 at every false-match budget from 0%
to 10%, in-sample and under split-half threshold selection (96% of splits at
the ≤2% budget). Honest caveat: **at the zero-false-match point the corpus
cannot separate them** — 12 correct answers versus 10 is inside the noise
floor, and the justification for the change is the whole-frontier dominance,
not that one point.

`delta_margin` does not transfer between the two definitions, and the failure
is not graceful: running the old `0.08` threshold against the new statistic
produces **3 false matches** on the PFR absent arm, breaking the 100%
abstention claim. Refitted, it is back to zero.

**Reranker `lam`/`gate`: deliberately not refitted.** The blueprint corpus
cannot separate them — r@1/r@5/r@10 is flat at 38.3/55.3/61.7 across `lam`
from 0.3 to 2.0 and `gate` from 0.0 to 0.7, because the gate switches the
term off on almost every non-PFR project. Anything that looks best there is
noise, and the values that look best on PFR are exactly the ones this
protocol forbids reading. `lam=0.9` stands.

Two consistency fixes rather than retunings. `bench` was passing `gate=0.5`
while `query` used the declared default of 0.45, so the shipped benchmark was
measuring a configuration the shipped code never ran. And `TreeReranker`
defaulted to 0.5 while `StructReranker` used 0.45, so the two rerankers
disagreed on the same constant for no stated reason. Everything now uses 0.45. The tree row is unaffected either way: 21.1 / 33.1 / 40.6 at both
gate values, which is its own small evidence that this gate is not where the
signal lives.

### The elaborated corpus cannot be evaluated on paper text

`bench` runs against `idx_full`, which is regex-scraped, so `idx_elaborated` —
the 464,208-declaration corpus the whole elaborated path was built for — had
never been measured on paper prose. Attempting it establishes that it cannot
be, which is worth more than the attempt.

`idx_elaborated` is mathlib-only, and blueprint `\lean{}` annotations almost
always name the *project's own* declarations rather than mathlib's. Of 618
paper statements (439 blueprint pairs + 179 PFR blocks), the number whose gold
answer exists in a mathlib-only corpus is **6**. Every recall figure over that
set moves in steps of 17 percentage points. There is no measurement here, and
reporting one would be dishonest. Evaluating the elaborated path on paper text
requires elaborating the blueprint projects too, which means building each of
them — hours and roughly 15 GB apiece.

So the claim that elaborated types help on the real task remains **unproven,
and is not currently provable with these corpora.** The ranking gains reported
for the third field were measured on scraped indices, and they stand; they are
simply not evidence about this corpus.

Two things did come out of looking.

**It is not "mathlib with better types".** `mathgraph elaborate` runs
`import Mathlib` and dumps the environment, which is a much larger and
different thing than Mathlib:

| | declarations |
|---|---|
| Mathlib | 339,368 |
| Lean core + Init + Std | 114,954 |
| Aesop, Batteries, ProofWidgets, Qq, … | 9,886 |

27% of the corpus is not Mathlib at all, and **8.1% (37,416) is compiler
boilerplate** — 14,653 `noConfusion`, 7,161 `.rec`, 5,758 `.mk.inj`, 5,672
`sizeOf_spec` — which are not mathematical statements in any sense. This is
the likeliest explanation for the elaborated corpus underperforming its
promise, and it is fixable by filtering rather than by tuning.

**It breaks the zero-false-match claim.** At `GRAPH_THRESHOLDS`, `idx_mathlib`
produces 0 false matches on the 612-statement absent arm and `idx_elaborated`
produces 1 — a con-nf statement that reduces to almost nothing after math
stripping (`"( ( ^ -1 )^ = ( ^ )^ -1 ), and ( ^ ) is permutative"`) matching
`Array.permute!`, a **Lean core** declaration reachable only because the
corpus contains far more than Mathlib. The thresholds were fitted on
source-scanned indices and do not transfer to this one.

For the record, the documented compact-Hausdorff behaviour reproduces on
`idx_mathlib` exactly as written — rank 3 for "a compact subset of a Hausdorff
space is closed" — but on `idx_elaborated` the same query gives rank **4**,
not the rank 3 the README claimed. Several natural rephrasings reach rank 1 on
both, which is a fair reminder of how little one query establishes.

### Auditing the third field: two fixes, one load-bearing accident

Adding a third index field put three things in the scoring path worth checking.
All three were measured; only two were wrong, and the interesting result is the
one that was not.

**`coverage` was not a fraction.** `_score` accumulated the denominator
`mass` only for query tokens with *name* postings, while module and type
postings still contributed to the numerator. So a token living solely in the
type field — exactly what the third field was added to serve — inflated
`coverage` without bounding it. This is reachable, not theoretical: the
two-token query `{equiv, bg}` scored **coverage 2.315** on
`Equiv.equivCongr_refl_left`. `coverage` is the abstention statistic — the
thing `tau_cov` is compared against, at the time 0.2474 — so the fitted
threshold was reading a quantity that is not a fraction. Fixed by charging each token the largest field weight it can
actually earn, which restores `mass` as an upper bound on `raw`.

The honest part: at the shipped `typ_weight=0.15` this changed **nothing
measurable**. Zero verdict flips across all 618 paper queries (439 blueprint
pairs + 179 PFR blocks), mean inflation 0.0009, and the abstention operating
point is identical before and after — 14 answered / 9 correct / **0 false
matches** of 439, refitting to the same thresholds either way. It only starts
moving verdicts around `typ_weight ≳ 1.0`, and at 2.0 it moves 143 of them and
real queries reach coverage 1.34. It was a latent defect whose severity scales
with a tunable constant, and the sweep above ran that constant to 1.0. Ranking
was never affected — order comes from `raw/lennorm`, which never touches
`mass`.

**`to_additive` twins had no type field at all.** `expand_to_additive` sets
`head = ""`, so all **10,875** generated declarations in `idx_full` carried
zero type tokens against 99.9% of source declarations — the third field was
structurally unable to fire for any additive lemma, in a tool benchmarked on
additive combinatorics. The type is recoverable without inventing source text:
it is the original's with the multiplicative structures renamed, applied at
token granularity through mathlib's own naming dictionary
(`names.additive_tokens`), leaving `head` honestly empty so provenance stays
truthful.

| | BP r@1/r@5 | PFR r@1/r@5 | PFR +structural |
|---|---|---|---|
| empty type field (shipped) | 21.0 / 30.3 | 18.9 / 32.0 | 20.0 / 38.9 |
| twins get type tokens | **21.2 / 30.5** | 18.9 / 32.0 | **20.6** / 38.9 |

Eight numbers, none worse, four better — but every delta is about **one
statement**, which is inside the noise floor this repository has already
established for these corpora. The case for it is that it removes a structural
asymmetry, not that it improves the benchmark, and it needed no threshold
refitted. It takes effect only on rebuild; existing indices are unaffected,
which is why `bench` is unchanged.

**`max_df` is bypassed, and closing it makes things worse.** `query_weights`
admits a token if it appears in *any* field, so 27 tokens whose name document
frequency far exceeds `max_df` (7,278) are readmitted through the module or
type index — and `_score` then adds their full name postings at full weight.
These are precisely the population the filter exists to exclude: `of`
(name_df 40,069), `theory` (37,581), `is` (33,041), `set` (12,771). Several
were newly readmitted by the type field.

Gating each field on its own document frequency — what a per-field frequency
filter should mean — costs real accuracy:

| | PFR r@1/r@5 | PFR +structural |
|---|---|---|
| shipped (wholesale bypass) | **18.9 / 32.0** | **20.0 / 38.9** |
| `max_df` per field | 17.1 / 30.3 | 20.0 / 35.4 |

So this is a **load-bearing accident, not a bug**, and it is left alone. The
reason it helps is that `add`, `mul`, `le`, `eq`, `set` and `is` are core
mathlib vocabulary rather than stopwords; a flat 3%-of-corpus cutoff is simply
miscalibrated for the name field, and the bypass has been silently
compensating. The honest description of the shipped behaviour is that `max_df`
applies only to tokens absent from the module and type indices. Worth
revisiting deliberately, as a `max_df` question rather than a gating one.

One more thing the audit turned up and did not fix: `type_tokens` truncates at
`":="`, which is essential on regex-scraped heads (86% contain one, and the
rest of the string is a definition body) but wrong on elaborated types, where
**5.5%** contain a `":="` inside the type itself and lose every token after it.

### Refitting against a validated corpus

Wiring the `to_additive` ground truth in left `GRAPH_THRESHOLDS` fitted
against a corpus the index builder no longer produces, and that was recorded
as the open item. Closing it turned up something worse than drift.

The old pair answers 14 of 439 with 9 correct and no false match on the
unvalidated corpus it was fitted on. On the validated corpus, at the same
thresholds, **three** statements from `equational_theories` — `387_implies_43`
and two like it — are answered against a mathlib-only index that does not
contain their declarations. Their coverage is 0.24743. `tau_cov` was 0.2474.

That is the whole story: the fit had placed the threshold **0.0002** above the
highest negative it had to exclude, and dropping 3,012 invented `to_additive`
names moved the IDF enough to push three statements across it. The zero-
false-match property was not robust to a corpus change; it was resting on the
fourth decimal place.

Refitting on the validated corpus gives `0.2525/0.2648` — 16 answered, 11
correct, no false match. But **both** corpus states ship: `setup` validates the
reconstruction only when `elaborate` has been run, and the laptop path has no
Lean toolchain, so a threshold that is clean on one and not the other is not
usable. `0.2525/0.2648` admits one false match on the unvalidated corpus.

The shipped pair is fitted against the negative arms of both at once:

| thresholds | validated corpus | unvalidated corpus |
|---|---|---|
| `0.2474/0.2671` (old) | 16 answered / 11 correct / **3 false** | 14 / 9 / 0 false |
| `0.2525/0.2648` (validated only) | 16 / 11 / 0 false | 14 / 9 / **1 false** |
| `0.2525/0.2649` (joint, at the time) | 16 / 11 / 0 false | 14 / 9 / 0 false |

One ten-thousandth of `delta_margin` separates the last two rows, which is a
fair description of how much slack this operating point has ever had. The PFR
absent arm is unaffected — 0 false matches on all three pairs, on both corpora.

Two things that should have caught this earlier are now in place. The fit is
code rather than a procedure described in prose and run by hand —

```
python -m mathgraph.evaluate graph <validated-artifacts> <unvalidated-artifacts>
```

which takes positives from the first corpus and negatives from every corpus
given, and reproduces the shipped pair exactly. It reports its counts at the
rounded 4-dp literal that actually ships rather than at the
unrepresentable optimum near it — rounding a margin floor down re-admits the
negative that set it. And the 439-pair negative arm now has a test. Only the
PFR arm did, which is exactly why a pair that held on PFR and failed here
could sit in `cli.py` unnoticed.

### The index that reported itself fresh

The corpus above was found unvalidated for a reason worth writing down.
`setup` skips any stage whose output already exists — that is what makes the
bootstrap resumable — so running `elaborate` afterwards rebuilt nothing, and
`setup` then reported success over a corpus whose `to_additive` names had
never been checked against anything.

The obvious fix is to treat an index older than the elaborated dump as stale.
It does not work, and shipping it would have been worse than the bug: **the
indices in question are newer than the dump they were never validated
against.** The dump landed on 28 Jul and the indices on 28 Jul nine minutes
later; the code that consults the dump landed on 2 Aug. What went stale was
the builder, not the ground truth, and no file time can see that.

What can see it is the index. `build` already computed `ground_truth_decls` —
0 when it ran without an elaborated environment — and buried it in the pickle,
where reading it costs a 4s deserialisation of 240k rows. It is now also
written to `meta.json` beside the index, which makes the check a small read,
and makes the provenance histogram legible without loading anything:

```json
{ "provenance": { "source": 230742,
                  "to_additive:inferred:validated": 6986,
                  "to_additive:explicit:validated": 1162 },
  "ground_truth_decls": 464208,
  "index_version": 2 }
```

So `setup` rebuilds an index whose `ground_truth_decls` does not match the
environment in hand — missing (built before the field existed), 0 (built
without one), or a different number (elaborated against a different mathlib).
An index with no ground truth in hand is never rebuilt, because the laptop
path has nothing to be stale against. Re-running `setup` on a current corpus
is still a 2s no-op.

`index_version` covers the case ground truth cannot, and the very next commit
needed it: fixing the explicit-name rule changed what a rebuild produces
without changing the environment it is checked against, so every existing
index was current by every test above and wrong anyway. The stamp is a
constant in `index.py` bumped when the builder's output changes — the same
staleness question asked about the code instead of the data.

### The library benchmark

`evaluate.py` runs the docstring version with a proper negative arm:
declarations removed from the index entirely, whose only correct answer is
abstention. Three-way split — training docstrings, positive probes withheld
from PMI training, and removed negatives — so nothing is scored against text
it trained on.

| metric | value | before the length-normalisation fix |
|---|---|---|
| recall@1 | **9.1%** | 5.8% |
| recall@5 | **22.1%** | 14.8% |
| MRR | **0.139** | 0.089 |
| max precision at any threshold (≥5 answers) | **14.6%** | — |

Ranking columns are a fresh 2%/2% holdout re-measured old-scorer-vs-new on one
index, so they read slightly below the 6.3%/16.0% originally published here
(different holdout draw and mathlib snapshot); the comparison between the two
columns is the like-for-like one. The precision row has **not** been
re-measured since the fix.

It does **not** calibrate either, and it is worse than the paper benchmark on
precision. Whatever is wrong is wrong with the scoring function, not with the
PFR text being unusually hard. Two independent benchmarks agreeing on that is
more informative than either alone — and they agreed again on the fix: the
same change moved both by roughly the same factor.

### What does work, exactly

Run over the whole 406-block PFR blueprint against mathlib alone:

```
nodes 406 · claims 218 · proofs 188
internal edges 746 · dangling refs 30
alignment: 183 unmatched · 12 ambiguous · 0 matched · 23 not attempted
```

The internal graph is exact. The alignment correctly reports that essentially
none of this paper is in mathlib — which is true, and is the honest shape of
the paper-to-library gap for current research mathematics.

---

---

## The dense retriever, and what it proved

`dense.py` is a dual encoder trained from scratch on the ~69,000
docstring/declaration pairs — no pretrained weights (they would not help; the
vocabulary that matters is `tendsto`, `bdd`, `symm`, and a general-purpose
sentence encoder never saw it). Both sides are bag-of-token linear encoders
projected to a shared 192-dim space, trained with InfoNCE over in-batch
negatives. It is a low-rank factorisation of the same English→token
association matrix the PMI table approximates sparsely, learned end-to-end and
without the top-12 truncation.

It converges cleanly: in-batch top-1 reaches 96.8%. Then, scored on the same
two arms:

> **Stale numbers.** Every dense/hybrid figure in this section and the next
> was measured before the length-normalisation fix, and the `lexical` rows
> are that scorer's old numbers (7.4% / 20.0% on PFR, now 17.7% / 29.1%).
> Retraining was out of scope for that fix. The qualitative finding — dense
> beats lexical in-distribution and collapses on paper prose — is unaffected
> in direction, but the *margin* against lexical is now smaller than shown,
> and on PFR lexical's lead over every dense variant is larger.

| retriever | docstrings r@1 | docstrings r@5 | PFR paper r@1 | PFR paper r@5 |
|---|---|---|---|---|
| lexical | 6.3% | 16.0% | **7.4%** | **20.0%** |
| dense | **17.4%** | **41.7%** | 0.6% | 3.4% |
| hybrid (RRF) | — | — | 5.1% | 13.1% |

Both docstring figures are full-corpus retrieval over 234,531 declarations
with the probe docstrings withheld from training.

**Dense is 2.8× better than lexical in-distribution and collapses to near-zero
on paper prose.** That is the single most useful thing this project produced.
The retrieval problem is not intractable — 41.7% recall@5 against 234k
candidates is a strong signal. The blocker is that the only large parallel
corpus available (library docstrings) is the wrong distribution: docstrings
are short, use library vocabulary, and describe the declaration's own
concepts. Paper statements are formula-dense with generic connective English —
median 13 English words against 4 formula blocks.

The lexical matcher, being distribution-free, degrades far less; it is the
only one of the three that does *better* on papers than on docstrings. Rank
fusion does not rescue the hybrid, because RRF weights a near-random list
equally with a useful one.

---

## Domain adaptation: the corpus hypothesis, tested

The dense/lexical split above says the blocker is a distribution mismatch, not
model capacity. That is a testable claim, so it was tested.

`harvest.py` crawls public `leanblueprint` projects — ordinary mathematical
prose carrying author-written `\lean{...}` annotations, which is exactly
(paper statement, declaration) supervision in the target distribution. Every
such project that could be found and cloned yielded:

| project | pairs | declarations |
|---|---|---|
| lean4-ergodic-theory | 632 | 4,431 |
| carleson | 164 | 2,819 |
| FLT | 122 | 3,044 |
| equational_theories | 77 | 14,338 |
| con-nf | 53 | 3,795 |
| LeanAPAP | 23 | 522 |
| **total** | **1,071** | **38,897** |

PFR is excluded throughout — both its blueprint pairs and the docstrings on
its own Lean declarations. It stays the test set.

`adapt.py` pretrains on docstrings, then continues on a mixture of upsampled
blueprint pairs and docstrings. Straight fine-tuning on 1k pairs collapses the
space; the mixture keeps the library vocabulary while pulling the query side
toward paper prose.

### Results, all on the same PFR arms

| retriever | r@1 | r@5 |
|---|---|---|
| **lexical** | **7.4%** | **20.0%** |
| dense, docstrings only | 0.6% | 3.4% |
| dense, + 1,071 blueprint pairs | **3.4%** | 4.6% |
| dense, + blueprint + augmentation | 1.7% | 4.6% |
| hybrid, best variant | 6.3% | 12.6% |

Real paper pairs move dense recall@1 by **5.7×** (0.6% → 3.4%). The direction
of the hypothesis is confirmed: paper-distribution supervision is what the
encoder was missing.

Synthetic augmentation does not work. Randomly dropping words from docstrings
to match the measured 13-words-plus-formulas shape *hurt* r@1 relative to real
pairs, on 65× more data. So the gap is not "papers say less" — it is which
words survive and what vocabulary they are drawn from, and that cannot be
faked from library text.

And 1,071 pairs is roughly **30× too few**. Nothing here beats the plain
lexical matcher on paper text. That is the state of the art this repository
reaches, stated plainly.

## Where to take it next

The binding constraint is now precisely located: **~1,500 author-annotated
paper-prose/declaration pairs is the total freely available supervision in
this distribution today**, across every public blueprint project. Not model
size, not architecture, not the abstention layer.

Three routes, in order of expected value:

1. Mine arXiv papers whose results were later formalized, pairing statements
   to declarations through the formalization's own commit history and
   docstrings. Orders of magnitude more pairs, noisier.
2. Grow with the ecosystem — blueprint projects are being written continuously
   and each one is free labelled data in exactly the right distribution.
3. Statement-level structure rather than bag-of-words — **now built, and it
   is the first thing in this repository that beats the lexical baseline on
   paper text.** See "Structural matching" below.

---

## Structural matching (`structmatch.py`)

The route here went through two measured failures. Bag-of-symbols
(`mathsym.py`): direct `\leq`→`le` mapping moved recall@1 from 7.4% to 8.0%
(pre-fix scorer, not re-measured), marginal either way; a learned symbol→token
PMI table drowned in project-vocabulary
contamination. The conclusion those forced: the formulas' value is in *what
relates what*, not which symbols appear.

The working version rests on one observation: **formalizations carry the
paper's own notation.** The PFR blueprint writes `d[X;Y] \leq \bbH[X+Y]`;
the Lean statement head reads `d[X ; μ # Y ; μ] ≤ H[X + Y]`. Relation symbol,
bracket-application heads, and operator shape survive translation nearly
verbatim — and none of them survive being flattened to `MATH`, which is what
every earlier stage did. So both sides are reduced to a skeleton (relations,
operators, application heads, relation|head bigrams) and skeleton overlap
reranks the lexical top-K — reranking, because at the time this was built the
measured bottleneck looked like ranking, not retrieval. Current numbers (see
["Why"](#why) above) put the pre-rerank pool's reach at 83.5%, not the 97%
originally measured, so that motivation is now only partly true — but
reranking still measurably helps (recall@5 31.8%→38.1%), so the design stands
on its current results, not the stale ones that motivated it.

Three design decisions, each forced by an off-PFR measurement:

- **Corpus-set weights, not hand-set.** Hand weights helped on PFR and hurt
  on the blueprint validation set: `rel:le` appears in a third of all
  statement heads and matched everything. Structural features are
  IDF-weighted from the corpus itself.
- **Only rare features score.** Per-project diagnosis showed application
  heads and bigrams carried the signal while bare relations and operators
  carried the noise; relations now act only through a contradiction penalty
  (claiming `≤` against a head that states only `=` counts against).
- **Per-query gating.** Structure means something only where the
  formalization preserved notation — measured directly: it helped exactly
  the notation-heavy projects (carleson +5pts) and hurt the rest. Whether
  notation survived is visible from the query's own candidate list; if no
  candidate matches the skeleton well, the term switches off.

Hyperparameters chosen on the blueprint corpus, PFR untouched until the final
transfer:

| PFR present arm (n=175, pre-scanner-fix corpus) | r@1 | r@5 | r@10 |
|---|---|---|---|
| lexical baseline | 18.9% | 32.0% | — |
| + structural reranking | **20.0%** | **38.9%** | — |

+16% / +26% / +24% relative, with the blueprint validation set unchanged
(the gate keeps the term out where it has nothing to say). On the current
corpus (n=176, ~11k more declarations) the same two rows are 18.2 / 31.8 and
**19.3 / 38.1** — the gap the reranker buys is what this table is about, and
it survives the corpus change at 1.1 / 6.3 points.

These are post-fix numbers. Against the pre-fix baseline the same term gave
8.0%→10.9% / 20.0%→28.0% / 25.7%→33.7%, a larger *relative* lift — fixing the
length normalisation absorbed part of what structural reranking was previously
recovering, which is what you would expect if both were correcting the same
long-name bias. The term still pays on top of the fix, and the ordering of the
conclusions below is unchanged. The PFR-tuned oracle bound (15.4% / 25.1%
pre-fix) has not been re-measured.

### One level deeper: side-aware trees (`treematch.py`)

The skeleton knows `≤` and `H[` co-occur. The tree stage additionally knows
*where*: `H[·]` left of the relation, `log` right of it, `+` inside the
entropy's argument — extracted by bracket-depth scanning on both sides, no
grammar. The sanity check is exact: the LaTeX and Lean renderings of the same
statement produce identical feature sets, and the converse statement produces
different side-tags, which is precisely what distinguishes
`entropy_le_log_card` from its reverse.

The same discipline forced the same correction a second time: side-tagged
bare operators (`L:op:add`) proved as noisy off-PFR as untagged ones had in
the skeleton stage, and were cut from scoring. After that, blueprint
validation is exactly neutral and the PFR transfer gives a Pareto frontier
rather than a single winner:

| PFR present arm | r@1 | r@5 | r@10 |
|---|---|---|---|
| lexical baseline | 18.9% | 32.0% | — |
| + skeleton | 20.6% | **36.6%** | **41.1%** |
| + tree | **21.1%** | 33.1% | 40.6% |
| + both | not re-measured since the fix (was **13.1%** / 24.6% / 30.9%) | | |

The frontier survived the length-normalisation fix in the same shape: tree
still buys r@1 and gives up r@5 relative to the skeleton.
Tree features are more precise and sparser: they name the right declaration
more often but reach fewer statements. Which column matters depends on the
consumer — the verification layer wants r@1 (and the tree/combo term slots
into its evidence function directly), a human-review candidate list wants
r@5, and both configurations ship.

### Argument identity (`argmatch.py`)

The deepest textual rung: alpha-canonical argument patterns. In
`d[X;Y] ≤ H[X+Y]` the arguments of `d` reappear summed inside `H`, and that
sharing is invariant under renaming — variables are canonicalised by first
appearance and the formula collapses to `pat:le(d[v0,v1]|h[v0+v1])`, emitted
identically from LaTeX and from Lean heads by tokenizers that agree on the
canonical form. Two findings and one relocation:

- **Formulas live in hypotheses.** Most gold formulas sit inside binders —
  `(hdist : d[X # X] = 0)` — which a conclusion-only reading misses entirely.
  Hypothesis bodies are scanned too.
- **Patterns are too sparse to rerank** (recall aggregates unmoved) —
  and that is the predicted profile, so they were relocated to where sparse-
  but-conclusive is the right shape: the verifier. Reproduce with
  `uv run mathgraph verify-bench --patterns`, which builds the same 176
  present-arm gold pairs as the table below but also passes each statement's
  LaTeX formulas as `math_segments`, so `Verifier.verify`'s pattern-accept
  path actually fires (added under mathgraph-g8x — before it, no checked-in
  command exercised that path at all: `verify.evaluate`'s gold pairs never
  carried `math_segments`). Measured fire rate on the current 176-statement
  present arm: 8.5% on correct proposals vs 2.3% on sibling lemmas and 0.0%
  on wrong-namespace, hallucinated, and random ones — a **~3.7:1** likelihood
  ratio against the hardest corruption, not the ~14:1 the previous,
  unreproducible version of this paragraph reported (8.6%/0.6%/0.0%, dated
  before the 175→176 corpus move and never re-verified against it — see
  mathgraph-g8x).

Wired in as an independent accept path (a firing pattern verifies on its
own, bypassing the profile's evidence thresholds), the permissive profile's
operating point moves from accepting 35.8% of correct proposals to
**42.6%** (precise: 8.5% → 16.5%). This is not free: the sibling
population's false-accept rate rises alongside it, permissive 9.7% →
**11.9%** and precise 1.1% → **3.4%** — the same sparse pattern feature that
fires on a correct proposal's formula also fires, less often, on a sibling
lemma from the same module. Every other corrupted population
(wrong-namespace, hallucinated, random) is unchanged at 0.0%. (The previous
version of this paragraph reported 34.9% → 41.7% "with every corrupted
population unchanged" and called it "free recall at held precision"; that
was unreproducible before mathgraph-g8x, and the "unchanged" claim does not
hold even on today's numbers — sibling moves. Reproduce with the same
`verify-bench --patterns` command above.)

Genuinely elaborated Lean ASTs (typeclass-resolved, notation-expanded) remain
the rung above. The path is now built — `lean/DumpDecls.lean` dumps them from
a built mathlib, `leanast.py` ingests them into the same `head` text shape
the matchers already read, so all three consume the better input with no code
changes. The Python ingest is tested against synthetic elaborated input; the
Lean dumper is written but **unrun**, since the development environment had
no toolchain. It is opt-in (`mathgraph elaborate`) and nothing else depends
on it. The ladder so
far — symbols failed, skeletons +40%, sides +precision, argument patterns
+7pts of verification recall at a real but smaller sibling-false-accept
cost — says each level of structure pays, and says where each level
belongs.

## The verification layer

`verify.py` inverts the problem. A strong LLM proposes a declaration name for
an informal statement; this layer decides whether to trust it. Generation is
what LLMs are good at; knowing when they are wrong is what they are bad at —
a hallucinated alignment is fluent and confident. The checks here are the
opposite shape: exact where possible, calibrated where not.

Three verdicts: **nonexistent** (name not in the index, including the
`to_additive` shadow — exact), **rejected** (exists, but the statement's words
do not support it), **verified**. Thresholds are calibrated on the non-PFR
blueprint corpus and transferred to PFR untouched.

Evaluated by corrupting gold proposals the ways proposers actually fail
(176 PFR present-arm statements × 5 proposal populations). Reproduce with
`uv run mathgraph verify-bench` — this driver did not exist before
mathgraph-2zj; `verify.evaluate`, which it wraps, had no caller anywhere in
the repository and this table was not reproducible from any checked-in
command:

| proposal population | accept rate (permissive) | accept rate (precise) |
|---|---|---|
| correct | **35.8%** | 8.5% |
| sibling lemma, same module | 9.7% | 1.1% |
| same name, wrong namespace (n=21, not 176 — see below) | 38.1% | 0.0% |
| hallucinated name | **0.0%** (100% caught as nonexistent) | 0.0% |
| random declaration | 0.0% | 0.0% |

This replaces a previously reported 175-statement table (34.9%/6.3%,
10.3%/1.1%, 33.3%/0.0%, 0.0%/0.0%, 0.6%/0.0%) that predates the present
arm's move from 175 to 176 statements (see above) and predates
`verify-bench` — no script in this repository reproduced it, so this is a
genuine re-measurement, not a rounding fix, and not every row moved the same
direction. **The wrong-namespace row is measured on 21 of the 176
statements, not all 176**: `corrupt()`'s wrong-namespace mode needs another
declaration in the index sharing the gold's last name component, and only 21
of the 176 gold names have one, so that row carries far less statistical
weight than the other four.

The existence check alone is worth deploying: every fabricated name is caught,
exactly, at zero false-alarm cost — and fabricated names are the dominant LLM
failure mode this layer exists for. The evidence check on top enriches a
mixed proposal stream (e.g. 50% correct → ~76% correct among accepted). The
weak spot is same-tail wrong-namespace proposals, which are lexically
identical to the gold; a namespace-aware feature is the obvious next fix.

The table above is the pre-fix measurement. The length-normalisation fix moves
the verifier's thresholds without invalidating them — re-run on the 439-pair
blueprint corpus, all three shipped profiles got strictly better on **both**
arms at once, so no recalibration was required:

| profile | accepts correct | falsely accepts top *wrong* candidate | falsely accepts a random declaration |
|---|---|---|---|
| precise | 12.8% → **18.0%** | 28.2% → **18.7%** | 0.0% → 0.0% |
| balanced | 17.1% → **26.2%** | 39.9% → **33.1%** | 0.0% → 0.0% |
| permissive | 33.5% → **40.1%** | 77.9% → **68.6%** | 0.7% → **0.0%** |

The hard negative here is the top lexical candidate that is *not* the gold —
a stronger adversary than the corruption populations above, which is why the
absolute rates are higher. `precise` and `permissive` are the original
constants, which survived the scoring change on the frontier; `balanced` is
refitted. See [Recalibration after the
fix](#recalibration-after-the-fix).

### Re-checked against the validated corpus

These profiles were fitted on the same unvalidated corpus that put three false
matches into `GRAPH_THRESHOLDS`, so they were re-measured after the rebuild
(`python -m mathgraph.evaluate verify <artifacts>`):

| profile | accepts correct | top *wrong* candidate | random |
|---|---|---|---|
| precise | 18.0 → **18.7%** | 18.7 → **17.5%** | 0.0 → 0.0% |
| balanced | 26.2 → **26.9%** | 33.1 → **28.2%** | 0.0 → 0.0% |
| permissive | 40.1 → **41.0%** | 68.6 → **64.9%** | 0.0 → **0.2%** |

Every profile moved better on both arms at once — more correct accepted, fewer
hard negatives — which is what dropping ~3,000 names that do not exist should
do to a layer whose first check is existence. The one regression is a single
random proposal of 439 accepted by `permissive`. No profile needed moving.

Searching for one anyway is where this gets interesting. Sweep every observed
(`tau_abs`, `tau_rel`) and the criterion in this repo — accepts strictly more
correct at no worse rate on *every* negative population — is met by 227
alternatives to `precise`, 52 to `balanced`, and 70 to `permissive`, the best
of them worth +7, +3 and +3 statements. Taking any of them would be a mistake.
Selecting the maximum of ~100k grid points against 439 statements finds a gain
whether or not one exists, so the sweep was redone fitted on three blueprint
projects and scored on the two held out (`LeanAPAP`, `con-nf`):

| profile | held-out correct | held-out hard negative |
|---|---|---|
| precise | 9.2% → 13.2% | 14.5% → **19.7%** |
| balanced | 18.4% → 18.4% | 32.9% → **34.2%** |
| permissive | 38.2% → 42.1% | 59.2% → **69.7%** |

Not one of them still dominates. `balanced` buys nothing at all and costs on
the negative arm; the other two buy three statements each and pay five and ten
points of false accepts for them. The dominance was in-fold only. This is the
same instinct that declined to move `permissive` for a one-statement gain
earlier — now with the held-out arm that shows it was right.

## The shipped benchmark

`bench_release/` is not checked into this repo — it's produced on demand by
running `python -m mathgraph.freeze_bench`, which writes a standalone
`tasks.jsonl` (one row per statement, each naming its reference corpus), a
stdlib-only `scorer.py`, and a data card, so the benchmark can be used without
cloning anything. Predictions are one JSON line per task, `null` meaning
abstain; the scorer reports precision, recall, and the absent-arm false-match
rate side by side so no system can hide behind any one number. Derived from
the PFR blueprint (Apache 2.0); inherits Apache 2.0.

Row counts depend on the corpus the generator is run against, and are not
reproduced here: the present arm has already drifted from 175 to **176**
statements elsewhere in this document (see above), and `freeze_bench.py`'s
data card is a static template whose text does not recompute from the corpus
it's actually run on — its stated counts and baseline numbers can go stale
independently of `tasks.jsonl`. Treat any counts printed inside a generated
`bench_release/README.md` as unverified until that template interpolates its
real numbers; check them against `tasks.jsonl` directly.

The calibrated abstention layer is model-agnostic and unchanged throughout.
Any replacement retrieval stage drops into `bench_dense.py` and is scored on
the same two arms against the same author-written ground truth — a real test
rather than a demo.

Index scale, measured directly against `idx_full` (`len(art['rows'])`,
`len(art['postings'])`, and 50 timed `Aligner.align` calls) as of 2026-08-08:
**251,236** declarations, **5,399** name tokens. These move with mathlib and
are not frozen; re-run the measurement rather than trusting this line. Per-
query latency is hardware- and container-dependent and not a reproducible
figure across environments, so it is omitted here rather than reported as a
false constant.
