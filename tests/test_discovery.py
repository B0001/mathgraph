import pytest
from mathgraph.discovery.schema import HypothesisCandidate

def test_hypothesis_candidate_roundtrip():
    candidate = HypothesisCandidate(
        source_node="algebra_101",
        target_node="linear_algebra",
        hypothesis_type="missing_prerequisite",
        confidence=0.85,
        metadata={"reason": "topological hole"}
    )
    json_data = candidate.to_json()
    loaded_candidate = HypothesisCandidate.from_json(json_data)
    
    assert loaded_candidate == candidate
    assert loaded_candidate.source_node == "algebra_101"
    assert loaded_candidate.target_node == "linear_algebra"
    assert loaded_candidate.hypothesis_type == "missing_prerequisite"
    assert loaded_candidate.confidence == 0.85
    assert loaded_candidate.metadata["reason"] == "topological hole"
