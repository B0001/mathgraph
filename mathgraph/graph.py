"""Assemble the output graph.

Two kinds of edge, and they are not the same kind of claim:

  depends_on   paper statement -> paper statement. Read directly off
               `\\label`/`\\ref`/`\\uses`. Exact; no inference.
  aligns_to    paper statement -> library declaration. A retrieval guess,
               always carrying its status and score.

Keeping them distinguishable in the output is the whole point. A consumer
that cannot tell an authored edge from an inferred one will eventually treat
a guess as a fact.
"""

from __future__ import annotations

import json
from collections import Counter

from .align import Aligner, MATCHED, AMBIGUOUS, UNMATCHED
from .latex import Block


def build_graph(blocks: list[Block], aligner: Aligner | None = None,
                topk: int = 5) -> dict:
    ids = {b.id for b in blocks}
    nodes, edges = [], []
    dangling = []

    for b in blocks:
        node = {
            "id": b.id,
            "kind": b.kind,
            "env": b.env,
            "title": b.title,
            "section": b.section,
            "line": b.line,
            "text": b.text,
            "authored_lean": b.declared_lean,
            "formalized": b.lean_ok,
        }
        if aligner is not None and b.kind in ("theorem", "definition") \
                and len(b.text.split()) >= 4:
            al = aligner.align(b.text, title=b.title, topk=topk)
            node["alignment"] = al.to_json()
        nodes.append(node)

        if b.proof_of:
            edges.append({"src": b.id, "dst": b.proof_of, "type": "proves"})
        for target in sorted(set(b.uses) | set(b.refs)):
            if target in ids:
                edges.append({"src": b.id, "dst": target,
                              "type": "depends_on",
                              "source": "uses" if target in b.uses else "ref"})
            else:
                dangling.append({"src": b.id, "dst": target})

    return {"nodes": nodes, "edges": edges, "dangling_refs": dangling,
            "summary": summarize(nodes, edges, dangling)}


def summarize(nodes, edges, dangling) -> dict:
    claims = [n for n in nodes if n["kind"] in ("theorem", "definition")]
    st = Counter(n.get("alignment", {}).get("status", "not_attempted")
                 for n in claims)
    return {
        "nodes": len(nodes),
        "claims": len(claims),
        "proofs": sum(1 for n in nodes if n["kind"] == "proof"),
        "internal_edges": len(edges),
        "dangling_refs": len(dangling),
        "alignment_status": dict(st),
        "authored_lean_annotations": sum(1 for n in nodes if n["authored_lean"]),
    }


def to_dot(graph: dict) -> str:
    """Graphviz output. Matched library declarations become their own nodes so
    the paper's boundary with the formal library is visible at a glance."""
    out = ["digraph paper {", '  rankdir=BT;',
           '  node [shape=box, style=rounded, fontname="Helvetica", fontsize=10];']
    for n in graph["nodes"]:
        if n["kind"] == "proof":
            continue
        st = n.get("alignment", {}).get("status", "not_attempted")
        fill = {"matched": "#cfe8d5", "ambiguous": "#fdf0c8",
                "unmatched": "#f6d7d7"}.get(st, "#eeeeee")
        label = (n["title"] or n["id"]).replace('"', "'")[:44]
        out.append(f'  "{n["id"]}" [label="{label}", style="rounded,filled", '
                   f'fillcolor="{fill}"];')
        if st == "matched":
            best = n["alignment"]["candidates"][0]["name"]
            out.append(f'  "lib::{best}" [label="{best[:46]}", shape=note, '
                       f'style=filled, fillcolor="#dde6f5"];')
            out.append(f'  "{n["id"]}" -> "lib::{best}" [style=dashed, '
                       f'color="#7a8ba8", label="aligns"];')
    for e in graph["edges"]:
        if e["type"] == "proves":
            continue
        out.append(f'  "{e["src"]}" -> "{e["dst"]}";')
    out.append("}")
    return "\n".join(out)


def to_json(graph: dict) -> str:
    return json.dumps(graph, indent=2, ensure_ascii=False)
