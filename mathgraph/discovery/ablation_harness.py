"""
Re-export ablation harness components for mathgraph.discovery.
"""

import sys
from pathlib import Path

# Ensure root tests directory is importable
repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from tests.fixtures.ablation_harness import (
    build_judson_dag,
    get_judson_dag,
    build_virginia_sol_dag,
    get_virginia_sol_dag,
    mask_prerequisite_edges,
    compute_recall_at_2n,
    compute_recall_at_k,
    AblationHarness,
    JUDSON_EDGES,
    VIRGINIA_SOL_EDGES,
)

__all__ = [
    'build_judson_dag',
    'get_judson_dag',
    'build_virginia_sol_dag',
    'get_virginia_sol_dag',
    'mask_prerequisite_edges',
    'compute_recall_at_2n',
    'compute_recall_at_k',
    'AblationHarness',
    'JUDSON_EDGES',
    'VIRGINIA_SOL_EDGES',
]
