"""
Ablation benchmark harness for graph-level hypothesis generation and gap detection.
Provides canonical Judson Abstract Algebra and Virginia SOL prerequisite DAGs,
deterministic seeded edge masking with weak connectivity preservation,
and Recall@2N evaluation.
"""

import random
from typing import Any, Collection, Dict, List, Optional, Sequence, Set, Tuple
import networkx as nx

# -----------------------------------------------------------------------------
# Canonical Judson Abstract Algebra DAG
# -----------------------------------------------------------------------------

JUDSON_EDGES: List[Tuple[str, str]] = [
    # Preliminaries
    ('sets', 'relations'),
    ('sets', 'functions'),
    ('relations', 'equivalence_relations'),
    ('functions', 'permutations'),
    ('integers_divisibility', 'modular_arithmetic'),
    ('induction', 'integers_divisibility'),
    ('integers_divisibility', 'gcd_euclidean_algorithm'),
    ('gcd_euclidean_algorithm', 'modular_arithmetic'),
    # Groups intro
    ('symmetries', 'group_axioms'),
    ('modular_arithmetic', 'group_axioms'),
    ('group_axioms', 'abelian_groups'),
    ('group_axioms', 'order_of_elements'),
    ('group_axioms', 'subgroup_criterion'),
    ('subgroup_criterion', 'cyclic_subgroups'),
    ('subgroup_criterion', 'center_of_group'),
    # Cyclic groups
    ('order_of_elements', 'cyclic_groups'),
    ('cyclic_subgroups', 'cyclic_groups'),
    ('modular_arithmetic', 'cyclic_groups'),
    ('cyclic_groups', 'generators'),
    ('cyclic_groups', 'classification_cyclic'),
    # Permutation groups
    ('permutations', 'cycle_notation'),
    ('cycle_notation', 'symmetric_group'),
    ('symmetric_group', 'alternating_group'),
    ('permutations', 'transpositions_parity'),
    ('transpositions_parity', 'alternating_group'),
    ('group_axioms', 'symmetric_group'),
    # Cosets and Lagrange
    ('subgroup_criterion', 'cosets'),
    ('equivalence_relations', 'cosets'),
    ('cosets', 'lagrange_theorem'),
    ('order_of_elements', 'lagrange_theorem'),
    ('lagrange_theorem', 'index_of_subgroup'),
    ('lagrange_theorem', 'fermats_little_theorem'),
    # Normal subgroups and quotients
    ('cosets', 'normal_subgroups'),
    ('normal_subgroups', 'factor_groups'),
    ('normal_subgroups', 'simple_groups'),
    ('lagrange_theorem', 'simple_groups'),
    # Homomorphisms and isomorphisms
    ('group_axioms', 'group_homomorphisms'),
    ('group_homomorphisms', 'kernel_and_image'),
    ('normal_subgroups', 'kernel_and_image'),
    ('factor_groups', 'first_isomorphism_theorem'),
    ('kernel_and_image', 'first_isomorphism_theorem'),
    ('first_isomorphism_theorem', 'second_third_isomorphism_theorems'),
    # Direct products
    ('abelian_groups', 'external_direct_products'),
    ('external_direct_products', 'internal_direct_products'),
    ('cyclic_groups', 'fundamental_theorem_abelian_groups'),
    ('external_direct_products', 'fundamental_theorem_abelian_groups'),
    # Group actions and Sylow
    ('group_axioms', 'group_actions'),
    ('group_actions', 'orbits_and_stabilizers'),
    ('orbits_and_stabilizers', 'orbit_stabilizer_theorem'),
    ('lagrange_theorem', 'orbit_stabilizer_theorem'),
    ('orbit_stabilizer_theorem', 'cauchy_theorem'),
    ('cauchy_theorem', 'sylow_theorems'),
    ('lagrange_theorem', 'sylow_theorems'),
    # Rings
    ('group_axioms', 'ring_axioms'),
    ('abelian_groups', 'ring_axioms'),
    ('ring_axioms', 'commutative_rings'),
    ('commutative_rings', 'integral_domains'),
    ('ring_axioms', 'characteristic_of_ring'),
    # Ideals and factor rings
    ('ring_axioms', 'ideals'),
    ('subgroup_criterion', 'ideals'),
    ('ideals', 'factor_rings'),
    ('factor_groups', 'factor_rings'),
    ('ideals', 'principal_ideals'),
    ('factor_rings', 'maximal_ideals'),
    ('factor_rings', 'prime_ideals'),
    ('integral_domains', 'prime_ideals'),
    # Ring homomorphisms
    ('ring_axioms', 'ring_homomorphisms'),
    ('group_homomorphisms', 'ring_homomorphisms'),
    ('ideals', 'ring_homomorphisms'),
    ('ring_homomorphisms', 'ring_isomorphism_theorems'),
    ('first_isomorphism_theorem', 'ring_isomorphism_theorems'),
    ('integral_domains', 'fraction_fields'),
    # Polynomial rings
    ('ring_axioms', 'polynomial_rings'),
    ('polynomial_rings', 'polynomial_division'),
    ('polynomial_division', 'irreducible_polynomials'),
    ('integral_domains', 'unique_factorization_domains'),
    ('principal_ideals', 'principal_ideal_domains'),
    ('unique_factorization_domains', 'euclidean_domains'),
    ('principal_ideal_domains', 'euclidean_domains'),
    ('irreducible_polynomials', 'unique_factorization_domains'),
    # Vector spaces and fields
    ('group_axioms', 'vector_spaces'),
    ('abelian_groups', 'vector_spaces'),
    ('vector_spaces', 'basis_and_dimension'),
    ('ring_axioms', 'fields_def'),
    ('integral_domains', 'fields_def'),
    ('fields_def', 'field_extensions'),
    ('basis_and_dimension', 'field_extensions'),
    ('field_extensions', 'algebraic_extensions'),
    ('irreducible_polynomials', 'algebraic_extensions'),
    ('algebraic_extensions', 'minimal_polynomials'),
    ('field_extensions', 'finite_fields'),
    ('classification_cyclic', 'finite_fields'),
    # Galois theory
    ('algebraic_extensions', 'splitting_fields'),
    ('splitting_fields', 'separable_extensions'),
    ('group_axioms', 'automorphism_groups'),
    ('splitting_fields', 'galois_group'),
    ('automorphism_groups', 'galois_group'),
    ('galois_group', 'fundamental_theorem_galois_theory'),
    ('field_extensions', 'fundamental_theorem_galois_theory'),
    ('fundamental_theorem_galois_theory', 'solvability_by_radicals'),
    ('symmetric_group', 'insolvability_of_quintic'),
    ('simple_groups', 'insolvability_of_quintic'),
    ('solvability_by_radicals', 'insolvability_of_quintic')
]

