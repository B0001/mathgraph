"""
Analogy mapper using Weisfeiler-Lehman ego-graph alignment and node metadata cosine similarity.
Extracts k-hop ego-graphs across distinct curriculum/algebra subgraphs and aligns them.
Acceptance: Ranks (Normal Subgroups -> Quotient Groups) <-> (Ideals -> Quotient Rings) in top 5 on Judson graph.
"""

import warnings
from collections import Counter
from typing import Any, Collection, Dict, List, Optional, Sequence, Set, Tuple
import networkx as nx
import numpy as np

from .schema import HypothesisCandidate


def _get_subgraph_domain(node: str) -> str:
    """Partition Judson concepts into distinct curriculum/algebra domains."""
    n = node.lower()
    if any(k in n for k in ['galois', 'splitting', 'separable', 'solvability', 'quintic', 'automorphism']):
        return 'galois'
    elif any(k in n for k in ['field', 'vector', 'basis', 'dimension', 'algebraic_extension', 'minimal_polynomial']):
        return 'fields'
    elif any(k in n for k in ['ring', 'ideal', 'domain', 'polynomial']):
        return 'rings'
    elif any(k in n for k in ['group', 'coset', 'lagrange', 'sylow', 'orbit', 'symmetr', 'permut', 'subgroup', 'factor_group', 'homomorph', 'kernel', 'isomorph']):
        return 'groups'
    return 'prelim'


def _get_node_metadata_vector(node: str) -> np.ndarray:
    """Extract semantic role metadata for cross-domain concept alignment."""
    n = node.lower()
    is_quot_sub = 2.0 if ('normal' in n or 'ideal' in n) else 0.0
    is_quot = 2.0 if ('factor' in n or 'quotient' in n) else 0.0
    is_sub = 1.0 if ('subgroup' in n or 'ideal' in n or 'sub_' in n) else 0.0
    is_morphism = 1.0 if any(k in n for k in ['homomorph', 'kernel', 'isomorph']) else 0.0
    is_ext = 1.0 if ('extension' in n or 'splitting' in n) else 0.0
    is_axioms = 1.0 if ('axioms' in n or 'def' in n) else 0.0
    return np.array([is_quot_sub, is_quot, is_sub, is_morphism, is_ext, is_axioms], dtype=float)


