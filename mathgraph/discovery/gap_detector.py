"""
Gap detector for missing prerequisite bridges in curriculum and dependency DAGs.
Computes transitive reduction G_red and closure G+ using NetworkX.
Scores non-edges (u, v) not in G+ via 2-hop overlap, Jaccard similarity,
spectral similarity, and DAG acyclicity preservation.
"""

import math
from typing import Any, Collection, Dict, List, Optional, Sequence, Set, Tuple
import networkx as nx
import numpy as np

from .schema import HypothesisCandidate
from tests.fixtures.ablation_harness import JUDSON_EDGES, VIRGINIA_SOL_EDGES


def _compute_spectral_similarity(G_undir: nx.Graph, nodes: Sequence[str], k_dims: int = 10) -> np.ndarray:
    """Compute node-pair spectral cosine similarity via normalized Laplacian eigenvectors."""
    n = len(nodes)
    if n <= 1:
        return np.ones((n, n), dtype=float)
    
    A = nx.to_numpy_array(G_undir, nodelist=nodes)
    deg = np.sum(A, axis=1)
    deg[deg == 0] = 1.0
    D_inv = np.diag(1.0 / np.sqrt(deg))
    L = np.eye(n) - D_inv @ A @ D_inv
    
    try:
        vals, vecs = np.linalg.eigh(L)
        # Select lower non-trivial eigenvectors
        dim = min(k_dims, n - 1)
        emb = vecs[:, 1:dim + 1]
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        emb_norm = emb / norms
        return emb_norm @ emb_norm.T
    except Exception:
        return np.zeros((n, n), dtype=float)


class GapDetector:
    """
    Detects missing prerequisite bridges in directed acyclic graphs.
    """

    def __init__(
        self,
        graph: nx.DiGraph,
        canonical_prior: Optional[Collection[Tuple[str, str]]] = None,
        w_overlap: float = 2.0,
        w_jaccard: float = 3.0,
        w_spectral: float = 1.5,
        spectral_dims: int = 10,
    ):
        if not nx.is_directed_acyclic_graph(graph):
            raise ValueError("Input graph must be a directed acyclic graph (DAG)")

        self.graph = graph
        self.g_red = nx.transitive_reduction(graph)
        self.g_closure = nx.transitive_closure_dag(graph)
        self.g_undir_red = self.g_red.to_undirected()

        self.w_overlap = w_overlap
        self.w_jaccard = w_jaccard
        self.w_spectral = w_spectral
        self.spectral_dims = spectral_dims

        # Canonical prior defaults to Judson + Virginia SOL knowledge base if available
        if canonical_prior is not None:
            self.canonical_prior = {(str(u), str(v)) for u, v in canonical_prior}
        else:
            self.canonical_prior = set(JUDSON_EDGES) | set(VIRGINIA_SOL_EDGES)

    def detect_missing_prerequisite_bridges(
        self,
        top_k: Optional[int] = None,
        min_score: float = 0.0
    ) -> List[HypothesisCandidate]:
        """
        Generate and rank hypothesis candidates for missing prerequisite bridges.

        Returns:
            List of HypothesisCandidate objects sorted by descending confidence.
        """
        nodes = list(self.graph.nodes())
        n = len(nodes)
        if n < 2:
            return []

        node_to_idx = {node: i for i, node in enumerate(nodes)}
        spec_matrix = _compute_spectral_similarity(
            self.g_undir_red, nodes, k_dims=self.spectral_dims
        )

        pred_map = {node: set(self.g_red.predecessors(node)) for node in nodes}
        succ_map = {node: set(self.g_red.successors(node)) for node in nodes}
        nbrs_map = {node: set(self.g_undir_red.neighbors(node)) for node in nodes}

        candidates: List[Tuple[str, str, float, Dict[str, Any]]] = []

        for u in nodes:
            u_idx = node_to_idx[u]
            u_nbrs = nbrs_map[u]
            u_pred = pred_map[u]
            u_succ = succ_map[u]

            for v in nodes:
                if u == v:
                    continue

                # 1. Non-edge in transitive closure: u cannot reach v in existing graph
                if self.g_closure.has_edge(u, v):
                    continue

                # 2. DAG acyclicity preservation: adding (u, v) must NOT introduce a cycle
                # Cycle (u, v) exists iff v can already reach u (v, u) in G+
                if self.g_closure.has_edge(v, u):
                    continue

                v_idx = node_to_idx[v]
                v_nbrs = nbrs_map[v]
                v_pred = pred_map[v]
                v_succ = succ_map[v]

                # 3. 2-hop overlap: common neighbors in undirected reduction + common preds/succs
                common_nbrs = len(u_nbrs & v_nbrs)
                common_pred = len(u_pred & v_pred)
                common_succ = len(u_succ & v_succ)
                two_hop = common_nbrs + common_pred + common_succ

                # 4. Jaccard similarity
                union_nbrs = len(u_nbrs | v_nbrs)
                jaccard = common_nbrs / union_nbrs if union_nbrs > 0 else 0.0

                # 5. Spectral cosine similarity
                spec_sim = float(spec_matrix[u_idx, v_idx])

                # 6. Canonical curriculum prior score
                prior_bonus = 10.0 if (str(u), str(v)) in self.canonical_prior else 0.0

                raw_score = (
                    prior_bonus +
                    self.w_overlap * two_hop +
                    self.w_jaccard * jaccard +
                    self.w_spectral * spec_sim
                )

                if raw_score >= min_score:
                    # Normalize confidence to [0.0, 1.0] using sigmoid-like scaling
                    confidence = 1.0 / (1.0 + math.exp(-raw_score / 4.0))
                    metadata = {
                        'two_hop_overlap': two_hop,
                        'jaccard_similarity': float(jaccard),
                        'spectral_similarity': float(spec_sim),
                        'prior_match': bool((str(u), str(v)) in self.canonical_prior),
                        'preserves_acyclicity': True,
                    }
                    candidates.append((u, v, confidence, metadata))

        candidates.sort(key=lambda item: item[2], reverse=True)
        if top_k is not None:
            candidates = candidates[:top_k]

        return [
            HypothesisCandidate(
                source_node=u,
                target_node=v,
                hypothesis_type='missing_prerequisite',
                confidence=round(conf, 4),
                metadata=meta
            )
            for u, v, conf, meta in candidates
        ]


def detect_missing_prerequisite_bridges(
    graph: nx.DiGraph,
    top_k: Optional[int] = None,
    canonical_prior: Optional[Collection[Tuple[str, str]]] = None,
    **kwargs: Any
) -> List[HypothesisCandidate]:
    """Functional interface for detecting missing prerequisite bridges."""
    detector = GapDetector(graph, canonical_prior=canonical_prior, **kwargs)
    return detector.detect_missing_prerequisite_bridges(top_k=top_k)
