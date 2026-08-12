"""Visual PDF diagnostics exposed through the ordinary doctor command."""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
from pathlib import Path

import pytest
from click.testing import CliRunner

from paperbase.cli.commands.doctor import checkVisualPdfConfig, checkVisualRuns
from paperbase.cli.main import main
from paperbase.core.visual_repair_run import prepareVisualRun

SOURCE_SHA = "a" * 64


def _write_config(base_dir: Path, visual_yaml: str) -> None:
    config_dir = base_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "paperbase.yaml").write_text(
        f"conversion:\n  pdf:\n    visual:\n{visual_yaml}",
        encoding="utf-8",
    )


def _write_run(base_dir: Path, run_id: str, state: str) -> Path:
    paper_dir = base_dir / "library" / "papers" / "p_visualtest"
    run = prepareVisualRun(
        paper_dir,
        SOURCE_SHA,
        hashlib.sha256(run_id.encode("utf-8")).hexdigest(),
        "visual-v1",
        {"chunk_pages": 3},
        run_id_factory=lambda: run_id,
    )
    run_dir = paper_dir / ".visual-runs" / run.run_id
    run_data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    run_data["state"] = state
    (run_dir / "run.json").write_text(
        json.dumps(run_data),
        encoding="utf-8",
    )
    return run_dir


def test_visual_pdf_config_reports_off_and_empty_model(tmp_path):
    _write_config(tmp_path, "      mode: 'off'\n")

    passed, message = checkVisualPdfConfig(tmp_path)

    assert passed is True
    assert "disabled" in message

    _write_config(tmp_path, "      mode: always\n      model: ''\n")
    passed, message = checkVisualPdfConfig(tmp_path)

    assert passed is False
    assert "non-empty model" in message


def test_visual_pdf_config_reports_host_validation_boundary(tmp_path):
    _write_config(
        tmp_path,
        "      mode: always\n      model: host-selected-model\n"
        "      chunk_pages: 3\n      retry: 1\n",
    )

    passed, message = checkVisualPdfConfig(tmp_path)

    assert passed is True
    assert "mode=always" in message
    assert "chunk_pages=3" in message
    assert "Agent Host" in message
    assert "does not call vendor APIs or a local LLM" in message


def test_visual_pdf_config_reports_invalid_config(tmp_path):
    _write_config(tmp_path, "      mode: unsupported\n")

    passed, message = checkVisualPdfConfig(tmp_path)

    assert passed is False
    assert "configuration is invalid" in message.lower()


def test_visual_runs_summarizes_each_state_without_mutating_runs(tmp_path):
    run_dirs = [
        _write_run(tmp_path, "run-prepared", "prepared"),
        _write_run(tmp_path, "run-running", "running"),
        _write_run(tmp_path, "run-failed", "failed"),
        _write_run(tmp_path, "run-ready", "ready_to_adopt"),
    ]
    before = [(run_dir / "run.json").read_bytes() for run_dir in run_dirs]

    passed, message = checkVisualRuns(tmp_path)

    assert passed is False
    assert "prepared=1" in message
    assert "running=1" in message
    assert "failed=1" in message
    assert "ready_to_adopt=1" in message
    assert [(run_dir / "run.json").read_bytes() for run_dir in run_dirs] == before


def test_visual_runs_reports_invalid_json_and_reparse_points(tmp_path):
    bad_run = tmp_path / "library" / "papers" / "p_bad" / ".visual-runs" / "bad-run"
    bad_run.mkdir(parents=True)
    (bad_run / "run.json").write_text("{not-json", encoding="utf-8")

    passed, message = checkVisualRuns(tmp_path)

    assert passed is False
    assert "run is invalid" in message.lower()

    shutil.rmtree(bad_run.parent.parent)
    target_dir = tmp_path / "reparse-target"
    target_dir.mkdir()
    runs_root = tmp_path / "library" / "papers" / "p_link" / ".visual-runs"
    runs_root.parent.mkdir(parents=True)
    try:
        runs_root.symlink_to(target_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic-link creation is unavailable in this environment")

    passed, message = checkVisualRuns(tmp_path)

    assert passed is False
    assert "unsafe" in message.lower()


def test_doctor_includes_visual_checks_without_network_calls(monkeypatch, tmp_path):
    _write_config(tmp_path, "      mode: 'off'\n")

    def fail_network(*args, **kwargs):
        raise AssertionError("doctor must not call a model network")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    result = CliRunner().invoke(main, ["--base-dir", str(tmp_path), "doctor"])

    assert result.exit_code == 1
    assert "Visual PDF Configuration" in result.output
    assert "Visual PDF Runs" in result.output
    assert "disabled (mode=off)" in result.output
