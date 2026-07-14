# tests/integration/test_doctor_command.py
import pytest
from click.testing import CliRunner
from paperbase.cli.commands.doctor import check_canonical_asset_paths, check_graph, check_llm_config
from paperbase.cli.main import main
from paperbase.core.paths import PaperPaths
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState


def test_doctor_command_runs():
    """doctor 命令应该能正常运行"""
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])

    assert result.exit_code == 0 or result.exit_code == 1  # 可能因为缺少依赖而失败
    assert "检查" in result.output or "Doctor" in result.output or "PaperBase" in result.output


def test_doctor_checks_python():
    """应该检查 Python 版本"""
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])

    assert "Python" in result.output


def test_doctor_provides_suggestions():
    """应该提供建议或诊断信息"""
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])

    # 应该有某种状态指示
    assert "✅" in result.output or "❌" in result.output or "⚠️" in result.output


def test_doctor_uses_explicit_base_dir(tmp_path):
    result = CliRunner().invoke(main, ["--base-dir", str(tmp_path), "doctor"])

    assert result.exit_code == 1
    assert "Library not found" in result.output
    assert "Registry database not found" in result.output
    assert "Knowledge graph not found" in result.output


def test_doctor_llm_check_uses_target_base_dir_config(monkeypatch, tmp_path):
    cwd_dir = tmp_path / "cwd"
    target_dir = tmp_path / "target"
    for base_dir, model in [(cwd_dir, "cwd-model"), (target_dir, "target-model")]:
        config_dir = base_dir / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "paperbase.yaml").write_text(
            f"llm:\n  base_url: https://example.test/v1\n  model: {model}\n",
            encoding="utf-8",
        )

    monkeypatch.chdir(cwd_dir)

    passed, message = check_llm_config(target_dir)

    assert passed is True
    assert message == "enabled (target-model)"


def test_doctor_graph_check_requires_valid_graph_json(tmp_path):
    passed, _ = check_graph(tmp_path)
    assert passed is False

    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    passed, _ = check_graph(tmp_path)
    assert passed is False

    (graph_dir / "other.json").write_text("{}", encoding="utf-8")
    passed, _ = check_graph(tmp_path)
    assert passed is False

    graph_json = graph_dir / "graph.json"
    graph_json.write_text("{invalid", encoding="utf-8")
    passed, _ = check_graph(tmp_path)
    assert passed is False

    graph_json.write_text('{"nodes": [], "links": []}', encoding="utf-8")
    passed, message = check_graph(tmp_path)
    assert passed is True
    assert message == "Knowledge graph found (graph.json)"


def test_doctor_rejects_machine_local_asset_paths(tmp_path):
    papers_dir = tmp_path / "library" / "papers"
    papers_dir.mkdir(parents=True)
    paper_path = papers_dir / "p_example.md"
    paper_path.write_text(
        "---\ntitle: Example\n---\n\n![Figure](C:\\Temp\\figure.png)\n",
        encoding="utf-8",
    )

    passed, message = check_canonical_asset_paths(tmp_path)

    assert passed is False
    assert "1 files" in message

    paper_path.write_text(
        "---\ntitle: Example\n---\n\n![Figure](./assets/figure.png)\n",
        encoding="utf-8",
    )

    passed, message = check_canonical_asset_paths(tmp_path)

    assert passed is True
    assert message == "Canonical Markdown asset paths are portable"

    paper_path.write_text(
        "---\ntitle: Example\n---\n\n![Figure](https://example.org/figure.png)\n",
        encoding="utf-8",
    )

    passed, _ = check_canonical_asset_paths(tmp_path)

    assert passed is True


@pytest.mark.parametrize("target", ["/tmp/figure.png", r"\assets\figure.png"])
def test_doctor_rejects_cross_platform_local_asset_paths(tmp_path, target):
    papers_dir = tmp_path / "library" / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "p_example.md").write_text(
        f"---\ntitle: Example\n---\n\n![Figure]({target})\n",
        encoding="utf-8",
    )

    passed, _ = check_canonical_asset_paths(tmp_path)

    assert passed is False


def test_doctor_reports_registry_and_canonical_mismatches(tmp_path):
    canonical_paths = PaperPaths(storage_id="p_present0001", base_dir=tmp_path)
    canonical_paths.paper_md.parent.mkdir(parents=True)
    canonical_paths.paper_md.write_text("# Unregistered canonical", encoding="utf-8")

    registry_path = tmp_path / "registry" / "papers.db"
    registry_path.parent.mkdir()
    with PaperRegistry(registry_path) as registry:
        registry.register_paper(
            paper_id="doi:10.1234/missing",
            storage_id="p_missing0001",
            state=PaperState.NORMALIZED,
            title="Missing canonical",
        )

    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(main, ["--base-dir", str(tmp_path), "doctor"])

    assert result.exit_code == 1
    assert "Canonical not registered: 1" in result.output
    assert "Registry missing canonical: 1" in result.output
    assert "All required checks passed" not in result.output
