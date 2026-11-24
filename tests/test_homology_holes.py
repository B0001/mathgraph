import pytest
import networkx as nx

from mathgraph.discovery.homology_holes import HomologyVoidDetector, detect_topological_voids
from mathgraph.discovery.ablation_harness import build_judson_dag


def test_homology_detector_initialization():
    dag = nx.DiGraph([('A', 'B'), ('B', 'C')])
    detector = HomologyVoidDetector(dag)
    assert detector.graph is dag

    cyclic = nx.DiGraph([('A', 'B'), ('B', 'C'), ('C', 'A')])
    with pytest.raises(ValueError):
        HomologyVoidDetector(cyclic)


def test_homology_detector_synthetic_diamond():
    # Diamond:
    # u -> a -> w
    # u -> b -> w
    dag = nx.DiGraph([
        ('u', 'a'), ('u', 'b'),
        ('a', 'w'), ('b', 'w')
    ])
    candidates = detect_topological_voids(dag, distance_threshold=0.3)
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.hypothesis_type == 'topological_void'
    assert 'supporting_paths' in cand.metadata
    paths = cand.metadata['supporting_paths']
    assert len(paths) == 2
    assert ['u', 'a', 'w'] in paths or ['u', 'b', 'w'] in paths
    assert cand.metadata['origin'] == 'u'
    assert cand.metadata['convergence'] == 'w'


def test_homology_detector_closed_diamond_ignored():
    # Diamond with synthesizing cross edge a -> b
    dag = nx.DiGraph([
        ('u', 'a'), ('u', 'b'),
        ('a', 'b'),
        ('a', 'w'), ('b', 'w')
    ])
    candidates = detect_topological_voids(dag, distance_threshold=0.3)
    # Since a -> b directly synthesizes them, no void is emitted
    assert len(candidates) == 0


def test_homology_detector_judson_graph_acceptance():
    """Acceptance test: Emits topological_void candidates with supporting paths on Judson."""
    dag = build_judson_dag()
    candidates = detect_topological_voids(dag)
    assert len(candidates) > 0

    for cand in candidates:
        assert cand.hypothesis_type == 'topological_void'
        assert 'supporting_paths' in cand.metadata
        paths = cand.metadata['supporting_paths']
        assert len(paths) == 2
        for path in paths:
            assert len(path) == 3
            # Verify paths are actual directed paths in the graph
            assert dag.has_edge(path[0], path[1])
            assert dag.has_edge(path[1], path[2])
