import pytest
from pathlib import Path
from paperbase.adapters.pdf_converter import convert_pdf_to_markdown


@pytest.fixture
def sample_pdf():
    return Path("tests/fixtures/sample_liu2025.pdf")


def test_convert_pdf_to_markdown(sample_pdf):
    """测试 PDF 转 Markdown"""
    if not sample_pdf.exists():
        pytest.skip("测试 PDF 不存在")

    markdown = convert_pdf_to_markdown(sample_pdf)

    assert isinstance(markdown, str)
    assert len(markdown) > 100  # 至少有一些内容
