import pytest
from paperbase.core.identity import normalize_paper_id, generate_storage_id, parse_paper_id


def test_normalize_doi():
    """测试 DOI 规范化"""
    assert normalize_paper_id("10.1038/s41586-026-10265-5") == "doi:10.1038/s41586-026-10265-5"
    assert normalize_paper_id("doi:10.1038/nature") == "doi:10.1038/nature"
    assert normalize_paper_id("DOI:10.1038/nature") == "doi:10.1038/nature"


def test_normalize_arxiv():
    """测试 arXiv 规范化"""
    assert normalize_paper_id("2401.12345") == "arxiv:2401.12345"
    assert normalize_paper_id("arxiv:2401.12345") == "arxiv:2401.12345"
    assert normalize_paper_id("arXiv:2401.12345v1") == "arxiv:2401.12345"


def test_generate_storage_id():
    """测试 storage_id 生成"""
    paper_id = "doi:10.1038/s41586-026-10265-5"
    storage_id = generate_storage_id(paper_id)

    assert storage_id.startswith("p_")
    assert len(storage_id) == 14  # p_ + 12 chars

    # 幂等性
    assert generate_storage_id(paper_id) == storage_id


def test_parse_paper_id():
    """测试 paper_id 解析"""
    result = parse_paper_id("doi:10.1038/nature")
    assert result["type"] == "doi"
    assert result["value"] == "10.1038/nature"

    result = parse_paper_id("arxiv:2401.12345")
    assert result["type"] == "arxiv"
    assert result["value"] == "2401.12345"
