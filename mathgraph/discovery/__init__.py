# Initialize discovery package
from .schema import HypothesisCandidate
from .ablation_harness import (
    AblationHarness,
    build_judson_dag,
    build_virginia_sol_dag,
    mask_prerequisite_edges,
    compute_recall_at_2n,
)

__all__ = [
    'HypothesisCandidate',
    'AblationHarness',
    'build_judson_dag',
    'build_virginia_sol_dag',
    'mask_prerequisite_edges',
    'compute_recall_at_2n',
]
