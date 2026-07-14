# tests/integration/test_doctor_command.py
import pytest
from click.testing import CliRunner
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
