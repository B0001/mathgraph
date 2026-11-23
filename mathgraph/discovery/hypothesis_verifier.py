"""
Hypothesis verifier and falsification filter for structural discovery conjectures.
Enforces:
(1) Strict DAG acyclicity check
(2) Topological depth monotonicity level(u) < level(v)
(3) Pluggable symbolic/LLM counterexample check

Acceptance: Zero cycles introduced when applying any subset of accepted missing_bridge edges.
"""

from dataclasses import dataclass
from typing import Any, Callable, Collection, Dict, List, Optional, Protocol, Sequence, Set, Tuple
import networkx as nx

from .schema import HypothesisCandidate


@dataclass(frozen=True)
class VerificationResult:
    candidate: HypothesisCandidate
    accepted: bool
    rejection_reason: Optional[str] = None
    level_u: Optional[int] = None
    level_v: Optional[int] = None


class CounterexampleChecker(Protocol):
    """Protocol for pluggable symbolic or LLM counterexample checkers."""
    def check(self, candidate: HypothesisCandidate, graph: nx.DiGraph) -> Tuple[bool, Optional[str]]:
        """
        Return (is_falsified, rejection_reason).
        If is_falsified is True, the candidate is rejected.
        """
        ...


class TrivialCounterexampleChecker:
    """Built-in symbolic counterexample checker rejecting self-loops and forbidden pairs."""

    def __init__(self, forbidden_pairs: Optional[Collection[Tuple[str, str]]] = None):
        self.forbidden_pairs: Set[Tuple[str, str]] = (
            {(str(u), str(v)) for u, v in forbidden_pairs} if forbidden_pairs else set()
        )

    def check(self, candidate: HypothesisCandidate, graph: nx.DiGraph) -> Tuple[bool, Optional[str]]:
        u, v = candidate.source_node, candidate.target_node
        if u == v:
            return True, f'Self-loop candidate ({u} -> {v}) is forbidden'
        if (u, v) in self.forbidden_pairs:
            return True, f'Candidate ({u} -> {v}) matches forbidden domain pair'
        return False, None


class HypothesisVerifier:
    """
    Verifies and filters hypothesis candidates using DAG invariants and counterexample checks.
    """

    def __init__(
        self,
        base_graph: nx.DiGraph,
        counterexample_checker: Optional[Callable[[HypothesisCandidate, nx.DiGraph], Tuple[bool, Optional[str]]]] = None,
        enforce_depth_monotonicity: bool = True,
        level_map: Optional[Dict[str, int]] = None,
    ):
        if not nx.is_directed_acyclic_graph(base_graph):
            raise ValueError('base_graph must be a directed acyclic graph (DAG)')

        self.base_graph = base_graph.copy()
        self.enforce_depth_monotonicity = enforce_depth_monotonicity

        # Pluggable counterexample checker defaults to TrivialCounterexampleChecker
        if counterexample_checker is not None:
            self.checker = counterexample_checker
        else:
            self.checker = TrivialCounterexampleChecker().check

        # Compute topological levels
        if level_map is not None:
            self.levels = dict(level_map)
        else:
            self.levels = {}
            for gen_idx, gen in enumerate(nx.topological_generations(self.base_graph)):
                for node in gen:
                    self.levels[node] = gen_idx

    def get_level(self, node: str) -> int:
        """Return the topological depth of a node (default 0 for unknown nodes)."""
        return self.levels.get(node, 0)

    def verify_single(self, candidate: HypothesisCandidate, current_graph: Optional[nx.DiGraph] = None) -> VerificationResult:
        """
        Verify a single candidate against current graph state.
        """
        graph = current_graph if current_graph is not None else self.base_graph
        u, v = candidate.source_node, candidate.target_node
        lvl_u = self.get_level(u)
        lvl_v = self.get_level(v)

        # 1. Self-loop check
        if u == v:
            return VerificationResult(
                candidate=candidate,
                accepted=False,
                rejection_reason='Self-loop: source and target are identical',
                level_u=lvl_u,
                level_v=lvl_v,
            )

        # 2. Strict DAG acyclicity check
        # An edge (u, v) introduces a cycle iff there is already a path from v to u
        if graph.has_node(u) and graph.has_node(v) and nx.has_path(graph, v, u):
            return VerificationResult(
                candidate=candidate,
                accepted=False,
                rejection_reason=f'Violates DAG acyclicity: path exists from {v} to {u}',
                level_u=lvl_u,
                level_v=lvl_v,
            )

        # 3. Topological depth monotonicity: level(u) < level(v)
        if self.enforce_depth_monotonicity and lvl_u >= lvl_v:
            return VerificationResult(
                candidate=candidate,
                accepted=False,
                rejection_reason=f'Violates depth monotonicity: level({u})={lvl_u} >= level({v})={lvl_v}',
                level_u=lvl_u,
                level_v=lvl_v,
            )

        # 4. Pluggable symbolic/LLM counterexample check
        falsified, reason = self.checker(candidate, graph)
        if falsified:
            return VerificationResult(
                candidate=candidate,
                accepted=False,
                rejection_reason=reason or 'Falsified by counterexample checker',
                level_u=lvl_u,
                level_v=lvl_v,
            )

        return VerificationResult(
            candidate=candidate,
            accepted=True,
            rejection_reason=None,
            level_u=lvl_u,
            level_v=lvl_v,
        )

    def filter_candidates(
        self,
        candidates: Sequence[HypothesisCandidate],
        max_accepted: Optional[int] = None
    ) -> List[HypothesisCandidate]:
        """
        Incrementally verify and filter a sequence of candidates.
        Ensures that applying any subset of accepted candidates to base_graph introduces zero cycles.

        Returns:
            List of accepted HypothesisCandidate objects with updated verification metadata.
        """
        current_graph = self.base_graph.copy()
        accepted_candidates: List[HypothesisCandidate] = []

        for cand in candidates:
            if max_accepted is not None and len(accepted_candidates) >= max_accepted:
                break

            result = self.verify_single(cand, current_graph=current_graph)
            if result.accepted:
                # Add to current augmented graph
                current_graph.add_edge(cand.source_node, cand.target_node)

                # Attach verification metadata
                meta = dict(cand.metadata)
                meta['verified'] = True
                meta['level_u'] = result.level_u
                meta['level_v'] = result.level_v

                verified_cand = HypothesisCandidate(
                    source_node=cand.source_node,
                    target_node=cand.target_node,
                    hypothesis_type=cand.hypothesis_type,
                    confidence=cand.confidence,
                    metadata=meta,
                )
                accepted_candidates.append(verified_cand)

        return accepted_candidates


def verify_hypotheses(
    candidates: Sequence[HypothesisCandidate],
    graph: nx.DiGraph,
    counterexample_checker: Optional[Callable[[HypothesisCandidate, nx.DiGraph], Tuple[bool, Optional[str]]]] = None,
    enforce_depth_monotonicity: bool = True,
    level_map: Optional[Dict[str, int]] = None,
    max_accepted: Optional[int] = None,
) -> List[HypothesisCandidate]:
    """Functional interface for verifying and filtering hypothesis candidates."""
    verifier = HypothesisVerifier(
        base_graph=graph,
        counterexample_checker=counterexample_checker,
        enforce_depth_monotonicity=enforce_depth_monotonicity,
        level_map=level_map,
    )
    return verifier.filter_candidates(candidates, max_accepted=max_accepted)
