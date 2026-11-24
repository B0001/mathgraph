import json
from pathlib import Path
import pytest
import networkx as nx

from mathgraph.discovery.publish_hypotheses import publish_hypotheses, main
from mathgraph.discovery.ablation_harness import build_judson_dag


def test_publish_hypotheses_default_dag(tmp_path):
    out_file = tmp_path / 'hypotheses.json'
    records = publish_hypotheses(out_path=str(out_file), top_k=20)

    assert len(records) > 0
    assert out_file.exists()

    with open(out_file, 'r', encoding='utf-8') as f:
        loaded = json.load(f)

    assert len(loaded) == len(records)
    for rec in loaded:
        assert 'source_node' in rec
        assert 'target_node' in rec
        assert 'hypothesis_type' in rec
        assert 'confidence' in rec
        assert 'metadata' in rec


def test_publish_hypotheses_cli(tmp_path):
    out_file = tmp_path / 'cli_hypotheses.json'
    exit_code = main(['--dag', 'judson', '--out', str(out_file), '--top-k', '10'])
    assert exit_code == 0
    assert out_file.exists()

    with open(out_file, 'r', encoding='utf-8') as f:
        loaded = json.load(f)
    assert len(loaded) <= 10
