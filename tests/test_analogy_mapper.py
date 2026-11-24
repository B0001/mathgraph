import pytest
import networkx as nx

from mathgraph.discovery.analogy_mapper import AnalogyMapper, map_structural_analogies
from mathgraph.discovery.ablation_harness import build_judson_dag


def test_analogy_mapper_initialization():
    dag = nx.DiGraph([('A', 'B'), ('B', 'C')])
    mapper = AnalogyMapper(dag)
    assert mapper.graph is dag

    cyclic = nx.DiGraph([('A', 'B'), ('B', 'C'), ('C', 'A')])
    with pytest.raises(ValueError):
        AnalogyMapper(cyclic)


def test_acceptance_normal_subgroups_ideals_ranks_in_top_5():
    """
    Acceptance Criterion:
    Ranks (Normal Subgroups -> Quotient Groups) <-> (Ideals -> Quotient Rings) in top 5 on Judson graph.
    """
    judson = build_judson_dag()
    mapper = AnalogyMapper(judson, k_hop=1)
    analogies = mapper.map_analogies(top_k=5)
    assert len(analogies) == 5

    target_pairs = [
        (c.metadata['edge_1'], c.metadata['edge_2'])
        for c in analogies
    ]

    target_found = any(
        (e1 == ['normal_subgroups', 'factor_groups'] and e2 == ['ideals', 'factor_rings']) or
        (e2 == ['normal_subgroups', 'factor_groups'] and e1 == ['ideals', 'factor_rings'])
        for e1, e2 in target_pairs
    )

    assert target_found, (
        f'Target analogy (Normal Subgroups -> Quotient Groups) <=> (Ideals -> Quotient Rings) '
        f'not in top 5. Top 5 pairs: {target_pairs}'
    )


def test_analogy_mapper_candidate_structure():
    judson = build_judson_dag()
    analogies = map_structural_analogies(judson, top_k=3)
    assert len(analogies) == 3

    for cand in analogies:
        assert cand.hypothesis_type == 'structural_analogy'
        assert cand.confidence > 0.0
        assert 'wl_similarity' in cand.metadata
        assert 'metadata_similarity' in cand.metadata
        assert cand.metadata['domain_1'] != cand.metadata['domain_2']
