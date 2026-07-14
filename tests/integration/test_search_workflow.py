"""搜索和查询工作流集成测试"""

import pytest
import json
import sqlite3
from pathlib import Path
from paperbase.core.search_engine import SearchEngine
from paperbase.core.graph_query import find_related_papers, find_papers_by_topic
from paperbase.core.registry import PaperRegistry


@pytest.fixture
def temp_workspace(tmp_path):
    """创建临时工作空间"""
    # 创建目录结构
    library_path = tmp_path / "library" / "papers"
    index_path = tmp_path / "index"
    registry_path = tmp_path / "registry"
    graph_path = tmp_path / "graph"

    library_path.mkdir(parents=True)
    index_path.mkdir(parents=True)
    registry_path.mkdir(parents=True)
    graph_path.mkdir(parents=True)

    return {
        "base": tmp_path,
        "library": library_path,
        "index": index_path / "fts.db",
        "registry": registry_path / "papers.db",
        "graph": graph_path
    }


@pytest.fixture
def sample_papers(temp_workspace):
    """创建示例论文数据"""
    library_path = temp_workspace["library"]
    registry_path = temp_workspace["registry"]

    # 创建示例论文
    papers = [
        {
            "paper_id": "paper001",
            "title": "Introduction to Machine Learning",
            "authors": "John Doe, Jane Smith",
            "year": 2020,
            "chunks": [
                {"id": "chunk001", "content": "Machine learning is a subset of artificial intelligence.", "position": 0},
                {"id": "chunk002", "content": "Supervised learning uses labeled training data.", "position": 1},
            ]
        },
        {
            "paper_id": "paper002",
            "title": "Deep Learning Foundations",
            "authors": "Alice Johnson",
            "year": 2021,
            "chunks": [
                {"id": "chunk003", "content": "Neural networks are the foundation of deep learning.", "position": 0},
                {"id": "chunk004", "content": "Backpropagation is used to train neural networks.", "position": 1},
            ]
        },
        {
            "paper_id": "paper003",
            "title": "Natural Language Processing",
            "authors": "Bob Wilson",
            "year": 2022,
            "chunks": [
                {"id": "chunk005", "content": "NLP enables computers to understand human language.", "position": 0},
                {"id": "chunk006", "content": "Transformers revolutionized natural language processing.", "position": 1},
            ]
        }
    ]

    # 写入 chunks.jsonl 文件
    for paper in papers:
        paper_dir = library_path / paper["paper_id"]
        paper_dir.mkdir()

        chunks_file = paper_dir / "chunks.jsonl"
        with open(chunks_file, "w", encoding="utf-8") as f:
            for chunk in paper["chunks"]:
                chunk_data = {
                    "id": chunk["id"],
                    "paper_id": paper["paper_id"],
                    "content": chunk["content"],
                    "position": chunk["position"]
                }
                f.write(json.dumps(chunk_data) + "\n")

    # 初始化 registry
    from paperbase.schemas.manifest import PaperState

    registry = PaperRegistry(registry_path)
    for paper in papers:
        registry.register_paper(
            paper_id=paper["paper_id"],
            storage_id=f"p_{paper['paper_id'][-3:]}",
            state=PaperState.READY,
            title=paper["title"],
            authors=paper["authors"].split(", "),
            year=paper["year"]
        )
    registry.close()

    return papers


@pytest.fixture
def sample_graph(temp_workspace):
    """创建示例图谱数据"""
    graph_path = temp_workspace["graph"]

    graph_data = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {
                "id": "p_001_paper",
                "label": "Introduction to Machine Learning",
                "norm_label": "introduction to machine learning",
                "file_type": "paper",
            },
            {
                "id": "p_002_paper",
                "label": "Deep Learning Foundations",
                "norm_label": "deep learning foundations",
                "file_type": "paper",
            },
            {
                "id": "p_003_paper",
                "label": "Natural Language Processing",
                "norm_label": "natural language processing",
                "file_type": "paper",
            }
        ],
        "links": [
            {"source": "p_001_paper", "target": "p_002_paper", "type": "cites"},
            {"source": "p_002_paper", "target": "p_003_paper", "type": "related"}
        ]
    }

    graph_file = graph_path / "graph.json"
    with open(graph_file, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2)

    return graph_data


def test_search_engine_build_index(temp_workspace, sample_papers):
    """测试搜索引擎索引构建"""
    engine = SearchEngine(temp_workspace["index"], temp_workspace["library"])
    engine.build_index()

    # 验证索引已创建
    assert temp_workspace["index"].exists()

    # 验证 FTS5 表已创建
    conn = sqlite3.connect(temp_workspace["index"])
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'")
    result = cursor.fetchone()
    conn.close()

    assert result is not None

    engine.close()


def test_search_engine_fulltext_search(temp_workspace, sample_papers):
    """测试全文检索功能"""
    engine = SearchEngine(temp_workspace["index"], temp_workspace["library"])
    engine.build_index()

    # 搜索 "machine learning"
    results = engine.search("machine learning", limit=5)

    assert len(results) > 0
    assert results[0]["paper_id"] == "paper001"
    assert "score" in results[0]
    assert "snippet" in results[0]
    assert results[0]["score"] > 0

    engine.close()


def test_search_engine_no_results(temp_workspace, sample_papers):
    """测试搜索无结果的情况"""
    engine = SearchEngine(temp_workspace["index"], temp_workspace["library"])
    engine.build_index()

    # 搜索不存在的内容
    results = engine.search("quantum computing", limit=5)

    assert len(results) == 0

    engine.close()


