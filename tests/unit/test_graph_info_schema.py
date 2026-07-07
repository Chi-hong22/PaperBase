"""测试 GraphInfo Schema 扩展"""

import pytest
from paperbase.schemas.manifest import GraphInfo


def test_graph_info_with_content_sha256():
    """测试 GraphInfo 记录内容 SHA256"""
    info = GraphInfo(
        indexed=True,
        updated_at="2026-07-07T10:30:00Z",
        content_sha256_at_index="a" * 64
    )

    assert info.indexed is True
    assert info.content_sha256_at_index == "a" * 64


def test_graph_info_backward_compatible():
    """测试向后兼容：旧 manifest 无 content_sha256_at_index"""
    info = GraphInfo(
        indexed=True,
        updated_at="2026-07-07T10:30:00Z"
    )

    assert info.content_sha256_at_index is None
