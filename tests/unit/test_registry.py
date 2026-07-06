import pytest
from pathlib import Path
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState


@pytest.fixture
def registry(tmp_path):
    """创建临时 registry"""
    db_path = tmp_path / "test.db"
    reg = PaperRegistry(db_path)
    yield reg
    reg.close()


def test_registry_init(registry):
    """测试 registry 初始化"""
    assert registry.conn is not None


def test_register_paper(registry):
    """测试注册论文"""
    registry.register_paper(
        paper_id="doi:10.1234/test",
        storage_id="p_abc123",
        state=PaperState.DISCOVERED,
        title="Test Paper",
        authors=["John Smith"],
        year=2026
    )

    paper = registry.get_paper("doi:10.1234/test")
    assert paper is not None
    assert paper["paper_id"] == "doi:10.1234/test"
    assert paper["state"] == "discovered"
    assert paper["title"] == "Test Paper"


def test_get_paper_not_found(registry):
    """测试查询不存在的论文"""
    paper = registry.get_paper("doi:10.1234/notexist")
    assert paper is None


def test_update_state(registry):
    """测试更新状态"""
    registry.register_paper(
        paper_id="doi:10.1234/test",
        storage_id="p_abc123",
        state=PaperState.DISCOVERED,
        title="Test",
        authors=[],
        year=2026
    )

    registry.update_state("doi:10.1234/test", PaperState.READY)

    paper = registry.get_paper("doi:10.1234/test")
    assert paper["state"] == "ready"


def test_list_papers_by_state(registry):
    """测试按状态查询"""
    registry.register_paper(
        paper_id="doi:10.1234/test1",
        storage_id="p_abc123",
        state=PaperState.READY,
        title="Test1",
        authors=[],
        year=2026
    )
    registry.register_paper(
        paper_id="doi:10.1234/test2",
        storage_id="p_abc124",
        state=PaperState.DISCOVERED,
        title="Test2",
        authors=[],
        year=2026
    )

    ready_papers = registry.list_papers(state=PaperState.READY)
    assert len(ready_papers) == 1
    assert ready_papers[0]["paper_id"] == "doi:10.1234/test1"
