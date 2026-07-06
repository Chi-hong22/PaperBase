"""Graph Query Tests

测试图谱查询功能
"""

import pytest
import json
from pathlib import Path
from paperbase.core.graph_query import find_related_papers, find_papers_by_topic


@pytest.fixture
def mock_graph_dir(tmp_path):
    """创建 mock graph 目录和数据"""
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()

    # 创建 mock graph.json
    # 基于 graphify 标准格式：nodes 和 edges
    mock_graph = {
        "nodes": [
            {
                "id": "paper_001",
                "label": "Attention Is All You Need",
                "type": "paper",
                "attributes": {
                    "topics": ["transformer", "attention", "neural_networks"]
                }
            },
            {
                "id": "paper_002",
                "label": "BERT: Pre-training of Deep Bidirectional Transformers",
                "type": "paper",
                "attributes": {
                    "topics": ["transformer", "bert", "pretraining"]
                }
            },
            {
                "id": "paper_003",
                "label": "GPT-3: Language Models are Few-Shot Learners",
                "type": "paper",
                "attributes": {
                    "topics": ["gpt", "language_model", "few_shot"]
                }
            },
            {
                "id": "paper_004",
                "label": "ResNet: Deep Residual Learning",
                "type": "paper",
                "attributes": {
                    "topics": ["cnn", "residual", "computer_vision"]
                }
            },
            {
                "id": "paper_005",
                "label": "Vision Transformer",
                "type": "paper",
                "attributes": {
                    "topics": ["transformer", "computer_vision", "vit"]
                }
            }
        ],
        "edges": [
            {
                "source": "paper_001",
                "target": "paper_002",
                "label": "CITES",
                "confidence": "EXTRACTED"
            },
            {
                "source": "paper_002",
                "target": "paper_003",
                "label": "RELATED_TO",
                "confidence": "INFERRED"
            },
            {
                "source": "paper_001",
                "target": "paper_005",
                "label": "CITES",
                "confidence": "EXTRACTED"
            },
            {
                "source": "paper_004",
                "target": "paper_005",
                "label": "RELATED_TO",
                "confidence": "INFERRED"
            }
        ]
    }

    graph_file = graph_dir / "graph.json"
    graph_file.write_text(json.dumps(mock_graph, indent=2), encoding="utf-8")

    return graph_dir


def test_find_related_papers_depth_1(mock_graph_dir):
    """测试查找直接相关的论文（depth=1）"""
    related = find_related_papers(
        graph_dir=mock_graph_dir,
        paper_id="paper_001",
        depth=1
    )

    # paper_001 直接连接到 paper_002 和 paper_005
    assert isinstance(related, list)
    assert len(related) == 2
    assert "paper_002" in related
    assert "paper_005" in related


def test_find_related_papers_depth_2(mock_graph_dir):
    """测试查找二度相关的论文（depth=2）"""
    related = find_related_papers(
        graph_dir=mock_graph_dir,
        paper_id="paper_001",
        depth=2
    )

    # paper_001 -> paper_002 -> paper_003
    # paper_001 -> paper_005 -> paper_004
    assert isinstance(related, list)
    assert len(related) >= 3  # 至少包括 paper_002, paper_003, paper_005
    assert "paper_002" in related
    assert "paper_003" in related
    assert "paper_005" in related


def test_find_related_papers_nonexistent(mock_graph_dir):
    """测试查找不存在的论文"""
    related = find_related_papers(
        graph_dir=mock_graph_dir,
        paper_id="paper_999",
        depth=1
    )

    assert isinstance(related, list)
    assert len(related) == 0


def test_find_papers_by_topic_single_match(mock_graph_dir):
    """测试按主题查找论文（单个匹配）"""
    papers = find_papers_by_topic(
        graph_dir=mock_graph_dir,
        topic="bert"
    )

    assert isinstance(papers, list)
    assert len(papers) == 1
    assert "paper_002" in papers


def test_find_papers_by_topic_multiple_matches(mock_graph_dir):
    """测试按主题查找论文（多个匹配）"""
    papers = find_papers_by_topic(
        graph_dir=mock_graph_dir,
        topic="transformer"
    )

    assert isinstance(papers, list)
    assert len(papers) == 3
    assert "paper_001" in papers
    assert "paper_002" in papers
    assert "paper_005" in papers


def test_find_papers_by_topic_case_insensitive(mock_graph_dir):
    """测试主题查找大小写不敏感"""
    papers_lower = find_papers_by_topic(
        graph_dir=mock_graph_dir,
        topic="transformer"
    )
    papers_upper = find_papers_by_topic(
        graph_dir=mock_graph_dir,
        topic="TRANSFORMER"
    )

    assert papers_lower == papers_upper


def test_find_papers_by_topic_no_match(mock_graph_dir):
    """测试查找不存在的主题"""
    papers = find_papers_by_topic(
        graph_dir=mock_graph_dir,
        topic="quantum_computing"
    )

    assert isinstance(papers, list)
    assert len(papers) == 0


def test_find_related_papers_no_graph_file(tmp_path):
    """测试 graph.json 不存在的情况"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        find_related_papers(
            graph_dir=empty_dir,
            paper_id="paper_001",
            depth=1
        )


def test_find_papers_by_topic_no_graph_file(tmp_path):
    """测试 graph.json 不存在的情况"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        find_papers_by_topic(
            graph_dir=empty_dir,
            topic="test"
        )