# -----------------------------------------------------------------------------
# Canonical Virginia SOL Mathematics DAG
# -----------------------------------------------------------------------------

VIRGINIA_SOL_EDGES: List[Tuple[str, str]] = [
    # Grade 6
    ('sol6_ratios', 'sol6_proportions_intro'),
    ('sol6_fractions_decimals', 'sol6_rational_conversions'),
    ('sol6_integers', 'sol6_absolute_value'),
    ('sol6_integers', 'sol6_coordinate_plane'),
    ('sol6_one_step_equations', 'sol7_two_step_equations'),
    ('sol6_rational_conversions', 'sol7_rational_operations'),
    ('sol6_proportions_intro', 'sol7_proportions'),
    ('sol6_circle_measurements', 'sol7_surface_area_volume'),
    ('sol6_fractions_decimals', 'sol6_integers'),
    ('sol6_integers', 'sol6_one_step_equations'),
    ('sol6_circle_measurements', 'sol6_integers'),
    ('sol6_fractions_decimals', 'sol7_rational_operations'),
    ('sol6_ratios', 'sol7_proportions'),
    ('sol6_one_step_equations', 'sol7_linear_inequalities'),
    # Grade 7
    ('sol7_proportions', 'sol7_slope_rate_of_change'),
    ('sol7_rational_operations', 'sol7_two_step_equations'),
    ('sol7_two_step_equations', 'sol7_linear_inequalities'),
    ('sol7_surface_area_volume', 'sol8_volume_surface_area_solids'),
    ('sol7_slope_rate_of_change', 'sol8_linear_functions'),
    ('sol7_linear_inequalities', 'sol8_multistep_equations'),
    ('sol7_rational_operations', 'sol8_real_numbers'),
    ('sol7_slope_rate_of_change', 'alg1_slope_linear_graphs'),
    ('sol7_proportions', 'geom_triangle_similarity'),
    # Grade 8
    ('sol8_real_numbers', 'sol8_scientific_notation'),
    ('sol8_real_numbers', 'sol8_pythagorean_theorem'),
    ('sol8_multistep_equations', 'sol8_linear_functions'),
    ('sol8_linear_functions', 'alg1_slope_linear_graphs'),
    ('sol8_multistep_equations', 'alg1_equations_inequalities'),
    ('sol8_pythagorean_theorem', 'geom_right_triangle_trigonometry'),
    ('sol8_pythagorean_theorem', 'geom_coordinate_transformations'),
    ('sol8_congruence_transformations', 'geom_triangle_congruence'),
    ('sol8_linear_functions', 'alg1_systems_linear_equations'),
    ('sol8_pythagorean_theorem', 'geom_triangle_similarity'),
    # Algebra I
    ('alg1_equations_inequalities', 'alg1_systems_linear_equations'),
    ('alg1_slope_linear_graphs', 'alg1_systems_linear_equations'),
    ('alg1_slope_linear_graphs', 'alg1_domain_range_relations'),
    ('alg1_equations_inequalities', 'alg1_literal_equations'),
    ('alg1_literal_equations', 'alg1_polynomial_operations'),
    ('alg1_polynomial_operations', 'alg1_factoring_quadratics'),
    ('alg1_factoring_quadratics', 'alg1_quadratic_equations'),
    ('sol8_real_numbers', 'alg1_radicals_exponents'),
    ('alg1_radicals_exponents', 'alg1_quadratic_equations'),
    ('alg1_domain_range_relations', 'alg1_quadratic_functions'),
    ('alg1_quadratic_equations', 'alg1_quadratic_functions'),
    ('alg1_slope_linear_graphs', 'alg1_quadratic_functions'),
    ('alg1_factoring_quadratics', 'alg2_rational_functions'),
    ('alg1_radicals_exponents', 'alg2_exponential_logarithmic'),
    # Geometry
    ('geom_reasoning_proofs', 'geom_parallel_transversals'),
    ('geom_parallel_transversals', 'geom_triangle_congruence'),
    ('geom_triangle_congruence', 'geom_triangle_similarity'),
    ('geom_triangle_similarity', 'geom_right_triangle_trigonometry'),
    ('geom_triangle_congruence', 'geom_quadrilaterals'),
    ('geom_triangle_similarity', 'geom_circles_angles_arcs'),
    ('geom_coordinate_transformations', 'geom_coordinate_proofs'),
    ('geom_quadrilaterals', 'geom_coordinate_proofs'),
    ('geom_reasoning_proofs', 'sol8_congruence_transformations'),
    ('alg1_quadratic_functions', 'geom_coordinate_transformations'),
    ('geom_triangle_congruence', 'geom_coordinate_proofs'),
    ('geom_right_triangle_trigonometry', 'trig_circular_functions'),
    ('geom_circles_angles_arcs', 'trig_unit_circle_definitions'),
    # Algebra II
    ('alg1_quadratic_equations', 'alg2_complex_numbers'),
    ('alg1_polynomial_operations', 'alg2_polynomial_functions'),
    ('alg1_factoring_quadratics', 'alg2_polynomial_functions'),
    ('alg1_domain_range_relations', 'alg2_rational_functions'),
    ('alg1_polynomial_operations', 'alg2_rational_functions'),
    ('alg1_radicals_exponents', 'alg2_radical_equations'),
    ('alg1_quadratic_functions', 'alg2_nonlinear_systems'),
    ('alg1_domain_range_relations', 'alg2_exponential_logarithmic'),
    ('alg2_polynomial_functions', 'alg2_sequences_series'),
    ('sol8_real_numbers', 'alg2_complex_numbers'),
    ('alg2_complex_numbers', 'anal_polar_parametric'),
    # Trigonometry & Math Analysis
    ('geom_right_triangle_trigonometry', 'trig_unit_circle_definitions'),
    ('trig_unit_circle_definitions', 'trig_circular_functions'),
    ('trig_circular_functions', 'trig_identities_equations'),
    ('geom_triangle_similarity', 'trig_law_sines_cosines'),
    ('trig_identities_equations', 'trig_law_sines_cosines'),
    ('alg2_exponential_logarithmic', 'anal_polar_parametric'),
    ('trig_circular_functions', 'anal_polar_parametric'),
    ('alg2_sequences_series', 'anal_limits_continuity'),
    ('alg2_rational_functions', 'anal_limits_continuity'),
    ('alg1_domain_range_relations', 'trig_circular_functions'),
    ('geom_right_triangle_trigonometry', 'trig_identities_equations'),
    # Calculus
    ('anal_limits_continuity', 'calc_derivative_definition'),
    ('calc_derivative_definition', 'calc_differentiation_rules'),
    ('calc_differentiation_rules', 'calc_applications_derivatives'),
    ('calc_derivative_definition', 'calc_definite_integrals'),
    ('calc_differentiation_rules', 'calc_fundamental_theorem_calculus'),
    ('calc_definite_integrals', 'calc_fundamental_theorem_calculus'),
    ('alg2_polynomial_functions', 'calc_derivative_definition'),
    ('alg2_exponential_logarithmic', 'calc_derivative_definition'),
    ('alg2_sequences_series', 'calc_definite_integrals')
]


