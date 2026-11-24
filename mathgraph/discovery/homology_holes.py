"""
Homology holes and topological void detector for mathematical dependency DAGs.
Detects unclosed diamond/square motifs (u -> a -> w, u -> b -> w) where
intermediates a, b exceed a semantic/structural distance threshold without
a direct synthesizing node.
"""

import math
from typing import Any, Collection, Dict, List, Optional, Sequence, Set, Tuple
import networkx as nx
import numpy as np

from .schema import HypothesisCandidate


def _compute_semantic_token_distance(a: str, b: str) -> float:
    """Compute Jaccard distance 1 - J(tokens_a, tokens_b)."""
    tokens_a = set(a.lower().split('_'))
    tokens_b = set(b.lower().split('_'))
    stems_a = {t[:-1] if t.endswith('s') and len(t) > 3 else t for t in tokens_a}
    stems_b = {t[:-1] if t.endswith('s') and len(t) > 3 else t for t in tokens_b}
    all_a = tokens_a | stems_a
    all_b = tokens_b | stems_b
    if not (all_a | all_b):
        return 1.0
    sim = len(all_a & all_b) / len(all_a | all_b)
    return float(1.0 - sim)


class HomologyVoidDetector:
    """
    Detects topological voids (unclosed diamond/square loops) in dependency graphs.
    """

    def __init__(
        self,
        graph: nx.DiGraph,
        distance_threshold: float = 0.5,
        max_path_length: int = 2,
    ):
        if not nx.is_directed_acyclic_graph(graph):
            raise ValueError('Input graph must be a directed acyclic graph (DAG)')

        self.graph = graph
        self.distance_threshold = distance_threshold
        self.max_path_length = max_path_length
        self.g_undir = graph.to_undirected()

    def _compute_structural_distance(self, a: str, b: str, u: str, w: str) -> float:
        """
        Compute structural distance between intermediates a and b on graph excluding u and w.
        """
        sub = self.g_undir.copy()
        sub.remove_nodes_from([u, w])
        if not sub.has_node(a) or not sub.has_node(b):
            return 1.0
        if not nx.has_path(sub, a, b):
            return 1.0
        dist = nx.shortest_path_length(sub, a, b)
        # Normalize distance into [0.0, 1.0]
        return float(min(1.0, dist / 4.0))

    def detect_topological_voids(
        self,
        top_k: Optional[int] = None
    ) -> List[HypothesisCandidate]:
        """
        Find unclosed diamond/square motifs and emit topological_void candidates.

        Returns:
            List of HypothesisCandidate objects with supporting paths in metadata.
        """
        candidates: List[HypothesisCandidate] = []
        seen_motifs: Set[Tuple[str, str, str, str]] = set()

        for u in self.graph.nodes():
            succ_u = sorted(list(self.graph.successors(u)))
            if len(succ_u) < 2:
                continue

            for i, a in enumerate(succ_u):
                for b in succ_u[i + 1:]:
                    # Find common successors w where both a -> w and b -> w
                    common_w = sorted(list(set(self.graph.successors(a)) & set(self.graph.successors(b))))
                    for w in common_w:
                        motif_key = (u, min(a, b), max(a, b), w)
                        if motif_key in seen_motifs:
                            continue
                        seen_motifs.add(motif_key)

                        # Check for synthesizing connection between a and b:
                        # Direct edges a -> b or b -> a
                        has_direct = self.graph.has_edge(a, b) or self.graph.has_edge(b, a)
                        if has_direct:
                            continue

                        # Check for intermediate synthesizing node s: a -> s -> b or b -> s -> a
                        succ_a = set(self.graph.successors(a))
                        succ_b = set(self.graph.successors(b))
                        pred_a = set(self.graph.predecessors(a))
                        pred_b = set(self.graph.predecessors(b))
                        has_mediator = bool((succ_a & pred_b) | (succ_b & pred_a))
                        if has_mediator:
                            continue

                        # Compute semantic and structural distances between a and b
                        sem_dist = _compute_semantic_token_distance(a, b)
                        struct_dist = self._compute_structural_distance(a, b, u, w)
                        combined_dist = 0.5 * sem_dist + 0.5 * struct_dist

                        if combined_dist >= self.distance_threshold or sem_dist >= self.distance_threshold:
                            # Higher distance indicates a more pronounced void
                            conf = min(0.99, max(0.5, combined_dist * 0.95))
                            cand = HypothesisCandidate(
                                source_node=a,
                                target_node=b,
                                hypothesis_type='topological_void',
                                confidence=round(conf, 4),
                                metadata={
                                    'motif': [u, a, b, w],
                                    'origin': u,
                                    'convergence': w,
                                    'intermediate_a': a,
                                    'intermediate_b': b,
                                    'path_a': [u, a, w],
                                    'path_b': [u, b, w],
                                    'supporting_paths': [[u, a, w], [u, b, w]],
                                    'semantic_distance': round(sem_dist, 4),
                                    'structural_distance': round(struct_dist, 4),
                                    'combined_distance': round(combined_dist, 4),
                                }
                            )
                            candidates.append(cand)

        candidates.sort(key=lambda c: c.confidence, reverse=True)
        if top_k is not None:
            candidates = candidates[:top_k]
        return candidates


def detect_topological_voids(
    graph: nx.DiGraph,
    distance_threshold: float = 0.5,
    top_k: Optional[int] = None
) -> List[HypothesisCandidate]:
    """Functional interface for detecting topological voids in a DAG."""
    detector = HomologyVoidDetector(graph, distance_threshold=distance_threshold)
    return detector.detect_topological_voids(top_k=top_k)
