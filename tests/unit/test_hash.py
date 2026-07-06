import pytest
from pathlib import Path
from paperbase.utils.hash import sha256_file, sha256_string


def test_sha256_string():
    """测试字符串 hash"""
    result = sha256_string("test")
    assert len(result) == 64
    assert result == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


def test_sha256_file(tmp_path):
    """测试文件 hash"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content", encoding="utf-8")

    result = sha256_file(test_file)
    assert len(result) == 64
