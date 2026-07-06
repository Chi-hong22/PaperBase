import pytest
from pathlib import Path
from paperbase.adapters.graphify_adapter import (
    check_graphify_installed,
    run_graphify,
)


def test_check_graphify_installed():
    """测试 graphify 是否已安装"""
    result = check_graphify_installed()
    assert isinstance(result, bool)
    # 如果未安装，测试应提示用户安装
    if not result:
        pytest.skip("graphify 未安装，跳过测试")


def test_run_graphify_invalid_directory(tmp_path):
    """测试无效目录处理"""
    nonexistent = tmp_path / "nonexistent"
    result = run_graphify(
        library_dir=nonexistent,
        graph_dir=tmp_path / "graph"
    )

    assert result["success"] is False
    assert result["error"] is not None


def test_run_graphify_empty_library(tmp_path):
    """测试空库处理"""
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    graph_dir = tmp_path / "graph"

    result = run_graphify(
        library_dir=library_dir,
        graph_dir=graph_dir
    )

    # 空库会失败，因为 graphify 要求至少有一个节点
    assert result["success"] is False
    assert "empty" in result["error"].lower() or "no nodes" in result["error"].lower()
