"""测试 search 命令"""

import pytest
from pathlib import Path
from click.testing import CliRunner
from paperbase.cli.main import main
from paperbase.core.search_engine import SearchEngine
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState
import json


@pytest.fixture
def test_workspace(tmp_path):
    """创建测试工作区"""
    # 创建目录结构
    library_path = tmp_path / "library" / "papers"
    index_path = tmp_path / "index"
    registry_path = tmp_path / "registry"

    library_path.mkdir(parents=True)
    index_path.mkdir(parents=True)
    registry_path.mkdir(parents=True)

    # 创建测试数据
    paper_dir = library_path / "paper001"
    paper_dir.mkdir()

    # 写入 chunks.jsonl
    chunks = [
        {
            "id": "chunk001",
            "paper_id": "paper001",
            "content": "Machine learning is a subset of artificial intelligence.",
            "position": 0
        },
        {
            "id": "chunk002",
            "paper_id": "paper001",
            "content": "Deep learning uses neural networks with multiple layers.",
            "position": 1
        }
    ]

    with open(paper_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk) + "\n")

    # 初始化 registry
    registry = PaperRegistry(registry_path / "papers.db")
    registry.register_paper(
        paper_id="paper001",
        storage_id="paper001",
        state=PaperState.READY,
        title="Introduction to Machine Learning",
        authors=["John Doe"],
        year=2024
    )
    registry.close()

    # 构建搜索索引
    engine = SearchEngine(index_path / "fts.db", library_path)
    engine.build_index()
    engine.close()

    return tmp_path


def test_search_command_with_results(test_workspace):
    """测试搜索命令 - 有结果"""
    runner = CliRunner()
    result = runner.invoke(main, [
        "--base-dir", str(test_workspace),
        "search", "machine learning"
    ])

    assert result.exit_code == 0
    assert "Introduction" in result.output
    assert "Learning" in result.output
    assert "找到" in result.output
    assert "Machine" in result.output


def test_search_command_no_results(test_workspace):
    """测试搜索命令 - 无结果"""
    runner = CliRunner()
    result = runner.invoke(main, [
        "--base-dir", str(test_workspace),
        "search", "quantum computing"
    ])

    assert result.exit_code == 0
    assert "未找到匹配结果" in result.output


def test_search_command_with_limit(test_workspace):
    """测试搜索命令 - 限制结果数量"""
    runner = CliRunner()
    result = runner.invoke(main, [
        "--base-dir", str(test_workspace),
        "search", "learning", "--limit", "1"
    ])

    assert result.exit_code == 0
    assert "learning" in result.output


def test_search_command_supports_documented_metadata_filters(test_workspace):
    """公开文档中的状态和年份边界参数应可组合使用。"""
    runner = CliRunner()
    result = runner.invoke(main, [
        "--base-dir", str(test_workspace),
        "search", "learning",
        "--state", "ready",
        "--year-min", "2020",
        "--year-max", "2025",
    ])

    assert result.exit_code == 0
    assert "Introduction" in result.output


def test_search_command_no_index(tmp_path):
    """测试搜索命令 - 索引不存在"""
    runner = CliRunner()
    result = runner.invoke(main, [
        "--base-dir", str(tmp_path),
        "search", "test"
    ])

    assert result.exit_code == 0
    assert "搜索索引不存在" in result.output


def test_search_without_registry_does_not_create_database(tmp_path):
    """无元数据过滤的全文搜索不应隐式创建 Registry。"""
    library_path = tmp_path / "library" / "papers"
    paper_dir = library_path / "paper001"
    paper_dir.mkdir(parents=True)
    with open(paper_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "id": "chunk001",
            "paper_id": "paper001",
            "content": "machine learning",
            "position": 0,
        }) + "\n")

    engine = SearchEngine(tmp_path / "index" / "fts.db", library_path)
    engine.build_index()
    engine.close()

    runner = CliRunner()
    result = runner.invoke(main, [
        "--base-dir", str(tmp_path),
        "search", "learning",
    ])

    assert result.exit_code == 0
    assert "找到 1 个结果" in result.output
    assert not (tmp_path / "registry" / "papers.db").exists()