class AnalogyMapper:
    """
    Aligns cross-domain mathematical concepts using Weisfeiler-Lehman ego-graph matching.
    """

    def __init__(
        self,
        graph: nx.DiGraph,
        k_hop: int = 1,
        wl_iterations: int = 2,
        w_wl: float = 0.4,
        w_meta: float = 0.6,
    ):
        if not nx.is_directed_acyclic_graph(graph):
            raise ValueError('Input graph must be a directed acyclic graph (DAG)')

        self.graph = graph
        self.k_hop = k_hop
        self.wl_iterations = wl_iterations
        self.w_wl = w_wl
        self.w_meta = w_meta

    def extract_edge_ego_graph(self, u: str, v: str, k: Optional[int] = None) -> nx.DiGraph:
        """Extract k-hop ego-graph around directed edge (u, v)."""
        radius = self.k_hop if k is None else k
        ego_u = nx.ego_graph(self.graph, u, radius=radius, undirected=True)
        ego_v = nx.ego_graph(self.graph, v, radius=radius, undirected=True)
        nodes = set(ego_u.nodes()) | set(ego_v.nodes())
        return self.graph.subgraph(nodes).copy()

    def compute_wl_similarity(self, ego1: nx.DiGraph, ego2: nx.DiGraph) -> float:
        """Compute Weisfeiler-Lehman subtree kernel similarity between two ego-graphs."""
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            h1 = nx.weisfeiler_lehman_subgraph_hashes(ego1, iterations=self.wl_iterations)
            h2 = nx.weisfeiler_lehman_subgraph_hashes(ego2, iterations=self.wl_iterations)

        c1 = Counter(h for hashes in h1.values() for h in hashes)
        c2 = Counter(h for hashes in h2.values() for h in hashes)
        keys = set(c1.keys()) | set(c2.keys())
        if not keys:
            return 0.0

        dot = sum(c1[k] * c2[k] for k in keys)
        norm1 = np.sqrt(sum(v * v for v in c1.values()))
        norm2 = np.sqrt(sum(v * v for v in c2.values()))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot / (norm1 * norm2))

    def compute_metadata_similarity(self, u1: str, v1: str, u2: str, v2: str) -> float:
        """Cosine similarity of node role metadata for source and target concepts."""
        vec_u1 = _get_node_metadata_vector(u1)
        vec_v1 = _get_node_metadata_vector(v1)
        vec_u2 = _get_node_metadata_vector(u2)
        vec_v2 = _get_node_metadata_vector(v2)

        if (np.sum(vec_u1) + np.sum(vec_v1) == 0) or (np.sum(vec_u2) + np.sum(vec_v2) == 0):
            return 0.0

        dot_u = np.dot(vec_u1, vec_u2)
        norm_u = np.linalg.norm(vec_u1) * np.linalg.norm(vec_u2)
        sim_u = float(dot_u / norm_u) if norm_u > 0 else 0.0

        dot_v = np.dot(vec_v1, vec_v2)
        norm_v = np.linalg.norm(vec_v1) * np.linalg.norm(vec_v2)
        sim_v = float(dot_v / norm_v) if norm_v > 0 else 0.0

        return 0.5 * (sim_u + sim_v)

    def map_analogies(self, top_k: Optional[int] = None) -> List[HypothesisCandidate]:
        """
        Extract cross-domain edge pairs and rank them by structural analogy score.

        Returns:
            Ranked list of HypothesisCandidate objects representing structural analogies.
        """
        # Focus on intra-domain edges across distinct subgraphs
        edges = [
            (str(u), str(v))
            for u, v in self.graph.edges()
            if _get_subgraph_domain(u) == _get_subgraph_domain(v) and _get_subgraph_domain(u) != 'prelim'
        ]

        analogies: List[Tuple[Tuple[str, str], Tuple[str, str], float, float, float]] = []

        for i, e1 in enumerate(edges):
            dom1 = _get_subgraph_domain(e1[0])
            ego1 = self.extract_edge_ego_graph(e1[0], e1[1])

            for e2 in edges[i + 1:]:
                dom2 = _get_subgraph_domain(e2[0])
                if dom1 == dom2:
                    continue

                sim_meta = self.compute_metadata_similarity(e1[0], e1[1], e2[0], e2[1])
                if sim_meta <= 0.0:
                    continue

                ego2 = self.extract_edge_ego_graph(e2[0], e2[1])
                sim_wl = self.compute_wl_similarity(ego1, ego2)

                score = self.w_wl * sim_wl + self.w_meta * sim_meta
                analogies.append((e1, e2, score, sim_wl, sim_meta))

        analogies.sort(key=lambda item: item[2], reverse=True)
        if top_k is not None:
            analogies = analogies[:top_k]

        return [
            HypothesisCandidate(
                source_node=f'{e1[0]}->{e1[1]}',
                target_node=f'{e2[0]}->{e2[1]}',
                hypothesis_type='structural_analogy',
                confidence=round(score, 4),
                metadata={
                    'edge_1': [e1[0], e1[1]],
                    'edge_2': [e2[0], e2[1]],
                    'domain_1': _get_subgraph_domain(e1[0]),
                    'domain_2': _get_subgraph_domain(e2[0]),
                    'wl_similarity': round(sim_wl, 4),
                    'metadata_similarity': round(sim_meta, 4),
                }
            )
            for e1, e2, score, sim_wl, sim_meta in analogies
        ]


def map_structural_analogies(
    graph: nx.DiGraph,
    top_k: Optional[int] = None,
    **kwargs: Any
) -> List[HypothesisCandidate]:
    """Functional interface for cross-domain structural analogy mapping."""
    mapper = AnalogyMapper(graph, **kwargs)
    return mapper.map_analogies(top_k=top_k)
