import json
from pathlib import Path
import pytest
import networkx as nx

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
    AnalogyMapper,
    map_structural_analogies,
    publish_hypotheses,
    run_discovery_pipeline,
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


def test_discovery_structural_analogy_mapping():
    judson = build_judson_dag()
    analogies = map_structural_analogies(judson, top_k=5)
    assert len(analogies) == 5
    assert all(a.hypothesis_type == 'structural_analogy' for a in analogies)


def test_discovery_publish_hypotheses_full_pipeline(tmp_path):
    out_file = tmp_path / 'published_hypotheses.json'
    results = publish_hypotheses(out_path=str(out_file), top_k=30)
    assert len(results) > 0
    assert out_file.exists()

    types = {r['hypothesis_type'] for r in results}
    # Should include multiple hypothesis discovery types
    assert len(types) >= 2
