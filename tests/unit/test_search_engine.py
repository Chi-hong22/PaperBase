"""测试 SearchEngine"""

import pytest
import json
import tempfile
from pathlib import Path
from paperbase.core.search_engine import SearchEngine


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_chunks(temp_dir):
    """创建示例 chunks.jsonl 文件"""
    # 创建两篇论文的 chunks
    library_dir = temp_dir / "library" / "papers"

    # Paper 1: 关于机器学习的论文
    paper1_dir = library_dir / "p_ml001"
    paper1_dir.mkdir(parents=True, exist_ok=True)
    chunks1 = [
        {
            "id": "p_ml001:chunk:0",
            "paper_id": "p_ml001",
            "content": "Machine learning is a subset of artificial intelligence that focuses on algorithms.",
            "position": 0
        },
        {
            "id": "p_ml001:chunk:1",
            "paper_id": "p_ml001",
            "content": "Deep learning uses neural networks with multiple layers to learn representations.",
            "position": 1
        },
        {
            "id": "p_ml001:chunk:2",
            "paper_id": "p_ml001",
            "content": "Supervised learning requires labeled training data for classification tasks.",
            "position": 2
        }
    ]
    with open(paper1_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
        for chunk in chunks1:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    # Paper 2: 关于自然语言处理的论文
    paper2_dir = library_dir / "p_nlp002"
    paper2_dir.mkdir(parents=True, exist_ok=True)
    chunks2 = [
        {
            "id": "p_nlp002:chunk:0",
            "paper_id": "p_nlp002",
            "content": "Natural language processing applies machine learning to text data.",
            "position": 0
        },
        {
            "id": "p_nlp002:chunk:1",
            "paper_id": "p_nlp002",
            "content": "Transformers revolutionized NLP with attention mechanisms.",
            "position": 1
        }
    ]
    with open(paper2_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
        for chunk in chunks2:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    return temp_dir


def test_search_engine_initialization(temp_dir):
    """测试 SearchEngine 初始化"""
    index_path = temp_dir / "registry" / "search_index.db"
    library_path = temp_dir / "library" / "papers"

    engine = SearchEngine(index_path, library_path)
    assert engine.index_path == index_path
    assert engine.library_path == library_path
    engine.close()


def test_build_index(sample_chunks):
    """测试构建 FTS5 索引"""
    index_path = sample_chunks / "registry" / "search_index.db"
    library_path = sample_chunks / "library" / "papers"

    engine = SearchEngine(index_path, library_path)
    engine.build_index()

    # 验证索引文件已创建
    assert index_path.exists()

    engine.close()


def test_simple_search(sample_chunks):
    """测试简单搜索"""
    index_path = sample_chunks / "registry" / "search_index.db"
    library_path = sample_chunks / "library" / "papers"

    engine = SearchEngine(index_path, library_path)
    engine.build_index()

    # 搜索 "machine learning"
    results = engine.search("machine learning")

    assert len(results) >= 2  # 应该匹配两篇论文
    assert all("paper_id" in r for r in results)
    assert all("score" in r for r in results)
    assert all("snippet" in r for r in results)

    # 验证结果包含相关论文
    paper_ids = [r["paper_id"] for r in results]
    assert "p_ml001" in paper_ids
    assert "p_nlp002" in paper_ids

    engine.close()


def test_boolean_and_query(sample_chunks):
    """测试布尔 AND 查询"""
    index_path = sample_chunks / "registry" / "search_index.db"
    library_path = sample_chunks / "library" / "papers"

    engine = SearchEngine(index_path, library_path)
    engine.build_index()

    # 搜索同时包含 "neural" 和 "networks" 的内容
    results = engine.search("neural AND networks")

    assert len(results) >= 1
    assert results[0]["paper_id"] == "p_ml001"

    engine.close()


def test_boolean_or_query(sample_chunks):
    """测试布尔 OR 查询"""
    index_path = sample_chunks / "registry" / "search_index.db"
    library_path = sample_chunks / "library" / "papers"

    engine = SearchEngine(index_path, library_path)
    engine.build_index()

    # 搜索包含 "transformers" 或 "neural" 的内容
    results = engine.search("transformers OR neural")

    assert len(results) >= 2
    paper_ids = [r["paper_id"] for r in results]
    assert "p_ml001" in paper_ids
    assert "p_nlp002" in paper_ids

    engine.close()


def test_boolean_not_query(sample_chunks):
    """测试布尔 NOT 查询"""
    index_path = sample_chunks / "registry" / "search_index.db"
    library_path = sample_chunks / "library" / "papers"

    engine = SearchEngine(index_path, library_path)
    engine.build_index()

    # 搜索包含 "machine" 但不包含 "neural" 的内容
    results = engine.search("machine NOT neural")

    assert len(results) >= 1
    # p_nlp002 应该匹配，因为它有 "machine" 但没有 "neural"
    paper_ids = [r["paper_id"] for r in results]
    assert "p_nlp002" in paper_ids

    engine.close()


def test_search_limit(sample_chunks):
    """测试搜索结果数量限制"""
    index_path = sample_chunks / "registry" / "search_index.db"
    library_path = sample_chunks / "library" / "papers"

    engine = SearchEngine(index_path, library_path)
    engine.build_index()

    # 限制返回 1 条结果
    results = engine.search("machine learning", limit=1)

    assert len(results) == 1

    engine.close()


def test_search_no_results(sample_chunks):
    """测试无结果搜索"""
    index_path = sample_chunks / "registry" / "search_index.db"
    library_path = sample_chunks / "library" / "papers"

    engine = SearchEngine(index_path, library_path)
    engine.build_index()

    # 搜索不存在的内容
    results = engine.search("quantum physics")

    assert len(results) == 0

    engine.close()


def test_search_with_special_characters(sample_chunks):
    """测试特殊字符搜索"""
    index_path = sample_chunks / "registry" / "search_index.db"
    library_path = sample_chunks / "library" / "papers"

    engine = SearchEngine(index_path, library_path)
    engine.build_index()

    # 搜索包含引号的查询
    results = engine.search('"machine learning"')

    # 应该找到匹配的结果
    assert len(results) >= 1

    engine.close()


def test_search_pages_until_it_collects_unique_papers(tmp_path):
    """重复分块填满一批时继续分页，不全量载入所有命中。"""
    engine = SearchEngine(tmp_path / "fts.db", tmp_path)
    engine.close()

    class FakeCursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params):
            self.calls.append(params)
            if len(self.calls) == 1:
                return FakeCursor([
                    {"paper_id": "paper001", "score": -1.0, "snippet": "first"}
                    for _ in range(100)
                ])
            return FakeCursor([
                {"paper_id": "paper002", "score": -0.5, "snippet": "second"}
            ])

        def close(self):
            pass

    fake_connection = FakeConnection()
    engine.conn = fake_connection

    results = engine.search("learning", limit=2)

    assert [result["paper_id"] for result in results] == ["paper001", "paper002"]
    assert len(fake_connection.calls) == 2
    assert fake_connection.calls[0][-2:] == [100, 0]
    assert fake_connection.calls[1][-2:] == [100, 100]


def test_rebuild_index(sample_chunks):
    """测试重建索引"""
    index_path = sample_chunks / "registry" / "search_index.db"
    library_path = sample_chunks / "library" / "papers"

    engine = SearchEngine(index_path, library_path)
    engine.build_index()

    # 第一次搜索
    results1 = engine.search("machine learning")
    count1 = len(results1)

    # 重建索引
    engine.build_index()

    # 第二次搜索，结果应该一致
    results2 = engine.search("machine learning")
    count2 = len(results2)

    assert count1 == count2

    engine.close()
