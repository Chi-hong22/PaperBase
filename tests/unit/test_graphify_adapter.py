import pytest
from pathlib import Path
from subprocess import CompletedProcess

import paperbase.adapters.graphify_adapter as graphify_adapter
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


def test_force_rebuild_preserves_existing_graph_when_graphify_fails(tmp_path, monkeypatch):
    library_dir = tmp_path / "library"
    papers_dir = library_dir / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "p_example.md").write_text("# Example", encoding="utf-8")

    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    sentinel = graph_dir / "sentinel.json"
    sentinel.write_text('{"version": "old"}', encoding="utf-8")

    monkeypatch.setattr(graphify_adapter, "check_graphify_installed", lambda: True)
    monkeypatch.setattr(
        graphify_adapter.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 1, stdout="", stderr="failed"),
    )

    result = run_graphify(library_dir, graph_dir, force_rebuild=True)

    assert result["success"] is False
    assert sentinel.read_text(encoding="utf-8") == '{"version": "old"}'


def test_successful_rebuild_replaces_existing_graph(tmp_path, monkeypatch):
    library_dir = tmp_path / "library"
    papers_dir = library_dir / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "p_example.md").write_text("# Example", encoding="utf-8")

    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    (graph_dir / "sentinel.json").write_text('{"version": "old"}', encoding="utf-8")

    def successful_run(cmd, **kwargs):
        assert cmd[2] == "."
        assert Path(kwargs["cwd"]) == papers_dir
        output_dir = Path(kwargs["cwd"]) / "graphify-out"
        output_dir.mkdir()
        (output_dir / "graph.json").write_text('{"version": "new"}', encoding="utf-8")
        return CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(graphify_adapter, "check_graphify_installed", lambda: True)
    monkeypatch.setattr(graphify_adapter.subprocess, "run", successful_run)

    result = run_graphify(library_dir, graph_dir, force_rebuild=True)

    assert result["success"] is True
    assert not (graph_dir / "sentinel.json").exists()
    assert (graph_dir / "graph.json").read_text(encoding="utf-8") == '{"version": "new"}'


def test_replacement_failure_preserves_existing_graph(tmp_path, monkeypatch):
    library_dir = tmp_path / "library"
    papers_dir = library_dir / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "p_example.md").write_text("# Example", encoding="utf-8")

    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    sentinel = graph_dir / "sentinel.json"
    sentinel.write_text('{"version": "old"}', encoding="utf-8")

    def successful_run(cmd, **kwargs):
        output_dir = Path(kwargs["cwd"]) / "graphify-out"
        output_dir.mkdir()
        (output_dir / "graph.json").write_text('{"version": "new"}', encoding="utf-8")
        return CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(graphify_adapter, "check_graphify_installed", lambda: True)
    monkeypatch.setattr(graphify_adapter.subprocess, "run", successful_run)
    monkeypatch.setattr(
        graphify_adapter.shutil,
        "copytree",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("copy failed")),
    )

    result = run_graphify(library_dir, graph_dir, force_rebuild=True)

    assert result["success"] is False
    assert sentinel.read_text(encoding="utf-8") == '{"version": "old"}'


def test_post_backup_swap_failure_restores_existing_graph(tmp_path, monkeypatch):
    library_dir = tmp_path / "library"
    papers_dir = library_dir / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "p_example.md").write_text("# Example", encoding="utf-8")

    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    sentinel = graph_dir / "sentinel.json"
    sentinel.write_text('{"version": "old"}', encoding="utf-8")

    def successful_run(cmd, **kwargs):
        output_dir = Path(kwargs["cwd"]) / "graphify-out"
        output_dir.mkdir()
        (output_dir / "graph.json").write_text('{"version": "new"}', encoding="utf-8")
        return CompletedProcess(cmd, 0, stdout="ok", stderr="")

    original_replace = Path.replace

    def fail_staged_replace(path, target):
        if path.name == "new" and Path(target) == graph_dir:
            raise OSError("swap failed after backup")
        return original_replace(path, target)

    monkeypatch.setattr(graphify_adapter, "check_graphify_installed", lambda: True)
    monkeypatch.setattr(graphify_adapter.subprocess, "run", successful_run)
    monkeypatch.setattr(Path, "replace", fail_staged_replace)

    result = run_graphify(library_dir, graph_dir, force_rebuild=True)

    assert result["success"] is False
    assert sentinel.read_text(encoding="utf-8") == '{"version": "old"}'
    assert not list(tmp_path.glob(".graph-swap-*"))


def test_success_without_fresh_graph_json_is_failure(tmp_path, monkeypatch):
    library_dir = tmp_path / "library"
    papers_dir = library_dir / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "p_example.md").write_text("# Example", encoding="utf-8")

    stale_output = papers_dir / "graphify-out"
    stale_output.mkdir()
    (stale_output / "graph.json").write_text('{"version": "stale"}', encoding="utf-8")

    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    sentinel = graph_dir / "sentinel.json"
    sentinel.write_text('{"version": "old"}', encoding="utf-8")

    monkeypatch.setattr(graphify_adapter, "check_graphify_installed", lambda: True)
    monkeypatch.setattr(
        graphify_adapter.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, stdout="ok", stderr=""),
    )

    result = run_graphify(library_dir, graph_dir, force_rebuild=True)

    assert result["success"] is False
    assert "graph.json" in result["error"]
    assert sentinel.read_text(encoding="utf-8") == '{"version": "old"}'
    assert not stale_output.exists()