def build_judson_dag() -> nx.DiGraph:
    """Construct and return the canonical Judson Abstract Algebra prerequisite DAG."""
    G = nx.DiGraph()
    G.name = 'judson_abstract_algebra'
    for u, v in JUDSON_EDGES:
        G.add_edge(u, v)
    return G


def get_judson_dag() -> nx.DiGraph:
    """Alias for build_judson_dag."""
    return build_judson_dag()


def build_virginia_sol_dag() -> nx.DiGraph:
    """Construct and return the canonical Virginia SOL Mathematics prerequisite DAG."""
    G = nx.DiGraph()
    G.name = 'virginia_sol_mathematics'
    for u, v in VIRGINIA_SOL_EDGES:
        G.add_edge(u, v)
    return G


def get_virginia_sol_dag() -> nx.DiGraph:
    """Alias for build_virginia_sol_dag."""
    return build_virginia_sol_dag()


# -----------------------------------------------------------------------------
# Edge Normalization and Masking
# -----------------------------------------------------------------------------

def _normalize_edge(edge: Any) -> Tuple[str, str]:
    """Extract (source, target) string tuple from various candidate representations."""
    if hasattr(edge, 'source_node') and hasattr(edge, 'target_node'):
        return (str(edge.source_node), str(edge.target_node))
    if isinstance(edge, (list, tuple)) and len(edge) >= 2:
        return (str(edge[0]), str(edge[1]))
    if isinstance(edge, dict) and 'source_node' in edge and 'target_node' in edge:
        return (str(edge['source_node']), str(edge['target_node']))
    raise TypeError(f'Cannot normalize edge of type {type(edge)}: {edge}')


