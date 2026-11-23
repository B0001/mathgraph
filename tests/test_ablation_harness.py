import pytest
import networkx as nx
from mathgraph.discovery.schema import HypothesisCandidate
from tests.fixtures.ablation_harness import (
    build_judson_dag,
    get_judson_dag,
    build_virginia_sol_dag,
    get_virginia_sol_dag,
    mask_prerequisite_edges,
    compute_recall_at_2n,
    compute_recall_at_k,
    AblationHarness,
)


def test_judson_dag_properties():
    G = build_judson_dag()
    assert isinstance(G, nx.DiGraph)
    assert nx.is_directed_acyclic_graph(G)
    assert nx.is_weakly_connected(G)
    assert G.number_of_nodes() > 50
    assert G.number_of_edges() > 70
    assert 'group_axioms' in G
    assert 'galois_group' in G
    # Alias
    assert get_judson_dag().number_of_edges() == G.number_of_edges()


def test_virginia_sol_dag_properties():
    G = build_virginia_sol_dag()
    assert isinstance(G, nx.DiGraph)
    assert nx.is_directed_acyclic_graph(G)
    assert nx.is_weakly_connected(G)
    assert G.number_of_nodes() > 40
    assert G.number_of_edges() > 60
    assert 'sol6_integers' in G
    assert 'calc_fundamental_theorem_calculus' in G
    # Alias
    assert get_virginia_sol_dag().number_of_edges() == G.number_of_edges()


def test_mask_prerequisite_edges_judson_deterministic():
    G = build_judson_dag()
    N = 20
    G_ablated_1, masked_1 = mask_prerequisite_edges(G, n=N, seed=42)
    G_ablated_2, masked_2 = mask_prerequisite_edges(G, n=N, seed=42)

    assert len(masked_1) == N
    assert len(masked_2) == N
    assert masked_1 == masked_2
    assert set(G_ablated_1.edges()) == set(G_ablated_2.edges())

    # Preserves weak connectivity
    assert nx.is_weakly_connected(G_ablated_1)
    # Preserves DAG property
    assert nx.is_directed_acyclic_graph(G_ablated_1)
    # Original graph is unmodified
    assert G.number_of_edges() == G_ablated_1.number_of_edges() + N


def test_mask_prerequisite_edges_virginia_deterministic():
    G = build_virginia_sol_dag()
    N = 20
    G_ablated_1, masked_1 = mask_prerequisite_edges(G, n=N, seed=42)
    G_ablated_2, masked_2 = mask_prerequisite_edges(G, n=N, seed=42)

    assert len(masked_1) == N
    assert len(masked_2) == N
    assert masked_1 == masked_2
    assert nx.is_weakly_connected(G_ablated_1)
    assert nx.is_directed_acyclic_graph(G_ablated_1)
    assert G.number_of_edges() == G_ablated_1.number_of_edges() + N


def test_mask_different_seeds():
    G = build_judson_dag()
    _, masked_seed_42 = mask_prerequisite_edges(G, n=20, seed=42)
    _, masked_seed_99 = mask_prerequisite_edges(G, n=20, seed=99)

    assert len(masked_seed_42) == 20
    assert len(masked_seed_99) == 20
    # Different seeds yield different masked subsets
    assert masked_seed_42 != masked_seed_99


def test_mask_edge_cases():
    G = build_judson_dag()
    # n = 0
    G_ablated, masked = mask_prerequisite_edges(G, n=0)
    assert len(masked) == 0
    assert G_ablated.number_of_edges() == G.number_of_edges()

    # n < 0
    with pytest.raises(ValueError):
        mask_prerequisite_edges(G, n=-1)

    # Cyclic graph raises ValueError
    G_cyclic = nx.DiGraph([('a', 'b'), ('b', 'c'), ('c', 'a')])
    with pytest.raises(ValueError):
        mask_prerequisite_edges(G_cyclic, n=1)


def test_compute_recall_at_2n():
    masked = [('A', 'B'), ('C', 'D'), ('E', 'F')]
    # Total masked = 3, so 2N = 6

    # 1. Perfect recall within top 2N
    preds_perfect = [
        ('A', 'B'),
        ('X', 'Y'),
        ('C', 'D'),
        ('W', 'Z'),
        ('E', 'F'),
        ('M', 'N'),
        ('Extra', 'Edge'),
    ]
    recall = compute_recall_at_2n(masked, preds_perfect)
    assert recall == 1.0

    # 2. Two out of three in top 6
    preds_partial = [
        ('A', 'B'),
        ('X', 'Y'),
        ('C', 'D'),
        ('W', 'Z'),
        ('M', 'N'),
        ('O', 'P'),
        ('E', 'F'),  # 7th position, beyond top 2N (cutoff=6)
    ]
    recall_partial = compute_recall_at_2n(masked, preds_partial)
    assert pytest.approx(recall_partial) == 2.0 / 3.0

    # 3. With HypothesisCandidate objects
    candidates = [
        HypothesisCandidate(source_node='A', target_node='B', hypothesis_type='missing_prerequisite', confidence=0.9),
        HypothesisCandidate(source_node='X', target_node='Y', hypothesis_type='missing_prerequisite', confidence=0.8),
        HypothesisCandidate(source_node='C', target_node='D', hypothesis_type='missing_prerequisite', confidence=0.7),
    ]
    recall_candidates = compute_recall_at_2n(masked, candidates)
    assert pytest.approx(recall_candidates) == 2.0 / 3.0

    # 4. Zero recall
    recall_zero = compute_recall_at_2n(masked, [('Foo', 'Bar'), ('Baz', 'Qux')])
    assert recall_zero == 0.0

    # 5. Empty masked list
    assert compute_recall_at_2n([], preds_perfect) == 1.0


def test_ablation_harness_class():
    harness_judson = AblationHarness(dag_name='judson', n=20, seed=42)
    assert harness_judson.n == 20
    assert len(harness_judson.masked_edges) == 20
    assert nx.is_weakly_connected(harness_judson.ablated_dag)
    assert nx.is_directed_acyclic_graph(harness_judson.ablated_dag)

    # Evaluate predictions directly on harness
    score = harness_judson.evaluate_recall_at_2n(harness_judson.masked_edges)
    assert score == 1.0

    # Test Virginia SOL harness
    harness_virginia = AblationHarness(dag_name='virginia_sol', n=20, seed=42)
    assert harness_virginia.n == 20
    assert len(harness_virginia.masked_edges) == 20
    assert nx.is_weakly_connected(harness_virginia.ablated_dag)

    # Test invalid dag name
    with pytest.raises(ValueError):
        AblationHarness(dag_name='nonexistent_dag')
