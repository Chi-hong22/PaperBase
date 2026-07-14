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
    # 基于 Graphify/NetworkX node-link 标准格式
    mock_graph = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {
                "id": "p_001_paper",
                "label": "Attention Is All You Need",
                "norm_label": "attention is all you need",
                "file_type": "paper",
            },
            {
                "id": "p_002_paper",
                "label": "BERT: Pre-training of Deep Bidirectional Transformers",
                "norm_label": "bert: pre-training of deep bidirectional transformers",
                "file_type": "paper",
            },
            {
                "id": "p_003_paper",
                "label": "GPT-3: Language Models are Few-Shot Learners",
                "norm_label": "gpt-3: language models are few-shot learners",
                "file_type": "paper",
            },
            {
                "id": "p_004_paper",
                "label": "ResNet: Deep Residual Learning",
                "norm_label": "resnet: deep residual learning",
                "file_type": "paper",
            },
            {
                "id": "p_005_paper",
                "label": "Vision Transformer",
                "norm_label": "vision transformer",
                "file_type": "paper",
            }
        ],
        "links": [
            {
                "source": "p_001_paper",
                "target": "p_002_paper",
                "label": "CITES",
                "confidence": "EXTRACTED"
            },
            {
                "source": "p_002_paper",
                "target": "p_003_paper",
                "label": "RELATED_TO",
                "confidence": "INFERRED"
            },
            {
                "source": "p_001_paper",
                "target": "p_005_paper",
                "label": "CITES",
                "confidence": "EXTRACTED"
            },
            {
                "source": "p_004_paper",
                "target": "p_005_paper",
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
        paper_id="p_001_paper",
        depth=1
    )

    # p_001_paper 直接连接到 p_002_paper 和 p_005_paper
    assert isinstance(related, list)
    assert len(related) == 2
    assert "p_002_paper" in related
    assert "p_005_paper" in related


def test_find_related_papers_depth_2(mock_graph_dir):
    """测试查找二度相关的论文（depth=2）"""
    related = find_related_papers(
        graph_dir=mock_graph_dir,
        paper_id="p_001_paper",
        depth=2
    )

    # p_001_paper -> p_002_paper -> p_003_paper
    # p_001_paper -> p_005_paper -> p_004_paper
    assert isinstance(related, list)
    assert len(related) >= 3
    assert "p_002_paper" in related
    assert "p_003_paper" in related
    assert "p_005_paper" in related


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
    assert "p_002_paper" in papers


def test_find_papers_by_topic_multiple_matches(mock_graph_dir):
    """测试按主题查找论文（多个匹配）"""
    papers = find_papers_by_topic(
        graph_dir=mock_graph_dir,
        topic="transformer"
    )

    assert isinstance(papers, list)
    assert len(papers) == 2
    assert "p_002_paper" in papers
    assert "p_005_paper" in papers


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
            paper_id="p_001_paper",
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
