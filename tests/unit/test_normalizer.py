import pytest
from paperbase.core.normalizer import normalize_paper, extract_abstract


def test_normalize_paper_minimal():
    """测试最小规范化"""
    candidate_md = """
# Test Paper

## Abstract
This is a test abstract.

## Introduction
Some content here.
"""

    metadata = {
        "title": "Test Paper",
        "authors": ["John Smith"],
        "year": 2025
    }

    result = normalize_paper(
        candidate_md=candidate_md,
        metadata=metadata,
        paper_id="doi:10.1234/test",
        storage_id="p_test123"
    )

    assert result.paper_id == "doi:10.1234/test"
    assert result.title == "Test Paper"
    assert len(result.authors) == 1
    assert result.year == 2025
    assert "test abstract" in result.abstract.lower()


def test_extract_abstract():
    """测试摘要提取"""
    text = """
# Title

## Abstract
This is the abstract content.
It spans multiple lines.

## Introduction
This is not abstract.
"""

    abstract = extract_abstract(text)
    assert "abstract content" in abstract.lower()
    assert "introduction" not in abstract.lower()