def mask_prerequisite_edges(
    G: nx.DiGraph,
    n: int = 20,
    seed: int = 42
) -> Tuple[nx.DiGraph, List[Tuple[str, str]]]:
    """
    Deterministically mask n prerequisite edges from DAG G while preserving weak connectivity.

    Args:
        G: Input directed acyclic graph.
        n: Number of edges to mask.
        seed: Random seed for deterministic selection.

    Returns:
        (G_masked, masked_edges) where G_masked is a copy of G with n edges removed,
        and masked_edges is the list of (u, v) tuples removed.
    """
    if not nx.is_directed_acyclic_graph(G):
        raise ValueError('Input graph G must be a directed acyclic graph (DAG)')
    if not nx.is_weakly_connected(G):
        raise ValueError('Input graph G must be weakly connected')
    if n < 0:
        raise ValueError('n must be non-negative')
    if n == 0:
        return G.copy(), []

    rng = random.Random(seed)
    G_masked = G.copy()

    # Deterministic sorting before shuffle guarantees cross-platform reproducibility
    candidates = sorted(list(G_masked.edges()), key=lambda e: (str(e[0]), str(e[1])))
    rng.shuffle(candidates)

    masked: List[Tuple[str, str]] = []
    for u, v in candidates:
        if len(masked) >= n:
            break
        G_masked.remove_edge(u, v)
        if nx.is_weakly_connected(G_masked):
            masked.append((str(u), str(v)))
        else:
            # Backtrack if removing this edge disconnects the graph
            G_masked.add_edge(u, v)

    if len(masked) < n:
        raise ValueError(
            f'Could only mask {len(masked)} edges while preserving weak connectivity (requested {n})'
        )
    return G_masked, masked


