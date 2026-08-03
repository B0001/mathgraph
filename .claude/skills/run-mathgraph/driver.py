#!/usr/bin/env python3
"""mathgraph driver: one process, index loaded once, many probes.

Loading an index costs 4s (idx_mathlib) to 19s and 2.7 GB (idx_elaborated),
so the CLI pays that per invocation and a five-probe investigation costs a
minute and a half of pickle. This keeps one loaded and reads commands from
stdin, so a heredoc of twenty probes costs one load.

    uv run python .claude/skills/run-mathgraph/driver.py <<'EOF'
    load idx_mathlib
    query the entropy of a sum is at most the log of the cardinality
    row Finset.sum_congr
    EOF

    uv run python .claude/skills/run-mathgraph/driver.py --smoke

Commands (one per line, blank lines and #-comments ignored):

    load [corpus]           load an index (default idx_mathlib)
    query <text>            ranked candidates, structural reranker on
    lex <text>              same, reranker off -- isolates the lexical scorer
    verify <text> || <Decl> audit a proposed alignment; prints the verdict
    row <Decl.Name>         the raw index row: provenance, module, head, tokens
    prov                    provenance histogram of the loaded index
    additive <Decl.Name>    names.to_additive_name, the reconstruction itself
    truth <Decl.Name>       does the elaborated environment contain it?
    graph <tex glob>        dependency-graph summary for a paper
    smoke                   the whole checklist, with pass/fail
    quit

Everything prints JSON except errors, which print `!! message`.
"""

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../../..")

from mathgraph import cli as C  # noqa: E402  (thresholds live there, not in a config)
from mathgraph.index import load, find_ground_truth, type_tokens  # noqa: E402
from mathgraph.names import to_additive_name  # noqa: E402
from mathgraph.align import Aligner  # noqa: E402
from mathgraph.structmatch import StructReranker  # noqa: E402
from mathgraph.verify import Verifier  # noqa: E402

DATA = os.environ.get("MATHGRAPH_DATA", "./mathgraph-data")
ART = os.path.join(os.path.abspath(DATA), "artifacts")

STATE = {"corpus": None, "al": None, "rr": None, "byname": None, "truth": None}


def out(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False), flush=True)


def do_load(corpus="idx_mathlib"):
    t = time.time()
    d = os.path.join(ART, corpus)
    if not os.path.exists(os.path.join(d, "index.pkl.gz")):
        raise SystemExit(f"!! no index at {d}\n"
                         f"!! run:  uv run mathgraph setup --data-dir {DATA}")
    art = load(d)
    al = Aligner(art, tau_cov=0.0, delta_margin=0.0, **C.LEX)
    STATE.update(corpus=corpus, al=al,
                 rr=StructReranker(al, lam=0.9, depth=10000),
                 byname={r["name"]: i for i, r in enumerate(al.rows)})
    out({"loaded": corpus, "rows": len(al.rows),
         "typ_postings": len(al.typpost), "seconds": round(time.time() - t, 1)})


def need():
    if STATE["al"] is None:
        do_load()
    return STATE["al"]


def do_query(text, rerank=True):
    al = need()
    if rerank:
        names, scored = STATE["rr"].rank(text, "", [], topk=5)
        rows = [{"name": n, "score": round(s, 4), "structural": round(t, 4),
                 "provenance": al.rows[i].get("provenance", "source")}
                for n, (s, i, t) in zip(names, scored)]
    else:
        rows = [c.to_json() for c in al.align(text, topk=5).candidates]
    out({"query": text, "corpus": STATE["corpus"], "candidates": rows})


def do_verify(arg):
    al = need()
    if "||" not in arg:
        return print("!! usage: verify <text> || <Decl.Name>", flush=True)
    text, proposal = (s.strip() for s in arg.split("||", 1))
    V = Verifier(al, **C.VERIFY_PROFILES["permissive"])
    out(V.verify(text, proposal, "").to_json())


def do_row(name):
    al = need()
    i = STATE["byname"].get(name)
    if i is None:
        return out({"name": name, "in_index": False})
    r = dict(al.rows[i])
    r["in_index"] = True
    r["tokens"] = list(r.get("tokens", []))[:20]
    r["head"] = (r.get("head") or "")[:300]
    r["doc"] = (r.get("doc") or "")[:200]
    out(r)


def do_prov():
    from collections import Counter
    al = need()
    out(dict(Counter(r.get("provenance", "source") for r in al.rows)))


