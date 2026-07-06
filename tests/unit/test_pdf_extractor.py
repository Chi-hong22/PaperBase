import pytest
from pathlib import Path
from paperbase.adapters.pdf_extractor import extract_pdf_metadata


@pytest.fixture
def sample_pdf():
    """测试 PDF 路径"""
    return Path("tests/fixtures/sample_liu2025.pdf")


def test_extract_pdf_metadata(sample_pdf):
    """测试提取 PDF 元数据"""
    if not sample_pdf.exists():
        pytest.skip("测试 PDF 不存在")

    metadata = extract_pdf_metadata(sample_pdf)

    assert "title" in metadata
    assert "authors" in metadata
    assert isinstance(metadata["authors"], list)


def test_extract_pdf_metadata_missing_file():
    """测试提取不存在的 PDF"""
    with pytest.raises(FileNotFoundError):
        extract_pdf_metadata(Path("nonexistent.pdf"))
