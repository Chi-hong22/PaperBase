# tests/unit/test_graphify_stats.py
import pytest
import json
from pathlib import Path
from paperbase.adapters.graphify_adapter import get_graph_stats


def test_get_graph_stats_empty_directory(tmp_path):
    """空目录应该返回空统计"""
    stats = get_graph_stats(tmp_path)

    assert stats["files"] == []
    assert stats["nodes"] == 0
    assert stats["edges"] == 0


def test_get_graph_stats_no_graph_json(tmp_path):
    """没有 graph.json 时应该返回 0 节点/边"""
    # 创建其他文件
    (tmp_path / "other.txt").write_text("test")

    stats = get_graph_stats(tmp_path)

    assert stats["nodes"] == 0
    assert stats["edges"] == 0
    assert "other.txt" in stats["files"]


def test_get_graph_stats_with_graph_json(tmp_path):
    """有 graph.json 时应该返回真实统计"""
    graph_data = {
        "nodes": [
            {"id": "paper1", "type": "Paper"},
            {"id": "paper2", "type": "Paper"},
            {"id": "method1", "type": "Method"}
        ],
        "edges": [
            {"source": "paper1", "target": "method1", "relation": "uses"},
            {"source": "paper2", "target": "method1", "relation": "uses"}
        ]
    }

    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps(graph_data), encoding="utf-8")

    stats = get_graph_stats(tmp_path)

    assert stats["nodes"] == 3
    assert stats["edges"] == 2
    assert "graph.json" in stats["files"]


def test_get_graph_stats_supports_node_link_schema(tmp_path):
    graph_data = {
        "nodes": [{"id": "paper1"}, {"id": "paper2"}],
        "links": [{"source": "paper1", "target": "paper2"}],
    }
    (tmp_path / "graph.json").write_text(json.dumps(graph_data), encoding="utf-8")

    stats = get_graph_stats(tmp_path)

    assert stats["nodes"] == 2
    assert stats["edges"] == 1


def test_get_graph_stats_invalid_json(tmp_path):
    """无效 JSON 应该返回 0 节点/边（优雅降级）"""
    graph_file = tmp_path / "graph.json"
    graph_file.write_text("invalid json{", encoding="utf-8")

    stats = get_graph_stats(tmp_path)

    assert stats["nodes"] == 0
    assert stats["edges"] == 0


def test_get_graph_stats_missing_keys(tmp_path):
    """缺少 nodes/edges 键应该返回 0"""
    graph_data = {"other_field": "value"}

    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps(graph_data), encoding="utf-8")

    stats = get_graph_stats(tmp_path)

    assert stats["nodes"] == 0
    assert stats["edges"] == 0