def do_truth(name):
    if STATE["truth"] is None:
        t = find_ground_truth(ART)
        if t is None:
            return print(f"!! no {ART}/mathlib_elab.jsonl -- run "
                         "`mathgraph elaborate` for a ground truth", flush=True)
        STATE["truth"] = t
    out({"name": name, "in_elaborated_environment": name in STATE["truth"],
         "environment_size": len(STATE["truth"])})


def do_graph(pattern):
    from mathgraph.latex import read_project
    from mathgraph.graph import build_graph
    files = sorted(glob.glob(pattern))
    if not files:
        return print(f"!! no .tex matched {pattern}", flush=True)
    al = need()
    for k, v in C.GRAPH_THRESHOLDS.items():   # query runs wide open, graph does not
        setattr(al, k, v)
    g = build_graph(read_project(files), al)
    out({"files": len(files), **g["summary"]})
    for k, v in dict(tau_cov=0.0, delta_margin=0.0).items():
        setattr(al, k, v)


def do_smoke():
    """The checklist. Exits non-zero on the first thing that is not true."""
    bad = []

    def check(label, ok, got=""):
        print(f"{'PASS' if ok else 'FAIL'}  {label}  {got}", flush=True)
        if not ok:
            bad.append(label)

    check("to_additive_name translates", to_additive_name("Finset.prod_congr")
          == "Finset.sum_congr", to_additive_name("Finset.prod_congr"))
    check("untranslatable returns None", to_additive_name("Nat.succ_le") is None)
    # the third field reaches a hypothesis the name never mentions, and the
    # `elaborated` flag decides whether `:=` starts a body or a structure
    head = "[T2Space X] : IsCompact s -> IsClosed s := byBlah"
    check("type_tokens reaches the hypothesis",
          {"t2", "space"} <= set(type_tokens(head)), type_tokens(head))
    check("elaborated flag changes what := means",
          "by" not in type_tokens(head)
          and "by" in type_tokens(head, elaborated=True))

    try:
        do_load()
    except SystemExit as e:                  # the logic checks above still ran
        print(f"{e}\nSKIP  every corpus check", flush=True)
        return 1 if bad else 0
    al = STATE["al"]
    check("index has rows", len(al.rows) > 100000, len(al.rows))
    check("third field populated", len(al.typpost) > 1000, len(al.typpost))

    names, _ = STATE["rr"].rank(
        "the entropy of a sum is at most the log of the cardinality", "",
        [r"d[X;Y] \leq \bbH[X+Y]"], topk=5)
    check("query returns 5 candidates", len(names) == 5, names[:2])

    V = Verifier(al, **C.VERIFY_PROFILES["permissive"])
    v = V.verify("a nonexistent statement about nothing", "No.Such.Decl", "")
    check("nonexistent name is caught", v.status == "nonexistent", v.status)

    from mathgraph.latex import read_project
    from mathgraph.graph import build_graph
    tex = sorted(glob.glob(os.path.join(
        DATA, "blueprints/pfr/blueprint/src/chapter/*.tex")))
    if tex:
        for k, val in C.GRAPH_THRESHOLDS.items():
            setattr(al, k, val)
        s = build_graph(read_project(tex), al)["summary"]
        check("graph abstains rather than guessing",
              s["alignment_status"].get("matched", 0) * 4
              < s["alignment_status"]["unmatched"], s["alignment_status"])
    else:
        print("SKIP  graph (no PFR blueprint under $MATHGRAPH_DATA)", flush=True)

    print(f"\n{'all checks passed' if not bad else 'FAILED: ' + ', '.join(bad)}",
          flush=True)
    return 1 if bad else 0


def dispatch(line):
    cmd, _, rest = line.partition(" ")
    rest = rest.strip()
    if cmd == "load":
        do_load(rest or "idx_mathlib")
    elif cmd == "query":
        do_query(rest)
    elif cmd == "lex":
        do_query(rest, rerank=False)
    elif cmd == "verify":
        do_verify(rest)
    elif cmd == "row":
        do_row(rest)
    elif cmd == "prov":
        do_prov()
    elif cmd == "additive":
        out({"name": rest, "additive": to_additive_name(rest)})
    elif cmd == "truth":
        do_truth(rest)
    elif cmd == "graph":
        do_graph(rest)
    elif cmd == "smoke":
        do_smoke()
    else:
        print(f"!! unknown command {cmd!r} -- see the docstring", flush=True)


def main():
    if "--smoke" in sys.argv:
        return do_smoke()
    for line in sys.stdin:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line in ("quit", "exit"):
            break
        try:
            dispatch(line)
        except Exception as e:                       # a bad probe must not
            print(f"!! {type(e).__name__}: {e}", flush=True)   # kill the load
    return 0


if __name__ == "__main__":
    sys.exit(main())
