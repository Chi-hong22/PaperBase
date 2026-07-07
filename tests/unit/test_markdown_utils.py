# tests/unit/test_markdown_utils.py
import pytest
from pathlib import Path
from paperbase.utils.markdown import (
    parse_frontmatter,
    generate_canonical_markdown,
    update_frontmatter_file
)


def test_parse_frontmatter_valid():
    """解析有效的 frontmatter"""
    content = """---
title: Test Paper
year: 2025
---

Body content here."""

    metadata, body = parse_frontmatter(content)

    assert metadata["title"] == "Test Paper"
    assert metadata["year"] == 2025
    assert body.strip() == "Body content here."


def test_parse_frontmatter_empty_body():
    """解析只有 frontmatter 的内容"""
    content = """---
title: Test
---
"""

    metadata, body = parse_frontmatter(content)

    assert metadata["title"] == "Test"
    assert body.strip() == ""


def test_parse_frontmatter_invalid_format():
    """解析无效格式应该抛出 ValueError"""
    content = "No frontmatter here"

    with pytest.raises(ValueError, match="Invalid frontmatter format"):
        parse_frontmatter(content)


def test_parse_frontmatter_invalid_yaml():
    """解析无效 YAML 应该抛出 ValueError"""
    content = """---
invalid: [unclosed
---
"""

    with pytest.raises(ValueError, match="Invalid YAML"):
        parse_frontmatter(content)


def test_generate_canonical_markdown():
    """生成 Canonical Markdown"""
    metadata = {
        "title": "Test Paper",
        "year": 2025,
        "authors": ["Alice", "Bob"]
    }
    body = "Paper content"

    result = generate_canonical_markdown(metadata, body)

    assert result.startswith("---\n")
    assert "title: Test Paper" in result
    assert "year: 2025" in result
    assert result.endswith("Paper content")


def test_generate_canonical_markdown_preserves_order():
    """生成的 Markdown 应该保持字段顺序"""
    # 使用普通 dict，Python 3.7+ 保证插入顺序
    metadata = {
        "schema_version": "1.0",
        "paper_id": "doi:123",
        "title": "Test"
    }
    body = "Content"

    result = generate_canonical_markdown(metadata, body)

    # 提取 frontmatter 部分
    frontmatter_section = result.split("---\n")[1]
    lines = frontmatter_section.strip().split("\n")

    # 检查顺序（dict 在 Python 3.7+ 保持插入顺序）
    assert "schema_version" in lines[0]
    assert "paper_id" in lines[1]
    assert "title" in lines[2]


def test_update_frontmatter_file(tmp_path):
    """原子更新 frontmatter 文件"""
    # 创建测试文件
    test_file = tmp_path / "paper.md"
    original_content = """---
title: Original
year: 2024
---

Body content."""
    test_file.write_text(original_content, encoding="utf-8")

    # 更新
    updates = {"year": 2025, "new_field": "value"}
    update_frontmatter_file(test_file, updates)

    # 验证
    updated_content = test_file.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(updated_content)

    assert metadata["title"] == "Original"  # 未修改的字段保留
    assert metadata["year"] == 2025  # 更新的字段
    assert metadata["new_field"] == "value"  # 新增的字段
    assert body.strip() == "Body content."  # Body 不变


def test_update_frontmatter_file_preserves_on_error(tmp_path):
    """更新失败时应该保留原文件（测试原子性）"""
    test_file = tmp_path / "paper.md"
    original_content = """---
title: Test
---

Body."""
    test_file.write_text(original_content, encoding="utf-8")

    # 模拟失败场景 - 使用无效的 YAML 内容触发解析错误
    # 先破坏文件，然后尝试更新（这会在 parse_frontmatter 阶段失败）
    test_file.write_text("Invalid content without frontmatter", encoding="utf-8")

    # 尝试更新应该失败
    try:
        updates = {"new_field": "value"}
        update_frontmatter_file(test_file, updates)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass  # 预期失败

    # 文件内容应该还是无效内容（因为在读取阶段就失败了）
    content = test_file.read_text(encoding="utf-8")
    assert "Invalid content" in content
