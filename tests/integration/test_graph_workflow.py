"""图谱工作流集成测试"""

import json
import pytest
from pathlib import Path
from click.testing import CliRunner

from paperbase.adapters.graphify_adapter import check_graphify_installed
from paperbase.cli.main import main
from paperbase.core.manifest import load_manifest, save_manifest
from paperbase.core.paths import PaperPaths
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState


@pytest.fixture
def skip_if_no_graphify():
    """如果 graphify 未安装，跳过测试"""
    if not check_graphify_installed():
        pytest.skip("graphify 未安装，跳过集成测试")


def test_graphify_installed(skip_if_no_graphify):
    """测试 graphify 是否可用"""
    from paperbase.adapters.graphify_adapter import check_graphify_installed
    assert check_graphify_installed() is True


def test_graph_workflow_end_to_end(monkeypatch, tmp_path):
    """真实摄入 PDF，并用确定性 Graphify 边界验证状态投影。"""
    pdf_path = Path(__file__).parents[1] / "fixtures" / "sample_liu2025.pdf"
    graphify_calls = []

    def fake_run_graphify(
        library_dir,
        graph_dir,
        force_rebuild,
        llm_config,
        process_timeout,
        api_timeout,
    ):
        graphify_calls.append(library_dir)
        assert library_dir == tmp_path / "library"
        assert graph_dir == tmp_path / "graph"
        assert process_timeout is None
        assert api_timeout == 600
        graph_dir.mkdir(parents=True, exist_ok=True)
        (graph_dir / "graph.json").write_text(
            json.dumps(
                {
                    "directed": False,
                    "multigraph": False,
                    "graph": {},
                    "nodes": [],
                    "links": [],
                }
            ),
            encoding="utf-8",
        )
        return {"success": True, "output": "", "error": None}

    monkeypatch.setattr("paperbase.cli.commands.graph.run_graphify", fake_run_graphify)

    runner = CliRunner()
    ingest_result = runner.invoke(
        main,
        ["--base-dir", str(tmp_path), "ingest", "--file", str(pdf_path), "--no-graph"],
    )
    assert ingest_result.exit_code == 0, ingest_result.output

    graph_result = runner.invoke(
        main,
        ["--base-dir", str(tmp_path), "graph", "update"],
    )
    assert graph_result.exit_code == 0, graph_result.output

    with PaperRegistry(tmp_path / "registry" / "papers.db") as registry:
        papers = registry.list_papers()
        assert len(papers) == 1
        registered = registry.get_paper(papers[0]["paper_id"])

    paths = PaperPaths(storage_id=registered["storage_id"], base_dir=tmp_path)
    manifest = load_manifest(paths.manifest_json)
    assert manifest.state == PaperState.READY
    assert manifest.graph is not None
    assert manifest.graph.indexed is True
    assert registered["state"] == PaperState.READY.value
    assert (tmp_path / "graph" / "graph.json").exists()

    manifest.canonical_md.sha256 = "changed-canonical-sha256"
    save_manifest(manifest, paths.manifest_json)
    incremental_result = runner.invoke(
        main,
        ["--base-dir", str(tmp_path), "graph", "update", "--incremental"],
    )

    assert incremental_result.exit_code == 0, incremental_result.output
    assert "检测到 1 篇论文有更新" in incremental_result.output
    assert "已索引: 1 篇论文" in incremental_result.output
    assert graphify_calls == [tmp_path / "library", tmp_path / "library"]

    refreshed_manifest = load_manifest(paths.manifest_json)
    assert refreshed_manifest.graph.content_sha256_at_index == "changed-canonical-sha256"


def test_graph_adopt_projects_agent_output_without_running_headless(monkeypatch, tmp_path):
    """Agent 先生成 graphify-out，PaperBase 只做确定性投影。"""
    pdf_path = Path(__file__).parents[1] / "fixtures" / "sample_liu2025.pdf"
    runner = CliRunner()

    ingest_result = runner.invoke(
        main,
        ["--base-dir", str(tmp_path), "ingest", "--file", str(pdf_path), "--no-graph"],
    )
    assert ingest_result.exit_code == 0, ingest_result.output

    papers_dir = tmp_path / "library" / "papers"
    graphify_out = papers_dir / "graphify-out"
    graphify_out.mkdir()
    (graphify_out / "graph.json").write_text(
        json.dumps({"nodes": [{"id": "agent"}], "links": []}),
        encoding="utf-8",
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("adopt 不应调用 headless graphify")

    monkeypatch.setattr("paperbase.cli.commands.graph.run_graphify", fail_if_called)

    adopt_result = runner.invoke(
        main,
        ["--base-dir", str(tmp_path), "graph", "adopt"],
    )

    assert adopt_result.exit_code == 0, adopt_result.output
    assert "已接纳 Graphify Agent 图谱" in adopt_result.output
    assert (tmp_path / "graph" / "graph.json").exists()
