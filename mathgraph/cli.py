"""mathgraph command line.

    mathgraph setup                     fetch corpora, build indices (once)
    mathgraph query   "<statement>"     rank candidate declarations
    mathgraph verify  "<statement>" <Decl.name>
                                        audit a proposed alignment
    mathgraph graph   paper/*.tex       extract the paper's dependency graph
    mathgraph bench                     reproduce the PFR benchmark
    mathgraph elaborate                 [optional] use real Lean types

All commands take --data-dir (default ./mathgraph-data, or $MATHGRAPH_DATA).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

DEFAULT_DATA = os.environ.get("MATHGRAPH_DATA", "./mathgraph-data")

# Retrieval parameters fitted on the blueprint validation corpus, with PFR
# held out. See README "Structural matching" for the derivation.
# typ_weight is deliberately small. Swept on the blueprint corpus with PFR
# held out, r@1 peaks at 0.15 and falls off hard above it; the single query
# that motivated the whole elaborated-types path wants 0.5, which is exactly
# where PFR r@1 collapses from 18.9% to 13.1%. Fitting to that one query
# would have cost a fifth of the benchmark.
LEX = dict(len_pivot=0.75, mod_weight=0.1, typ_weight=0.15,
           prefix_weight=0.85, title_boost=2.5)
# Abstention thresholds for `graph`, fitted on the 439 non-PFR blueprint pairs
# against a genuine negative arm (the same statements against a mathlib-only
# index, where their answer does not exist), by exhaustive search over every
# observed coverage and margin value at the zero-false-match constraint.
# Reproduce with `python -m mathgraph.evaluate graph <validated> <unvalidated>`
# (positives from the first, negatives from both).
# delta_margin is not comparable across margin definitions -- 0.2658 here is
# against the tail-mean separation statistic, not the old rank-1-vs-2 one.
# The constraint is held on the negative arms of *both* corpus states, because
# both are shipped: `setup` validates the to_additive reconstruction only when
# `elaborate` has been run, and the laptop path has no toolchain. The previous
# pair was fitted on the unvalidated one alone and did not survive the other --
# see README "Refitting against a validated corpus".
# History: 0.35/0.08 answered 1 of 439 with 1 false match; rank-1-vs-2
# refitted answered 13 with 10 correct and none false; 0.2474/0.2671 answered
# 14 with 9 correct and none false on an unvalidated corpus but 16 with 11 and
# *three* false on a validated one; 0.2525/0.2649 and then 0.2525/0.2650 each
# survived one corpus change and not the next. Every move has been forced by
# the corpus growing or shrinking under it, never by a scorer change -- this
# operating point is genuinely narrow and the arms are what detect it. This
# answers 16 with 11 correct on the validated corpus and 14 with 9 on the
# unvalidated one, with no false match on either, nor on the PFR absent arm.
GRAPH_THRESHOLDS = dict(tau_cov=0.2526, delta_margin=0.2658)
# Verifier thresholds calibrated on non-PFR blueprint projects.
# Re-checked after the length-normalisation fix by asking, for each profile,
# whether any threshold accepts strictly more correct proposals at no worse
# false-accept rate on *every* negative population. `precise` and
# `permissive` are still on that frontier and are left untouched; `balanced`
# was dominated -- the entry below accepts 26.2% of correct proposals instead
# of 23.5% at an identical rate on the hardest negative.
VERIFY_PROFILES = {
    "precise": dict(tau_abs=0.0946, tau_rel=1.0),
    "balanced": dict(tau_abs=0.0451, tau_rel=0.9268),
    "permissive": dict(tau_abs=0.0554, tau_rel=0.7059),
}
CORPORA = ["idx_mathlib", "idx_full", "idx_blueprint", "idx_elaborated"]


def _art(args, name: str) -> str:
    p = os.path.join(os.path.abspath(args.data_dir), "artifacts", name)
    if not os.path.exists(os.path.join(p, "index.pkl.gz")):
        raise SystemExit(f"missing index {p}\n"
                         f"run:  mathgraph setup --data-dir {args.data_dir}")
    return p


def _aligner(args, corpus="idx_mathlib", **over):
    from .index import load
    from .align import Aligner
    kw = dict(LEX, tau_cov=0.0, delta_margin=0.0)
    kw.update(over)
    return Aligner(load(_art(args, corpus)), **kw)


def _reranker(al, mode: str):
    if mode == "none":
        return None
    if mode == "tree":
        from .treematch import TreeReranker
        return TreeReranker(al, lam=0.9, depth=10000)
    from .structmatch import StructReranker
    return StructReranker(al, lam=0.9, depth=10000)


# -- commands ---------------------------------------------------------------


def cmd_query(args):
    al = _aligner(args, args.corpus)
    rr = _reranker(al, args.rerank)
    if rr is not None:
        names, scored = rr.rank(args.text, args.title or "", args.math or [],
                                topk=args.topk)
        rows = [{"name": n, "score": round(s, 4), "structural": round(t, 4),
                 "module": al.rows[i]["module"]}
                for n, (s, i, t) in zip(names, scored)]
    else:
        a = al.align(args.text, topk=args.topk, title=args.title or "")
        rows = [c.to_json() for c in a.candidates]
    print(json.dumps({"query": args.text, "corpus": args.corpus,
                      "candidates": rows}, indent=2, ensure_ascii=False))


def cmd_verify(args):
    from .verify import Verifier
    al = _aligner(args, args.corpus)
    V = Verifier(al, **VERIFY_PROFILES[args.profile])
    v = V.verify(args.text, args.proposal, args.title or "",
                 math_segments=args.math or [])
    print(json.dumps(v.to_json(), indent=2, ensure_ascii=False))
    return 0 if v.status == "verified" else 1


def cmd_graph(args):
    from .latex import read_project
    from .graph import build_graph, to_dot, to_json
    blocks = read_project(args.tex)
    al = None if args.no_align else _aligner(args, args.corpus,
                                             **GRAPH_THRESHOLDS)
    g = build_graph(blocks, al)
    print(json.dumps(g["summary"], indent=2))
    if args.json:
        open(args.json, "w", encoding="utf-8").write(to_json(g))
        print(f"graph -> {args.json}")
    if args.dot:
        open(args.dot, "w", encoding="utf-8").write(to_dot(g))
        print(f"dot   -> {args.dot}  (render: dot -Tsvg {args.dot} -o g.svg)")


def cmd_bench(args):
    import glob
    from .latex import parse
    from .index import load
    from .align import Aligner
    from .structmatch import StructReranker

    pat = os.path.join(os.path.abspath(args.data_dir), "blueprints", "pfr",
                       "blueprint", "src", "chapter", "*.tex")
    files = sorted(glob.glob(pat))
    if not files:
        raise SystemExit(f"no PFR blueprint sources at {pat}")
    blocks = []
    for f in files:
        blocks.extend(parse(open(f, encoding="utf-8").read()))
    blocks = [b for b in blocks if b.declared_lean and b.kind != "proof"
              and len(b.text.split()) >= 5]

    al = Aligner(load(_art(args, "idx_full")), tau_cov=0.0, delta_margin=0.0,
                 **LEX)
    known = {r["name"] for r in al.rows}
    rr = StructReranker(al, lam=0.9, depth=10000)
    out = {}
    for label, lam in (("lexical", 0.0), ("+structural", 0.9)):
        rr.lam = lam
        h1 = h5 = n = 0
        for b in blocks:
            gold = [g for g in b.declared_lean if g in known]
            if not gold:
                continue
            n += 1
            # gate left at the StructReranker default: `bench` has to measure
            # the configuration `query` actually runs, and the blueprint
            # tuning corpus cannot separate gate values (see README).
            names, _ = rr.rank(b.text, b.title, b.math, topk=5)
            if names and names[0] in gold:
                h1 += 1
            if set(names) & set(gold):
                h5 += 1
        out[label] = {"n": n, "recall@1": round(h1 / n, 3),
                      "recall@5": round(h5 / n, 3)}
    print(json.dumps(out, indent=2))


def cmd_scan(args):
    from .leanscan import write_index
    print(f"{write_index(args.src, args.out)} declarations -> {args.out}")


def cmd_index(args):
    from .index import build, find_ground_truth
    art = os.path.join(os.path.abspath(args.data_dir), "artifacts")
    print(json.dumps(build(args.raw, args.out, args.holdout, args.pmi_holdout,
                           truth=find_ground_truth(art)), indent=2))


def cmd_elaborate(args):
    """Optional upgrade path: replace regex-scraped types with real
    elaborated ones. Requires a built mathlib and a Lean toolchain."""
    from .leanast import dump, to_index_rows, merge_docs
    from .index import build, find_ground_truth
    art = os.path.join(os.path.abspath(args.data_dir), "artifacts")
    mathlib = args.mathlib or os.path.join(os.path.abspath(args.data_dir),
                                           "mathlib4")
    raw = dump(mathlib, out=os.path.join(art, "mathlib_elab_raw.jsonl"))
    rows = os.path.join(art, "mathlib_elab.jsonl")
    n = to_index_rows(raw, rows)
    src = os.path.join(art, "mathlib.jsonl")
    if os.path.exists(src):
        n = merge_docs(rows, src, rows + ".tmp")
        os.replace(rows + ".tmp", rows)
    out = os.path.join(art, "idx_elaborated")
    # `rows` is the environment dump itself, so it is its own ground truth:
    # every to_additive twin in it is already a real declaration and the
    # reconstruction has nothing left to add.
    print(json.dumps({"rows": n,
                      "index": build(rows, out, truth=find_ground_truth(art))},
                     indent=2))
    print("use with:  mathgraph query --corpus idx_elaborated ...")
    print("the scraped indices can now be rebuilt against it: mathgraph setup")


def cmd_setup(args):
    from .setup_cmd import main as setup_main
    return setup_main(args)


# -- parser -----------------------------------------------------------------


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="mathgraph", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", default=DEFAULT_DATA,
                   help=f"corpus + index location (default {DEFAULT_DATA})")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="fetch corpora and build indices")
    s.set_defaults(fn=cmd_setup)

    s = sub.add_parser("query", help="rank candidate declarations")
    s.add_argument("text")
    s.add_argument("--title", default="")
    s.add_argument("--math", action="append",
                   help="LaTeX formula from the statement (repeatable)")
    s.add_argument("--topk", type=int, default=5)
    s.add_argument("--corpus", default="idx_mathlib", choices=CORPORA)
    s.add_argument("--rerank", default="struct",
                   choices=["none", "struct", "tree"])
    s.set_defaults(fn=cmd_query)

    s = sub.add_parser("verify", help="audit a proposed alignment")
    s.add_argument("text")
    s.add_argument("proposal")
    s.add_argument("--title", default="")
    s.add_argument("--math", action="append")
    s.add_argument("--profile", default="permissive",
                   choices=list(VERIFY_PROFILES))
    s.add_argument("--corpus", default="idx_mathlib", choices=CORPORA)
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("graph", help="extract a paper's dependency graph")
    s.add_argument("tex", nargs="+")
    s.add_argument("--dot")
    s.add_argument("--json")
    s.add_argument("--no-align", action="store_true")
    s.add_argument("--corpus", default="idx_mathlib", choices=CORPORA)
    s.set_defaults(fn=cmd_graph)

    s = sub.add_parser("elaborate",
                       help="[optional] rebuild the index from real elaborated "
                            "Lean types (needs a built mathlib)")
    s.add_argument("--mathlib", default=None,
                   help="path to a built mathlib4 checkout")
    s.set_defaults(fn=cmd_elaborate)

    s = sub.add_parser("bench", help="reproduce the PFR benchmark")
    s.set_defaults(fn=cmd_bench)

    s = sub.add_parser("scan", help="scan a Lean source tree")
    s.add_argument("src")
    s.add_argument("out")
    s.set_defaults(fn=cmd_scan)

    s = sub.add_parser("index", help="build an index from scanned declarations")
    s.add_argument("raw")
    s.add_argument("out")
    s.add_argument("--holdout", type=float, default=0.0)
    s.add_argument("--pmi-holdout", dest="pmi_holdout", type=float, default=0.0)
    s.set_defaults(fn=cmd_index)

    args = p.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
