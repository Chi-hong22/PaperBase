import pytest
from paperbase.schemas.csl import CSLName, CSLDate, CSLItem
from paperbase.schemas.paper import PaperMetadata, PaperIdentifiers, PaperSource, PaperProvenance
from paperbase.schemas.manifest import ManifestSchema, PaperState


def test_csl_name_valid():
    """测试 CSL 名称格式"""
    name = CSLName(family="Smith", given="John")
    assert name.family == "Smith"
    assert name.given == "John"


def test_csl_name_family_only():
    """测试仅姓氏"""
    name = CSLName(family="Smith")
    assert name.family == "Smith"
    assert name.given is None


def test_csl_date_valid():
    """测试 CSL 日期格式"""
    date = CSLDate(date_parts=[[2026, 7, 6]])
    assert date.date_parts == [[2026, 7, 6]]


def test_csl_item_minimal():
    """测试最小 CSL item"""
    item = CSLItem(
        type="article-journal",
        id="item-1",
        title="Test Paper",
        author=[CSLName(family="Smith", given="John")],
        issued=CSLDate(date_parts=[[2026]])
    )
    assert item.type == "article-journal"
    assert item.title == "Test Paper"
    assert len(item.author) == 1


def test_csl_item_with_doi():
    """测试带 DOI 的 CSL item"""
    item = CSLItem(
        type="article-journal",
        id="item-1",
        title="Test Paper",
        author=[CSLName(family="Smith")],
        issued=CSLDate(date_parts=[[2026]]),
        DOI="10.1234/test"
    )
    assert item.DOI == "10.1234/test"


def test_paper_metadata_minimal():
    """测试最小 paper metadata"""
    metadata = PaperMetadata(
        schema_version="1.0",
        paper_id="doi:10.1234/test",
        storage_id="p_abc123",
        title="Test Paper",
        authors=[{"name": "John Smith"}],
        year=2026,
        abstract="Test abstract"
    )
    assert metadata.paper_id == "doi:10.1234/test"
    assert metadata.title == "Test Paper"
    assert metadata.year == 2026


def test_paper_metadata_with_identifiers():
    """测试带完整标识符的 metadata"""
    metadata = PaperMetadata(
        schema_version="1.0",
        paper_id="doi:10.1234/test",
        storage_id="p_abc123",
        title="Test Paper",
        authors=[{"name": "John Smith"}],
        year=2026,
        abstract="Test abstract",
        identifiers=PaperIdentifiers(
            doi="10.1234/test",
            arxiv="2401.12345"
        )
    )
    assert metadata.identifiers.doi == "10.1234/test"
    assert metadata.identifiers.arxiv == "2401.12345"


def test_manifest_minimal():
    """测试最小 manifest"""
    manifest = ManifestSchema(
        paper_id="doi:10.1234/test",
        storage_id="p_abc123",
        state=PaperState.NORMALIZED
    )
    assert manifest.paper_id == "doi:10.1234/test"
    assert manifest.state == PaperState.NORMALIZED


def test_manifest_state_transitions():
    """测试状态枚举"""
    assert {state.value for state in PaperState} == {
        "normalized",
        "ready",
        "needs_review",
        "blocked",
        "failed_retryable",
        "failed_permanent",
    }