def test_search_engine_limit(temp_workspace, sample_papers):
    """测试搜索结果数量限制"""
    engine = SearchEngine(temp_workspace["index"], temp_workspace["library"])
    engine.build_index()

    # 搜索 "learning"，应该匹配多个结果
    results = engine.search("learning", limit=2)

    assert len(results) <= 2

    engine.close()


def test_search_engine_deduplicates_chunks_by_paper(temp_workspace, sample_papers):
    """同一论文命中多个分块时只返回一次论文结果。"""
    engine = SearchEngine(temp_workspace["index"], temp_workspace["library"])
    engine.build_index()

    results = engine.search("learning", limit=10)

    assert [result["paper_id"] for result in results] == ["paper001", "paper002"]
    engine.close()


def test_search_limit_is_applied_after_metadata_filter(temp_workspace, sample_papers):
    """元数据过滤必须发生在最终结果数量截断之前。"""
    engine = SearchEngine(temp_workspace["index"], temp_workspace["library"])
    engine.build_index()

    results = engine.search("learning", limit=1, year_range=(2021, 2021))

    assert [result["paper_id"] for result in results] == ["paper002"]
    engine.close()


def test_search_engine_filters_by_state(temp_workspace, sample_papers):
    """状态过滤使用 Registry 中的当前状态。"""
    from paperbase.schemas.manifest import PaperState

    registry = PaperRegistry(temp_workspace["registry"])
    registry.update_state("paper001", PaperState.NORMALIZED)
    registry.close()

    engine = SearchEngine(temp_workspace["index"], temp_workspace["library"])
    engine.build_index()

    results = engine.search("learning", limit=10, state_filter="normalized")

    assert [result["paper_id"] for result in results] == ["paper001"]
    engine.close()


def test_graph_query_find_related_papers(temp_workspace, sample_graph):
    """测试查找相关论文"""
    graph_dir = temp_workspace["graph"]

    # 查找 paper001 的直接相关论文
    related = find_related_papers(graph_dir, "p_001_paper", depth=1)

    assert "p_002_paper" in related
    assert "p_001_paper" not in related  # 不包含自己

    # 查找二度相关论文
    related_depth2 = find_related_papers(graph_dir, "p_001_paper", depth=2)

    assert "p_002_paper" in related_depth2
    assert "p_003_paper" in related_depth2  # 二度相关


def test_graph_query_no_related_papers(temp_workspace, sample_graph):
    """测试不存在的论文"""
    graph_dir = temp_workspace["graph"]

    # 查找不存在的论文
    related = find_related_papers(graph_dir, "paper999", depth=1)

    assert len(related) == 0


def test_graph_query_find_papers_by_topic(temp_workspace, sample_graph):
    """测试按主题查找论文"""
    graph_dir = temp_workspace["graph"]

    # 查找包含 "machine learning" 主题的论文
    papers = find_papers_by_topic(graph_dir, "machine learning")

    assert "p_001_paper" in papers

    # 查找包含 "deep learning" 主题的论文
    papers = find_papers_by_topic(graph_dir, "deep learning")

    assert "p_002_paper" in papers


def test_graph_query_topic_case_insensitive(temp_workspace, sample_graph):
    """测试主题查询大小写不敏感"""
    graph_dir = temp_workspace["graph"]

    # 大小写不同的查询应该返回相同结果
    papers1 = find_papers_by_topic(graph_dir, "Machine Learning")
    papers2 = find_papers_by_topic(graph_dir, "machine learning")
    papers3 = find_papers_by_topic(graph_dir, "MACHINE LEARNING")

    assert papers1 == papers2 == papers3


def test_graph_query_topic_no_match(temp_workspace, sample_graph):
    """测试主题查询无匹配"""
    graph_dir = temp_workspace["graph"]

    # 查找不存在的主题
    papers = find_papers_by_topic(graph_dir, "quantum computing")

    assert len(papers) == 0


def test_end_to_end_search_and_query(temp_workspace, sample_papers, sample_graph):
    """端到端测试：搜索 + 图谱查询"""
    # 1. 构建搜索索引
    engine = SearchEngine(temp_workspace["index"], temp_workspace["library"])
    engine.build_index()

    # 2. 搜索 "neural networks"
    search_results = engine.search("neural networks", limit=5)
    assert len(search_results) > 0

    found_paper_id = search_results[0]["paper_id"]
    assert found_paper_id == "paper002"

    # 3. 通过 Registry 的 storage_id 映射到 Graphify 论文节点
    registry = PaperRegistry(temp_workspace["registry"])
    found_paper = registry.get_paper(found_paper_id)
    related_papers = find_related_papers(
        temp_workspace["graph"],
        f"{found_paper['storage_id']}_paper",
        depth=1,
    )
    assert len(related_papers) > 0

    # 4. 验证 Graphify 节点前缀对应 Registry storage_id
    registry_by_storage = {paper["storage_id"]: paper for paper in registry.list_papers()}
    for graph_node_id in related_papers:
        storage_id = graph_node_id.removesuffix("_paper")
        assert storage_id in registry_by_storage

    registry.close()
    engine.close()


def test_registry_integration(temp_workspace, sample_papers):
    """测试 Registry 集成"""
    registry = PaperRegistry(temp_workspace["registry"])

    # 验证所有论文都在 registry 中
    for paper in sample_papers:
        paper_data = registry.get_paper(paper["paper_id"])
        assert paper_data is not None
        assert paper_data["title"] == paper["title"]
        # authors 存储为列表
        assert paper_data["authors"] == paper["authors"].split(", ")
        assert paper_data["year"] == paper["year"]

    registry.close()
