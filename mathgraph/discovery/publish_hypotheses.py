"""
CLI tool for publishing structural conjectures and hypotheses from graph discovery pipelines.
Emits ranked hypotheses.json with provenance paths, confidence scores, and verification metadata.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
import networkx as nx

from .ablation_harness import build_judson_dag, build_virginia_sol_dag
from .analogy_mapper import map_structural_analogies
from .gap_detector import detect_missing_prerequisite_bridges
from .homology_holes import detect_topological_voids
from .hypothesis_verifier import verify_hypotheses
from .schema import HypothesisCandidate


def load_graph_or_default(graph_path: Optional[str] = None, dag_name: str = 'judson') -> nx.DiGraph:
    """Load DAG from JSON edge-list file or return canonical benchmark DAG."""
    if graph_path and Path(graph_path).exists():
        with open(graph_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        G = nx.DiGraph()
        if isinstance(data, list):
            for item in data:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    G.add_edge(str(item[0]), str(item[1]))
                elif isinstance(item, dict) and 'source' in item and 'target' in item:
                    G.add_edge(str(item['source']), str(item['target']))
        elif isinstance(data, dict) and 'edges' in data:
            for u, v in data['edges']:
                G.add_edge(str(u), str(v))
        return G

    if dag_name.lower() in ('virginia', 'virginia_sol', 'sol'):
        return build_virginia_sol_dag()
    return build_judson_dag()


def run_discovery_pipeline(
    graph: nx.DiGraph,
    include_bridges: bool = True,
    include_voids: bool = True,
    include_analogies: bool = True,
    verify: bool = True,
    top_k: Optional[int] = None,
) -> List[HypothesisCandidate]:
    """Execute full discovery engine over DAG and return ranked verified hypotheses."""
    all_candidates: List[HypothesisCandidate] = []

    # 1. Missing prerequisite bridges
    if include_bridges:
        bridge_candidates = detect_missing_prerequisite_bridges(graph)
        if verify:
            verified_bridges = verify_hypotheses(bridge_candidates, graph)
            all_candidates.extend(verified_bridges)
        else:
            all_candidates.extend(bridge_candidates)

    # 2. Topological voids / homology holes
    if include_voids:
        void_candidates = detect_topological_voids(graph)
        all_candidates.extend(void_candidates)

    # 3. Cross-domain structural analogies
    if include_analogies:
        analogy_candidates = map_structural_analogies(graph)
        all_candidates.extend(analogy_candidates)

    # Global ranking by confidence
    all_candidates.sort(key=lambda c: c.confidence, reverse=True)
    if top_k is not None:
        all_candidates = all_candidates[:top_k]

    return all_candidates


def publish_hypotheses(
    graph: Optional[nx.DiGraph] = None,
    graph_path: Optional[str] = None,
    dag_name: str = 'judson',
    out_path: str = 'hypotheses.json',
    top_k: Optional[int] = 50,
    verify: bool = True,
) -> List[Dict[str, Any]]:
    """
    Generate hypotheses, serialize to hypotheses.json, and return serialized records.
    """
    if graph is None:
        graph = load_graph_or_default(graph_path=graph_path, dag_name=dag_name)

    candidates = run_discovery_pipeline(
        graph=graph,
        verify=verify,
        top_k=top_k,
    )

    records: List[Dict[str, Any]] = [
        {
            'source_node': c.source_node,
            'target_node': c.target_node,
            'hypothesis_type': c.hypothesis_type,
            'confidence': c.confidence,
            'metadata': c.metadata,
        }
        for c in candidates
    ]

    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=2)

    return records


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI main entrypoint."""
    parser = argparse.ArgumentParser(description='Publish structural conjectures and hypotheses')
    parser.add_argument('--graph', type=str, default=None, help='Path to input graph JSON')
    parser.add_argument('--dag', type=str, default='judson', choices=['judson', 'virginia_sol'], help='Benchmark DAG')
    parser.add_argument('--out', type=str, default='hypotheses.json', help='Output JSON path')
    parser.add_argument('--top-k', type=int, default=50, help='Max number of hypotheses to output')
    parser.add_argument('--no-verify', dest='verify', action='store_false', help='Skip verification stage')
    args = parser.parse_args(argv)

    results = publish_hypotheses(
        graph_path=args.graph,
        dag_name=args.dag,
        out_path=args.out,
        top_k=args.top_k,
        verify=args.verify,
    )

    print(f'Successfully published {len(results)} hypotheses to {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
