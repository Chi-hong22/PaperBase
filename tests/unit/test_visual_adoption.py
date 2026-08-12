"""显式确认后的视觉资产采用与成功运行清理测试。"""

import json
import subprocess
from pathlib import Path

import pytest

from paperbase.core.visual_adoption import (
    VisualAdoptionError,
    adoptConfirmedVisualWarnings,
    cleanupReadyVisualRuns,
)
from paperbase.core.visual_boundary_review import (
    BoundaryReviewActionRequired,
    prepareOrValidateBoundaryReview,
)
from tests.unit.test_visual_fallback_assets import _write_completed_run


def _mark_ready_with_boundary_pass(run_dir: Path) -> None:
    boundary = prepareOrValidateBoundaryReview(run_dir)
    assert isinstance(boundary, BoundaryReviewActionRequired)
    task = json.loads((boundary.task_package / "task.json").read_text(encoding="utf-8"))
    run = task["run"]
    items = task["items"]
    assert isinstance(run, dict)
    assert isinstance(items, list)
    (boundary.task_package / "result.json").write_text(
        json.dumps(
            {
                "schema_version": "visual-boundary-review-result-v1",
                "run_id": run["run_id"],
                "candidate_sha256": run["candidate_sha256"],
                "decision": "pass",
                "checked_item_ids": [item["item_id"] for item in items],
                "affected_chunk_ids": [],
                "unresolved_issues": [],
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )
    run_json = run_dir / "run.json"
    run_data = json.loads(run_json.read_text(encoding="utf-8"))
    run_data["state"] = "ready_to_adopt"
    _add_source_hash(run_data)
    run_json.write_text(json.dumps(run_data), encoding="utf-8")


def _add_source_hash(run_data: dict[str, object]) -> None:
    compatibility = run_data["compatibility"]
    assert isinstance(compatibility, dict)
    compatibility["source_pdf_sha256"] = "a" * 64


def test_confirmed_crop_adoption_copies_byte_exact_asset_without_writing_canonical(tmp_path):
    """确认后只把 run-local 裁剪投影到 paper assets，并返回同一 Markdown 计划。"""
    run_dir = _write_completed_run(
        tmp_path / "paper",
        {"chunk-001": [{"page": 1, "bbox": [0.0, 0.0, 0.5, 0.5], "kind": "formula"}]},
    )
    _mark_ready_with_boundary_pass(run_dir)

    adoption = adoptConfirmedVisualWarnings(run_dir)

    assert adoption.assets == ("./assets/visual-page-0001-formula-01.png",)
    source_asset = run_dir / "fallback-assets" / "visual-page-0001-formula-01.png"
    target_asset = run_dir.parent.parent / "assets" / source_asset.name
    assert target_asset.read_bytes() == source_asset.read_bytes()
    assert "paperbase:visual-page" not in adoption.markdown
    assert "not machine-readable" in adoption.markdown
    assert adoption.warnings
    assert not (run_dir.parent.parent / "library").exists()


def _write_run_record(paper_dir: Path, run_id: str, state: str) -> Path:
    run_dir = paper_dir / ".visual-runs" / run_id
    run_dir.mkdir(parents=True)
    run_dir.joinpath("run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "compatibility": {
                    "source_pdf_sha256": "a" * 64,
                    "candidate_sha256": "b" * 64,
                    "template_version": "visual-v1",
                    "chunking_scheme": {"page_count": 1, "chunks": []},
                },
                "state": state,
                "chunks": {"chunk-001": {"state": "completed", "lease_token": None}},
                "created_at": "2026-08-11T00:00:00+00:00",
                "updated_at": "2026-08-11T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def test_cleanup_removes_only_ready_runs_without_an_active_lease(tmp_path):
    """成功清理只能删除 ready_to_adopt；进行中、失败和活动 lease 现场均须保留。"""
    paper_dir = tmp_path / "paper"
    ready_dir = _write_run_record(paper_dir, "ready", "ready_to_adopt")
    running_dir = _write_run_record(paper_dir, "running", "running")
    failed_dir = _write_run_record(paper_dir, "failed", "failed")
    leased_dir = _write_run_record(paper_dir, "leased", "ready_to_adopt")
    leased_dir.joinpath("lease.json").write_text(
        json.dumps(
            {
                "owner": "active-host",
                "token": "token",
                "acquired_at": "2026-08-11T00:00:00+00:00",
                "expires_at": "2099-08-11T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    note_path = paper_dir / ".visual-runs" / "keep.txt"
    note_path.write_text("keep", encoding="utf-8")

    cleaned = cleanupReadyVisualRuns(paper_dir)

    assert cleaned == ("ready",)
    assert not ready_dir.exists()
    assert running_dir.is_dir()
    assert failed_dir.is_dir()
    assert leased_dir.is_dir()
    assert note_path.is_file()


def test_confirmed_worker_warning_without_crop_returns_no_asset_plan(tmp_path):
    """没有 crop 但已有 worker 警告时，显式确认仍可采用 marker-free Markdown。"""
    run_dir = _write_completed_run(tmp_path / "paper")
    result_path = run_dir / "tasks" / "chunk-001" / "result.json"
    result_data = json.loads(result_path.read_text(encoding="utf-8"))
    result_data["warnings"] = ["layout needs user confirmation"]
    result_path.write_text(json.dumps(result_data), encoding="utf-8")
    _mark_ready_with_boundary_pass(run_dir)

    adoption = adoptConfirmedVisualWarnings(run_dir)

    assert adoption.assets == ()
    assert adoption.warnings == ("layout needs user confirmation",)
    assert "paperbase:visual-page" not in adoption.markdown
    assert not (run_dir.parent.parent / "assets").exists()


def test_adoption_rejects_unready_nonpassing_or_warningless_runs(tmp_path):
    """函数名不替代前置门禁：ready、Boundary pass 和 warning 三者缺一不可。"""
    unready_run = _write_completed_run(tmp_path / "unready")
    unready_data = json.loads((unready_run / "run.json").read_text(encoding="utf-8"))
    _add_source_hash(unready_data)
    (unready_run / "run.json").write_text(json.dumps(unready_data), encoding="utf-8")
    with pytest.raises(VisualAdoptionError, match="ready_to_adopt"):
        adoptConfirmedVisualWarnings(unready_run)

    nonpassing_run = _write_completed_run(tmp_path / "nonpassing")
    _mark_ready_with_boundary_pass(nonpassing_run)
    boundary_path = nonpassing_run / "boundary-review" / "result.json"
    boundary_data = json.loads(boundary_path.read_text(encoding="utf-8"))
    boundary_data.update({"decision": "blocked", "unresolved_issues": ["ambiguous reference tail"]})
    boundary_path.write_text(json.dumps(boundary_data), encoding="utf-8")
    with pytest.raises(VisualAdoptionError, match="Boundary Review"):
        adoptConfirmedVisualWarnings(nonpassing_run)

    warningless_run = _write_completed_run(tmp_path / "warningless")
    _mark_ready_with_boundary_pass(warningless_run)
    with pytest.raises(VisualAdoptionError, match="requires existing"):
        adoptConfirmedVisualWarnings(warningless_run)


def test_same_target_bytes_are_idempotent_but_different_bytes_are_a_conflict(tmp_path):
    """同名目标只能复用同字节内容；不允许确认动作覆盖已有不同资产。"""
    crop_request = {"chunk-001": [{"page": 1, "bbox": [0.0, 0.0, 0.5, 0.5], "kind": "formula"}]}
    run_dir = _write_completed_run(tmp_path / "idempotent", crop_request)
    _mark_ready_with_boundary_pass(run_dir)

    first = adoptConfirmedVisualWarnings(run_dir)
    second = adoptConfirmedVisualWarnings(run_dir)
    assert second == first

    conflict_run = _write_completed_run(tmp_path / "conflict", crop_request)
    _mark_ready_with_boundary_pass(conflict_run)
    target_root = conflict_run.parent.parent / "assets"
    target_root.mkdir()
    (target_root / "visual-page-0001-formula-01.png").write_bytes(b"different bytes")
    with pytest.raises(VisualAdoptionError, match="conflicts"):
        adoptConfirmedVisualWarnings(conflict_run)


def test_reparse_assets_root_is_rejected_when_windows_allows_junction(tmp_path):
    """paper assets junction 不得把确认采用写入 paper 外部。"""
    run_dir = _write_completed_run(
        tmp_path / "paper",
        {"chunk-001": [{"page": 1, "bbox": [0.0, 0.0, 0.5, 0.5], "kind": "formula"}]},
    )
    _mark_ready_with_boundary_pass(run_dir)
    external = tmp_path / "external-assets"
    external.mkdir()
    assets_root = run_dir.parent.parent / "assets"
    creation = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(assets_root), str(external)],
        capture_output=True,
        text=True,
        check=False,
    )
    if creation.returncode != 0:
        pytest.skip("当前 Windows 环境不允许创建 junction")

    with pytest.raises(VisualAdoptionError):
        adoptConfirmedVisualWarnings(run_dir)
