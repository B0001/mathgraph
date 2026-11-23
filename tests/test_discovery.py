import pytest
from mathgraph.discovery.schema import HypothesisCandidate
from mathgraph.discovery import (
    AblationHarness,
    build_judson_dag,
    build_virginia_sol_dag,
    mask_prerequisite_edges,
    compute_recall_at_2n,
)


def test_hypothesis_candidate_roundtrip():
    candidate = HypothesisCandidate(
        source_node='algebra_101',
        target_node='linear_algebra',
        hypothesis_type='missing_prerequisite',
        confidence=0.85,
        metadata={'reason': 'topological hole'}
    )
    json_data = candidate.to_json()
    loaded_candidate = HypothesisCandidate.from_json(json_data)

    assert loaded_candidate == candidate
    assert loaded_candidate.source_node == 'algebra_101'
    assert loaded_candidate.target_node == 'linear_algebra'
    assert loaded_candidate.hypothesis_type == 'missing_prerequisite'
    assert loaded_candidate.confidence == 0.85
    assert loaded_candidate.metadata['reason'] == 'topological hole'


def test_discovery_ablation_harness_integration():
    harness = AblationHarness(dag_name='judson', n=20, seed=42)
    assert len(harness.masked_edges) == 20
    candidates = [
        HypothesisCandidate(
            source_node=u,
            target_node=v,
            hypothesis_type='missing_prerequisite',
            confidence=1.0 - (i * 0.01)
        )
        for i, (u, v) in enumerate(harness.masked_edges)
    ]
    recall = harness.evaluate_recall_at_2n(candidates)
    assert recall == 1.0