# -----------------------------------------------------------------------------
# Evaluation: Recall@2N
# -----------------------------------------------------------------------------

def compute_recall_at_2n(
    masked_edges: Sequence[Any],
    predictions: Sequence[Any],
    k: Optional[int] = None
) -> float:
    """
    Compute Recall@2N (or Recall@K if k specified) for ranked predictions against masked edges.

    Args:
        masked_edges: Ground truth masked edges.
        predictions: Ranked sequence of predicted edges / HypothesisCandidate objects.
        k: Optional evaluation depth cutoff. Defaults to 2 * len(masked_edges).

    Returns:
        Recall score in [0.0, 1.0].
    """
    if not masked_edges:
        return 1.0

    target_k = 2 * len(masked_edges) if k is None else k
    masked_set: Set[Tuple[str, str]] = {_normalize_edge(e) for e in masked_edges}
    top_k_preds: Set[Tuple[str, str]] = {_normalize_edge(e) for e in predictions[:target_k]}

    hits = len(masked_set & top_k_preds)
    return float(hits / len(masked_set))


def compute_recall_at_k(
    masked_edges: Sequence[Any],
    predictions: Sequence[Any],
    k: int
) -> float:
    """Alias for compute_recall_at_2n with explicit k."""
    return compute_recall_at_2n(masked_edges, predictions, k=k)


# -----------------------------------------------------------------------------
# Ablation Benchmark Harness Class
# -----------------------------------------------------------------------------

class AblationHarness:
    """
    Benchmark harness managing DAG retrieval, edge masking, and Recall evaluation.
    """

    def __init__(
        self,
        dag: Optional[nx.DiGraph] = None,
        dag_name: str = 'judson',
        n: int = 20,
        seed: int = 42
    ):
        if dag is not None:
            self.original_dag = dag.copy()
            self.dag_name = getattr(dag, 'name', 'custom')
        elif dag_name.lower() in ('judson', 'abstract_algebra'):
            self.original_dag = build_judson_dag()
            self.dag_name = 'judson'
        elif dag_name.lower() in ('virginia', 'virginia_sol', 'sol'):
            self.original_dag = build_virginia_sol_dag()
            self.dag_name = 'virginia_sol'
        else:
            raise ValueError(f'Unknown DAG name: {dag_name}. Expected judson or virginia_sol.')

        self.n = n
        self.seed = seed
        self.ablated_dag, self.masked_edges = mask_prerequisite_edges(
            self.original_dag, n=n, seed=seed
        )

    def evaluate_recall_at_2n(self, predictions: Sequence[Any]) -> float:
        """Evaluate Recall@2N against the harness masked edges."""
        return compute_recall_at_2n(self.masked_edges, predictions, k=2 * self.n)

    def evaluate_recall(self, predictions: Sequence[Any], k: Optional[int] = None) -> float:
        """Evaluate Recall@K (default K=2N)."""
        return compute_recall_at_2n(self.masked_edges, predictions, k=k)
