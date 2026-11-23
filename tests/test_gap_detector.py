import pytest
import networkx as nx
from mathgraph.discovery.gap_detector import GapDetector, detect_missing_prerequisite_bridges
from mathgraph.discovery.schema import HypothesisCandidate
from tests.fixtures.ablation_harness import AblationHarness, compute_recall_at_2n


def test_gap_detector_initialization():
    # Valid DAG
    dag = nx.DiGraph([('A', 'B'), ('B', 'C')])
    detector = GapDetector(dag)
    assert detector.g_red is not None
    assert detector.g_closure is not None

    # Cyclic graph raises ValueError
    cyclic = nx.DiGraph([('A', 'B'), ('B', 'C'), ('C', 'A')])
    with pytest.raises(ValueError):
        GapDetector(cyclic)


def test_gap_detector_judson_benchmark_recall_at_2n():
    """Acceptance test: Recall@2N >= 0.60 on Judson N=20 ablation benchmark."""
    harness = AblationHarness(dag_name='judson', n=20, seed=42)
    assert len(harness.masked_edges) == 20

    candidates = detect_missing_prerequisite_bridges(harness.ablated_dag)
    assert len(candidates) > 0

    recall = harness.evaluate_recall_at_2n(candidates)
    assert recall >= 0.60, f'Expected Recall@2N >= 0.60 on Judson N=20, got {recall:.4f}'


def test_gap_detector_acyclicity_preservation():
    """Verify that every emitted candidate preserves DAG acyclicity when added."""
    harness = AblationHarness(dag_name='judson', n=20, seed=42)
    candidates = detect_missing_prerequisite_bridges(harness.ablated_dag, top_k=20)

    for cand in candidates:
        assert cand.hypothesis_type == 'missing_prerequisite'
        assert cand.metadata['preserves_acyclicity'] is True

        # Test adding this edge to ablated_dag
        test_graph = harness.ablated_dag.copy()
        test_graph.add_edge(cand.source_node, cand.target_node)
        assert nx.is_directed_acyclic_graph(test_graph), (
            f'Adding candidate ({cand.source_node}, {cand.target_node}) created a cycle!'
        )


def test_gap_detector_synthetic_dag():
    """Test gap detection on a known synthetic DAG with a masked edge."""
    # Diamond with one edge removed:
    # A -> B -> D
    # A -> C -> D
    # Masked: A -> C (so A reaches C only if we recover the edge)
    # Actually let's test: A -> B, A -> C, B -> D, C -> D
    # Remove B -> D:
    # A -> B
    # A -> C -> D
    G = nx.DiGraph([('A', 'B'), ('A', 'C'), ('C', 'D')])
    # B and D have common ancestor A, B and C share parent A
    detector = GapDetector(G, canonical_prior=[('B', 'D')])
    candidates = detector.detect_missing_prerequisite_bridges()

    # B -> D should be among candidates
    edges = [(c.source_node, c.target_node) for c in candidates]
    assert ('B', 'D') in edges

    # Verify candidate properties
    bd_cand = next(c for c in candidates if c.source_node == 'B' and c.target_node == 'D')
    assert bd_cand.confidence > 0.0
    assert 'two_hop_overlap' in bd_cand.metadata


def test_gap_detector_top_k():
    harness = AblationHarness(dag_name='judson', n=20, seed=42)
    candidates = detect_missing_prerequisite_bridges(harness.ablated_dag, top_k=10)
    assert len(candidates) == 10
