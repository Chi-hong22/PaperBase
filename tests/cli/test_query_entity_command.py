"""CLI tests for query entity command"""

import json
from pathlib import Path
import pytest
from click.testing import CliRunner
from paperbase.cli.main import main as cli


@pytest.fixture
def mock_project(tmp_path):
    """创建模拟项目环境"""
    # 创建 graph 目录和 entities.jsonl
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()

    entities_file = graph_dir / "entities.jsonl"
    nodes = [
        {"id": "method:SLAM", "type": "Method", "name": "SLAM", "category": "methods"},
        {"id": "dataset:ImageNet", "type": "Dataset", "name": "ImageNet", "category": "datasets"},
    ]
    edges = [
        {"source": "doi:10.1038/nature01", "target": "method:SLAM", "relation": "uses_method"},
        {"source": "doi:10.1038/nature02", "target": "method:SLAM", "relation": "uses_method"},
        {"source": "doi:10.1038/nature01", "target": "dataset:ImageNet", "relation": "uses_dataset"},
    ]

    with open(entities_file, "w", encoding="utf-8") as f:
        for node in nodes:
            f.write(json.dumps(node, ensure_ascii=False) + "\n")
        for edge in edges:
            f.write(json.dumps(edge, ensure_ascii=False) + "\n")

    # 创建 registry
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()

    # 使用 SQLite 创建简单的 registry
    import sqlite3
    db_path = registry_dir / "papers.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE papers (
            paper_id TEXT PRIMARY KEY,
            storage_id TEXT,
            title TEXT,
            authors TEXT,
            year INTEGER,
            state TEXT,
            ingest_time TEXT,
            update_time TEXT
        )
    """)

    cursor.execute("""
        INSERT INTO papers (paper_id, storage_id, title, authors, year, state, ingest_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "doi:10.1038/nature01",
        "paper1",
        "Sample Paper 1",
        "Alice, Bob",
        2023,
        "ready",
        "2024-01-01T00:00:00Z",
        "2024-01-01T00:00:00Z"
    ))

    cursor.execute("""
        INSERT INTO papers (paper_id, storage_id, title, authors, year, state, ingest_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "doi:10.1038/nature02",
        "paper2",
        "Sample Paper 2",
        "Carol",
        2024,
        "ready",
        "2024-01-02T00:00:00Z",
        "2024-01-02T00:00:00Z"
    ))

    conn.commit()
    conn.close()

    return tmp_path


class TestQueryEntityCommand:
    """测试 query entity CLI 命令"""

    def test_query_entity_basic(self, mock_project):
        """测试基本实体查询"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--base-dir", str(mock_project),
            "query", "entity", "methods:SLAM"
        ])

        assert result.exit_code == 0
        assert "doi:10.1038/nature01" in result.output
        assert "doi:10.1038/nature02" in result.output
        assert "找到 2 个论文" in result.output

    def test_query_entity_single_match(self, mock_project):
        """测试单个匹配"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--base-dir", str(mock_project),
            "query", "entity", "datasets:ImageNet"
        ])

        assert result.exit_code == 0
        assert "doi:10.1038/nature01" in result.output
        assert "找到 1 个论文" in result.output

    def test_query_entity_no_match(self, mock_project):
        """测试无匹配"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--base-dir", str(mock_project),
            "query", "entity", "methods:NonExistent"
        ])

        assert result.exit_code == 0
        assert "未找到使用实体" in result.output

    def test_query_entity_case_insensitive(self, mock_project):
        """测试大小写不敏感"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--base-dir", str(mock_project),
            "query", "entity", "METHODS:slam"
        ])

        assert result.exit_code == 0
        assert "doi:10.1038/nature01" in result.output
        assert "doi:10.1038/nature02" in result.output

    def test_query_entity_no_graph(self, tmp_path):
        """测试图谱不存在"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--base-dir", str(tmp_path),
            "query", "entity", "methods:SLAM"
        ])

        assert result.exit_code == 0
        assert "图谱目录不存在" in result.output

    def test_query_entity_no_registry(self, tmp_path):
        """测试 registry 不存在"""
        # 只创建 graph 目录
        graph_dir = tmp_path / "graph"
        graph_dir.mkdir()
        (graph_dir / "entities.jsonl").touch()

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--base-dir", str(tmp_path),
            "query", "entity", "methods:SLAM"
        ])

        assert result.exit_code == 0
        assert "Registry 不存在" in result.output
