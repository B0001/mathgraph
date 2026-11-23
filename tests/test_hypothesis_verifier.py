import itertools
import pytest
import networkx as nx

from mathgraph.discovery.hypothesis_verifier import (
    HypothesisVerifier,
    verify_hypotheses,
    VerificationResult,
    TrivialCounterexampleChecker,
)
from mathgraph.discovery.gap_detector import GapDetector
from mathgraph.discovery.schema import HypothesisCandidate
from tests.fixtures.ablation_harness import AblationHarness


def test_verifier_initialization_and_validation():
    dag = nx.DiGraph([('A', 'B'), ('B', 'C')])
    verifier = HypothesisVerifier(dag)
    assert verifier.get_level('A') == 0
    assert verifier.get_level('B') == 1
    assert verifier.get_level('C') == 2

    cyclic = nx.DiGraph([('A', 'B'), ('B', 'C'), ('C', 'A')])
    with pytest.raises(ValueError):
        HypothesisVerifier(cyclic)


def test_verifier_depth_monotonicity_filter():
    # Two parallel branches:
    # A -> B (levels: A=0, B=1)
    # C -> D (levels: C=0, D=1)
    dag = nx.DiGraph([('A', 'B'), ('C', 'D')])
    verifier = HypothesisVerifier(dag, enforce_depth_monotonicity=True)

    # Valid: level(A)=0 < level(D)=1 (no path exists between them, acyclic)
    valid_cand = HypothesisCandidate('A', 'D', 'missing_prerequisite', 0.9)
    res_valid = verifier.verify_single(valid_cand)
    assert res_valid.accepted is True

    # Invalid due to depth monotonicity: level(B)=1 >= level(C)=0 (no path from C to B, so acyclic, but level(B) >= level(C))
    invalid_cand = HypothesisCandidate('B', 'C', 'missing_prerequisite', 0.8)
    res_invalid = verifier.verify_single(invalid_cand)
    assert res_invalid.accepted is False
    assert 'depth monotonicity' in res_invalid.rejection_reason.lower()

    # Invalid: level(A)=0 == level(A)=0 (self-loop)
    self_loop = HypothesisCandidate('A', 'A', 'missing_prerequisite', 0.5)
    res_self = verifier.verify_single(self_loop)
    assert res_self.accepted is False


def test_verifier_acyclicity_check():
    dag = nx.DiGraph([('A', 'B'), ('B', 'C')])
    # Without depth monotonicity to isolate acyclicity
    verifier = HypothesisVerifier(dag, enforce_depth_monotonicity=False)

    # Adding C -> A would create cycle A -> B -> C -> A
    cycle_cand = HypothesisCandidate('C', 'A', 'missing_prerequisite', 0.9)
    res = verifier.verify_single(cycle_cand)
    assert res.accepted is False
    assert 'acyclicity' in res.rejection_reason.lower()


def test_verifier_pluggable_counterexample_check():
    dag = nx.DiGraph([('A', 'B'), ('B', 'C')])

    # Custom mock LLM checker that flags any candidate involving node 'B'
    def mock_llm_checker(cand: HypothesisCandidate, g: nx.DiGraph):
        if 'B' in (cand.source_node, cand.target_node):
            return True, 'MockLLM: counterexample found in literature'
        return False, None

    verifier = HypothesisVerifier(dag, counterexample_checker=mock_llm_checker, enforce_depth_monotonicity=False)

    cand_with_b = HypothesisCandidate('A', 'B', 'missing_prerequisite', 0.9)
    res_b = verifier.verify_single(cand_with_b)
    assert res_b.accepted is False
    assert 'MockLLM' in res_b.rejection_reason

    cand_without_b = HypothesisCandidate('A', 'C', 'missing_prerequisite', 0.9)
    res_c = verifier.verify_single(cand_without_b)
    assert res_c.accepted is True


def test_acceptance_zero_cycles_when_applying_any_subset_of_accepted_edges():
    """
    Acceptance Criterion:
    Zero cycles introduced when applying any subset of accepted missing_bridge edges.
    """
    harness = AblationHarness(dag_name='judson', n=20, seed=42)
    base_dag = harness.ablated_dag

    detector = GapDetector(base_dag)
    raw_candidates = detector.detect_missing_prerequisite_bridges(top_k=40)

    verifier = HypothesisVerifier(base_dag, enforce_depth_monotonicity=True)
    accepted_candidates = verifier.filter_candidates(raw_candidates)

    assert len(accepted_candidates) > 0, 'Should accept valid candidates'

    # 1. Verify applying ALL accepted edges together produces a valid DAG
    full_augmented = base_dag.copy()
    for cand in accepted_candidates:
        full_augmented.add_edge(cand.source_node, cand.target_node)

    assert nx.is_directed_acyclic_graph(full_augmented), 'Augmented graph with all accepted edges must be a DAG'
    assert len(list(nx.simple_cycles(full_augmented))) == 0

    # 2. Verify all subsets of accepted edges (test up to combinations of size 4 and random subsets)
    for k in range(1, min(5, len(accepted_candidates) + 1)):
        for subset in itertools.combinations(accepted_candidates[:12], k):
            sub_graph = base_dag.copy()
            for cand in subset:
                sub_graph.add_edge(cand.source_node, cand.target_node)
            assert nx.is_directed_acyclic_graph(sub_graph), f'Subset of size {k} introduced a cycle!'
            assert len(list(nx.simple_cycles(sub_graph))) == 0


def test_verify_hypotheses_functional_interface():
    dag = nx.DiGraph([('A', 'B'), ('C', 'D')])
    cands = [
        HypothesisCandidate('A', 'D', 'missing_prerequisite', 0.9),
        HypothesisCandidate('B', 'C', 'missing_prerequisite', 0.8),  # violates depth monotonicity level(B) >= level(C)
        HypothesisCandidate('C', 'B', 'missing_prerequisite', 0.7),  # valid: level(C)=0 < level(B)=1
    ]
    verified = verify_hypotheses(cands, dag)
    edges = [(c.source_node, c.target_node) for c in verified]
    assert ('A', 'D') in edges
    assert ('B', 'C') not in edges
    assert ('C', 'B') in edges
    assert all(c.metadata.get('verified') is True for c in verified)
