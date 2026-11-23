# Initialize discovery package
from .schema import HypothesisCandidate
from .ablation_harness import (
    AblationHarness,
    build_judson_dag,
    build_virginia_sol_dag,
    mask_prerequisite_edges,
    compute_recall_at_2n,
)
from .gap_detector import GapDetector, detect_missing_prerequisite_bridges
from .hypothesis_verifier import (
    HypothesisVerifier,
    verify_hypotheses,
    VerificationResult,
    TrivialCounterexampleChecker,
)

__all__ = [
    'HypothesisCandidate',
    'AblationHarness',
    'build_judson_dag',
    'build_virginia_sol_dag',
    'mask_prerequisite_edges',
    'compute_recall_at_2n',
    'GapDetector',
    'detect_missing_prerequisite_bridges',
    'HypothesisVerifier',
    'verify_hypotheses',
    'VerificationResult',
    'TrivialCounterexampleChecker',
]
