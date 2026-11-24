import pytest
from mathgraph.discovery.schema import HypothesisCandidate
from mathgraph.discovery import (
    AblationHarness,
    build_judson_dag,
    build_virginia_sol_dag,
    mask_prerequisite_edges,
    compute_recall_at_2n,
    GapDetector,
    detect_missing_prerequisite_bridges,
    HypothesisVerifier,
    verify_hypotheses,
    HomologyVoidDetector,
    detect_topological_voids,
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


def test_discovery_pipeline_gap_detection_and_verification():
    harness = AblationHarness(dag_name='judson', n=20, seed=42)
    assert len(harness.masked_edges) == 20
    candidates = detect_missing_prerequisite_bridges(harness.ablated_dag)
    assert len(candidates) > 0
    recall = harness.evaluate_recall_at_2n(candidates)
    assert recall >= 0.60

    verified = verify_hypotheses(candidates, harness.ablated_dag)
    assert len(verified) > 0
    assert all(c.metadata.get('verified') is True for c in verified)


def test_discovery_topological_voids_detection():
    judson = build_judson_dag()
    voids = detect_topological_voids(judson)
    assert len(voids) > 0
    assert all(v.hypothesis_type == 'topological_void' for v in voids)
    assert all('supporting_paths' in v.metadata for v in voids)
