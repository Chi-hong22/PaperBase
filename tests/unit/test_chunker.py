import pytest
import json
import tempfile
from pathlib import Path
from paperbase.core.chunker import generate_chunks, write_chunks_jsonl


def test_generate_chunks_basic():
    """测试基本段落分块"""
    markdown = """# Introduction

This is the first paragraph.

This is the second paragraph.

This is the third paragraph."""

    paper_id = "arxiv:2401.12345"
    chunks = generate_chunks(markdown, paper_id)

    assert len(chunks) == 4  # title + 3 paragraphs
    assert chunks[0]["id"] == "arxiv:2401.12345:chunk:0"
    assert chunks[0]["paper_id"] == paper_id
    assert chunks[0]["position"] == 0
    assert "Introduction" in chunks[0]["content"]

    assert chunks[1]["id"] == "arxiv:2401.12345:chunk:1"
    assert chunks[1]["content"] == "This is the first paragraph."
    assert chunks[1]["position"] == 1


def test_generate_chunks_empty():
    """测试空内容处理"""
    chunks = generate_chunks("", "arxiv:2401.12345")
    assert chunks == []

    chunks = generate_chunks("   \n\n   ", "arxiv:2401.12345")
    assert chunks == []


def test_generate_chunks_long_paragraph():
    """测试超长段落自动切分"""
    # 创建一个超过 2048 字符的段落（约 5000 字符）
    long_text = "word " * 1000  # 约 5000 字符
    markdown = f"# Title\n\n{long_text}"

    paper_id = "doi:10.1038/test"
    chunks = generate_chunks(markdown, paper_id)

    # 应该被切分为多个 chunk（title + 至少 2 个切分的段落）
    assert len(chunks) >= 3

    # 每个 chunk 不应该太长（约 512 token = 2048 字符，留一些余量）
    for chunk in chunks:
        assert len(chunk["content"]) <= 2500

    # 验证 position 连续
    for i, chunk in enumerate(chunks):
        assert chunk["position"] == i


def test_generate_chunks_mixed_content():
    """测试混合内容（标题、段落、列表）"""
    markdown = """# Main Title

## Section 1

First paragraph in section 1.

Second paragraph in section 1.

## Section 2

- List item 1
- List item 2

Final paragraph."""

    paper_id = "arxiv:2401.99999"
    chunks = generate_chunks(markdown, paper_id)

    # 验证有多个 chunk
    assert len(chunks) > 0

    # 验证所有 chunk 都有必需字段
    for chunk in chunks:
        assert "id" in chunk
        assert "paper_id" in chunk
        assert "content" in chunk
        assert "position" in chunk
        assert chunk["paper_id"] == paper_id

    # 验证 id 格式
    assert chunks[0]["id"] == f"{paper_id}:chunk:0"


def test_generate_chunks_preserves_formatting():
    """测试保留格式"""
    markdown = """## Abstract

This is **bold** and *italic* text.

This has `code` in it."""

    chunks = generate_chunks(markdown, "arxiv:test")

    # 验证格式被保留
    assert any("**bold**" in chunk["content"] for chunk in chunks)
    assert any("*italic*" in chunk["content"] for chunk in chunks)
    assert any("`code`" in chunk["content"] for chunk in chunks)


def test_write_chunks_jsonl():
    """测试 JSONL 输出"""
    markdown = """# Title

First paragraph.

Second paragraph."""

    paper_id = "arxiv:2401.12345"
    chunks = generate_chunks(markdown, paper_id)

    # 创建临时文件
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "chunks.jsonl"
        write_chunks_jsonl(chunks, output_path)

        # 验证文件存在
        assert output_path.exists()

        # 验证 JSONL 格式
        with open(output_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == len(chunks)

        # 验证每行都是有效的 JSON
        for i, line in enumerate(lines):
            loaded_chunk = json.loads(line)
            assert loaded_chunk["id"] == chunks[i]["id"]
            assert loaded_chunk["paper_id"] == chunks[i]["paper_id"]
            assert loaded_chunk["content"] == chunks[i]["content"]
            assert loaded_chunk["position"] == chunks[i]["position"]


def test_write_chunks_jsonl_creates_parent_dir():
    """测试 JSONL 输出会创建父目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "subdir" / "nested" / "chunks.jsonl"

        chunks = [
            {
                "id": "test:chunk:0",
                "paper_id": "test",
                "content": "Test content",
                "position": 0,
            }
        ]

        write_chunks_jsonl(chunks, output_path)

        # 验证文件和父目录都存在
        assert output_path.exists()
        assert output_path.parent.exists()
