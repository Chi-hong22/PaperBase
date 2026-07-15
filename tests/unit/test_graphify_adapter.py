import json

import pytest
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired

import paperbase.adapters.graphify_adapter as graphify_adapter
from paperbase.adapters.graphify_adapter import (
    adopt_graphify_output,
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


def test_incremental_run_preserves_graphify_cache(tmp_path, monkeypatch):
    library_dir = tmp_path / "library"
    papers_dir = library_dir / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "p_example.md").write_text("# Example", encoding="utf-8")

    graphify_out = papers_dir / "graphify-out"
    semantic_cache = graphify_out / "cache" / "semantic"
    semantic_cache.mkdir(parents=True)
    cache_entry = semantic_cache / "cached.json"
    cache_entry.write_text('{"nodes": []}', encoding="utf-8")

    def successful_run(cmd, **kwargs):
        (graphify_out / "graph.json").write_text('{"version": "new"}', encoding="utf-8")
        return CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(graphify_adapter, "check_graphify_installed", lambda: True)
    monkeypatch.setattr(graphify_adapter.subprocess, "run", successful_run)

    result = run_graphify(library_dir, tmp_path / "graph")

    assert result["success"] is True
    assert cache_entry.exists()
    assert (graphify_out / "graph.json").exists()


def test_run_graphify_passes_configured_timeouts(tmp_path, monkeypatch):
    library_dir = tmp_path / "library"
    papers_dir = library_dir / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "p_example.md").write_text("# Example", encoding="utf-8")

    observed = {}

    def successful_run(cmd, **kwargs):
        observed["cmd"] = cmd
        observed["timeout"] = kwargs["timeout"]
        output_dir = Path(kwargs["cwd"]) / "graphify-out"
        output_dir.mkdir()
        (output_dir / "graph.json").write_text('{"version": "new"}', encoding="utf-8")
        return CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(graphify_adapter, "check_graphify_installed", lambda: True)
    monkeypatch.setattr(graphify_adapter.subprocess, "run", successful_run)

    result = run_graphify(
        library_dir,
        tmp_path / "graph",
        process_timeout=900,
        api_timeout=120,
    )

    assert result["success"] is True
    assert observed["timeout"] == 900
    assert observed["cmd"][-2:] == ["--api-timeout", "120"]


def test_run_graphify_has_no_default_process_timeout(tmp_path, monkeypatch):
    library_dir = tmp_path / "library"
    papers_dir = library_dir / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "p_example.md").write_text("# Example", encoding="utf-8")

    observed = {}

    def successful_run(cmd, **kwargs):
        observed["timeout"] = kwargs["timeout"]
        output_dir = Path(kwargs["cwd"]) / "graphify-out"
        output_dir.mkdir()
        (output_dir / "graph.json").write_text('{"version": "new"}', encoding="utf-8")
        return CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(graphify_adapter, "check_graphify_installed", lambda: True)
    monkeypatch.setattr(graphify_adapter.subprocess, "run", successful_run)

    result = run_graphify(library_dir, tmp_path / "graph")

    assert result["success"] is True
    assert observed["timeout"] is None


def test_run_graphify_reports_configured_process_timeout(tmp_path, monkeypatch):
    library_dir = tmp_path / "library"
    papers_dir = library_dir / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "p_example.md").write_text("# Example", encoding="utf-8")

    def timed_out(cmd, **kwargs):
        raise TimeoutExpired(cmd, kwargs["timeout"], output="partial output")

    monkeypatch.setattr(graphify_adapter, "check_graphify_installed", lambda: True)
    monkeypatch.setattr(graphify_adapter.subprocess, "run", timed_out)

    result = run_graphify(library_dir, tmp_path / "graph", process_timeout=900)

    assert result["success"] is False
    assert result["output"] == "partial output"
    assert "900 秒" in result["error"]


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


def test_success_without_graph_json_is_failure(tmp_path, monkeypatch):
    library_dir = tmp_path / "library"
    papers_dir = library_dir / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "p_example.md").write_text("# Example", encoding="utf-8")

    stale_output = papers_dir / "graphify-out"
    stale_cache = stale_output / "cache" / "semantic"
    stale_cache.mkdir(parents=True)
    (stale_cache / "cached.json").write_text('{"nodes": []}', encoding="utf-8")

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

    result = run_graphify(library_dir, graph_dir, force_rebuild=False)

    assert result["success"] is False
    assert "graph.json" in result["error"]
    assert sentinel.read_text(encoding="utf-8") == '{"version": "old"}'
    assert stale_output.exists()


def test_adopt_graphify_output_preserves_source_cache(tmp_path):
    library_dir = tmp_path / "library"
    graphify_out = library_dir / "papers" / "graphify-out"
    cache_dir = graphify_out / "cache" / "semantic"
    cache_dir.mkdir(parents=True)
    (graphify_out / "graph.json").write_text('{"version": "agent"}', encoding="utf-8")
    (cache_dir / "cached.json").write_text('{"nodes": []}', encoding="utf-8")

    graph_dir = tmp_path / "graph"
    result = adopt_graphify_output(library_dir, graph_dir)

    assert result["success"] is True
    assert (graph_dir / "graph.json").read_text(encoding="utf-8") == '{"version": "agent"}'
    assert (cache_dir / "cached.json").exists()


@pytest.mark.parametrize(
    ("source_file", "source_location"),
    [
        ("p_example/source/source.pdf", "page 3"),
        ("p_example.md", "external_pdf:p3:method"),
    ],
)
def test_adopt_rejects_noncanonical_graph_sources(
    tmp_path,
    source_file,
    source_location,
):
    library_dir = tmp_path / "library"
    papers_dir = library_dir / "papers"
    graphify_out = papers_dir / "graphify-out"
    graphify_out.mkdir(parents=True)
    (papers_dir / "p_example.md").write_text("# Canonical", encoding="utf-8")
    (graphify_out / "graph.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "p_example_method",
                        "source_file": source_file,
                        "source_location": source_location,
                    }
                ],
                "links": [],
            }
        ),
        encoding="utf-8",
    )

    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    sentinel = graph_dir / "sentinel.json"
    sentinel.write_text('{"version": "old"}', encoding="utf-8")

    result = adopt_graphify_output(library_dir, graph_dir)

    assert result["success"] is False
    assert "Canonical Markdown" in result["error"]
    assert sentinel.read_text(encoding="utf-8") == '{"version": "old"}'
