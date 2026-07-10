"""测试 Registry 查重功能"""

import pytest
from pathlib import Path
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState


def test_find_by_doi(tmp_path):
    """测试通过 DOI 查找论文"""
    db_path = tmp_path / "test.db"
    registry = PaperRegistry(db_path)

    # 注册论文
    registry.register_paper(
        paper_id="doi:10.1038/nature12345",
        storage_id="p_abc123",
        state=PaperState.READY,
        title="Test Paper",
        doi="10.1038/nature12345"
    )

    # 查找存在的 DOI
    result = registry.find_by_doi("10.1038/nature12345")
    assert result is not None
    assert result["paper_id"] == "doi:10.1038/nature12345"

    # 查找不存在的 DOI
    result = registry.find_by_doi("10.9999/notfound")
    assert result is None

    registry.close()


def test_find_by_title(tmp_path):
    """测试通过标题查找论文"""
    db_path = tmp_path / "test.db"
    registry = PaperRegistry(db_path)

    # 注册论文
    registry.register_paper(
        paper_id="test:001",
        storage_id="p_xyz789",
        state=PaperState.READY,
        title="Unique Test Paper Title"
    )

    # 查找存在的标题
    result = registry.find_by_title("Unique Test Paper Title")
    assert result is not None
    assert result["paper_id"] == "test:001"

    # 查找不存在的标题
    result = registry.find_by_title("Nonexistent Title")
    assert result is None

    registry.close()


def test_doi_index_exists(tmp_path):
    """测试 DOI 索引是否创建"""
    db_path = tmp_path / "test.db"
    registry = PaperRegistry(db_path)

    # 检查索引是否存在
    cursor = registry.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_papers_doi'"
    )
    result = cursor.fetchone()
    assert result is not None
    assert result[0] == "idx_papers_doi"

    registry.close()


def test_duplicate_doi_detection(tmp_path):
    """测试 DOI 重复检测"""
    db_path = tmp_path / "test.db"
    registry = PaperRegistry(db_path)

    # 注册第一篇论文
    registry.register_paper(
        paper_id="doi:10.1038/nature12345",
        storage_id="p_abc123",
        state=PaperState.READY,
        title="Original Paper",
        doi="10.1038/nature12345"
    )

    # 尝试查找相同 DOI
    existing = registry.find_by_doi("10.1038/nature12345")
    assert existing is not None
    assert existing["paper_id"] == "doi:10.1038/nature12345"
    assert existing["title"] == "Original Paper"

    registry.close()


def test_duplicate_title_detection(tmp_path):
    """测试标题重复检测"""
    db_path = tmp_path / "test.db"
    registry = PaperRegistry(db_path)

    # 注册第一篇论文
    registry.register_paper(
        paper_id="test:001",
        storage_id="p_xyz789",
        state=PaperState.READY,
        title="Duplicate Title Test"
    )

    # 尝试查找相同标题
    existing = registry.find_by_title("Duplicate Title Test")
    assert existing is not None
    assert existing["paper_id"] == "test:001"

    registry.close()


def test_find_by_doi_with_authors(tmp_path):
    """测试查找包含作者信息的论文"""
    db_path = tmp_path / "test.db"
    registry = PaperRegistry(db_path)

    # 注册论文（包含作者）
    registry.register_paper(
        paper_id="doi:10.1038/nature12345",
        storage_id="p_abc123",
        state=PaperState.READY,
        title="Test Paper with Authors",
        authors=["Alice", "Bob", "Charlie"],
        year=2024,
        doi="10.1038/nature12345"
    )

    # 查找并验证作者信息
    result = registry.find_by_doi("10.1038/nature12345")
    assert result is not None
    assert result["authors"] == ["Alice", "Bob", "Charlie"]
    assert result["year"] == 2024

    registry.close()
