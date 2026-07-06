import pytest
import json
import tempfile
from pathlib import Path
from paperbase.core.reference_extractor import extract_references, write_references_jsonl


def test_extract_references_from_markdown_basic():
    """测试从 Markdown 提取基本引用"""
    markdown = """---
schema_version: "1.0"
paper_id: "arxiv:2401.12345"
---

# Introduction

Some content here.

## References

[1] Smith, J. (2020). A Study on Machine Learning. *Nature*, 123, 456-789. DOI: 10.1038/nature123

[2] Johnson, A., & Williams, B. (2019). Deep Learning Methods. *Science*, 456, 123-456.

[3] Brown, C. (2021). Neural Networks Today. arXiv:2101.12345.
"""

    paper_id = "arxiv:2401.12345"
    references = extract_references(markdown, paper_id)

    assert len(references) == 3

    # 验证第一个引用
    assert references[0]["id"] == "arxiv:2401.12345:ref:0"
    assert references[0]["paper_id"] == paper_id
    assert "Smith" in references[0]["authors"]
    assert references[0]["year"] == 2020
    assert "Machine Learning" in references[0]["title"]
    assert references[0]["doi"] == "10.1038/nature123"

    # 验证第二个引用
    assert references[1]["id"] == "arxiv:2401.12345:ref:1"
    assert "Johnson" in references[1]["authors"]
    assert "Williams" in references[1]["authors"]
    assert references[1]["year"] == 2019

    # 验证第三个引用
    assert references[2]["id"] == "arxiv:2401.12345:ref:2"
    assert "Brown" in references[2]["authors"]
    assert references[2]["year"] == 2021


def test_extract_references_no_references_section():
    """测试没有 References 部分"""
    markdown = """# Introduction

Some content without references.

## Conclusion

Done."""

    references = extract_references(markdown, "arxiv:test")
    assert references == []


def test_extract_references_empty_references_section():
    """测试空的 References 部分"""
    markdown = """# Introduction

Some content.

## References

(No references provided)
"""

    references = extract_references(markdown, "arxiv:test")
    assert references == []


def test_extract_references_alternative_heading():
    """测试不同的标题格式（Bibliography）"""
    markdown = """# Introduction

Content.

# Bibliography

[1] Author, X. (2022). Test Paper. *Journal*, 1, 1-10.
"""

    references = extract_references(markdown, "doi:10.1234/test")
    assert len(references) >= 1


def test_extract_references_with_complex_authors():
    """测试复杂作者列表"""
    markdown = """## References

[1] Smith, J., Johnson, A., Williams, B., Brown, C., & Davis, D. (2023). A Complex Study. DOI: 10.1000/test
"""

    references = extract_references(markdown, "test")

    assert len(references) == 1
    assert "Smith" in references[0]["authors"]
    assert "Davis" in references[0]["authors"]
    assert references[0]["year"] == 2023


def test_extract_references_without_doi():
    """测试没有 DOI 的引用"""
    markdown = """## References

[1] Anonymous (2020). Paper Without DOI. *Unknown Journal*.
"""

    references = extract_references(markdown, "test")

    assert len(references) == 1
    assert references[0]["doi"] is None


def test_extract_references_preserves_position():
    """测试 position 字段正确递增"""
    markdown = """## References

[1] First, A. (2020). First Paper.

[2] Second, B. (2021). Second Paper.

[3] Third, C. (2022). Third Paper.
"""

    references = extract_references(markdown, "test")

    assert len(references) == 3
    for i, ref in enumerate(references):
        assert ref["position"] == i


def test_write_references_jsonl():
    """测试 JSONL 输出"""
    references = [
        {
            "id": "test:ref:0",
            "paper_id": "test",
            "title": "Test Paper",
            "authors": "Smith, J.",
            "year": 2020,
            "doi": "10.1234/test",
            "position": 0,
        },
        {
            "id": "test:ref:1",
            "paper_id": "test",
            "title": "Another Paper",
            "authors": "Johnson, A.",
            "year": 2021,
            "doi": None,
            "position": 1,
        },
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "references.jsonl"
        write_references_jsonl(references, output_path)

        # 验证文件存在
        assert output_path.exists()

        # 验证 JSONL 格式
        with open(output_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 2

        # 验证每行都是有效的 JSON
        loaded_ref_0 = json.loads(lines[0])
        assert loaded_ref_0["title"] == "Test Paper"
        assert loaded_ref_0["doi"] == "10.1234/test"

        loaded_ref_1 = json.loads(lines[1])
        assert loaded_ref_1["title"] == "Another Paper"
        assert loaded_ref_1["doi"] is None


def test_write_references_jsonl_creates_parent_dir():
    """测试 JSONL 输出会创建父目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "subdir" / "nested" / "references.jsonl"

        references = [
            {
                "id": "test:ref:0",
                "paper_id": "test",
                "title": "Test",
                "authors": "Author",
                "year": 2020,
                "doi": None,
                "position": 0,
            }
        ]

        write_references_jsonl(references, output_path)

        # 验证文件和父目录都存在
        assert output_path.exists()
        assert output_path.parent.exists()


def test_extract_references_mixed_formats():
    """测试混合格式的引用（不同引用风格）"""
    markdown = """## References

[1] Smith J, Johnson A (2020) Title here. Journal Name 10:123-456.

[2] Williams, B. and Brown, C. (2021). "Another Title." In Proceedings of Conference, pp. 1-10. DOI: 10.1234/conf

[3] Davis D (2022). "Third Paper". Available at: https://example.com
"""

    references = extract_references(markdown, "test")

    # 至少能提取到引用（即使解析不完美）
    assert len(references) >= 1
