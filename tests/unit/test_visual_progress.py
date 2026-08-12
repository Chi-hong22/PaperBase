"""可恢复视觉转换推进的外部行为测试。"""

import json
import subprocess
from pathlib import Path

import pymupdf
import pytest

from paperbase.config.models import PdfConversionConfig, VisualPdfConfig
from paperbase.core import pdf_conversion
from paperbase.core.pdf_conversion import (
    AgentActionRequiredOutcome,
    FailedConversionOutcome,
    NeedsConfirmationOutcome,
    ReadyConversionOutcome,
)
from paperbase.core.visual_progress import prepareOrProgressVisualConversion
from paperbase.core.visual_repair_run import acquireRunLease, loadVisualRun, releaseRunLease


def _write_source_pdf(source_pdf: Path, page_count: int = 3) -> None:
    source_pdf.parent.mkdir(parents=True)
    document = pymupdf.open()
    try:
        for page_number in range(1, page_count + 1):
            page = document.new_page()
            page.insert_text((72, 72), f"Source page {page_number}")
        document.save(source_pdf)
    finally:
        document.close()


def _visual_config(retry: int = 1) -> VisualPdfConfig:
    return VisualPdfConfig.model_validate(
        {"mode": "always", "model": "host-model", "chunk_pages": 2, "retry": retry}
    )


def _start_run(tmp_path: Path, *, retry: int = 1) -> tuple[Path, Path, VisualPdfConfig]:
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    _write_source_pdf(source_pdf)
    visual_config = _visual_config(retry)
    outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)
    assert isinstance(outcome, AgentActionRequiredOutcome)
    assert outcome.task_package.parent.name == ".visual-runs"
    return source_pdf, outcome.task_package, visual_config


def _read_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _write_worker_result(
    task_dir: Path,
    *,
    status: str = "completed",
    failure_code: str | None = None,
    warnings: list[str] | None = None,
    crop_requests: list[dict[str, object]] | None = None,
) -> None:
    task = _read_json(task_dir / "task.json")
    run = task["run"]
    chunk = task["chunk"]
    assert isinstance(run, dict)
    assert isinstance(chunk, dict)
    core_pages = chunk["core_pages"]
    assert isinstance(core_pages, list)
    completed = status == "completed"
    result = {
        "schema_version": "visual-chunk-result-v1",
        "run_id": run["run_id"],
        "candidate_sha256": run["candidate_sha256"],
        "chunk_id": chunk["chunk_id"],
        "core_pages": core_pages,
        "status": status,
        "covered_pages": core_pages if completed else [],
        "warnings": warnings or [],
        "unresolved_issues": ["quality issue"] if status == "blocked" else [],
        "failure_code": failure_code,
        "crop_requests": crop_requests or [],
    }
    if completed:
        markdown = "".join(
            f"<!-- paperbase:visual-page-start page={page_number} -->\n"
            f"Page {page_number} content.\n"
            f"<!-- paperbase:visual-page-end page={page_number} -->\n"
            for page_number in core_pages
        )
    else:
        markdown = ""
    (task_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (task_dir / "result.md").write_text(markdown, encoding="utf-8")


def _write_all_completed(run_dir: Path, *, warning_or_crop: bool = False) -> None:
    for index, task_dir in enumerate(sorted((run_dir / "tasks").iterdir())):
        if warning_or_crop and index == 0:
            task = _read_json(task_dir / "task.json")
            chunk = task["chunk"]
            assert isinstance(chunk, dict)
            core_pages = chunk["core_pages"]
            assert isinstance(core_pages, list)
            _write_worker_result(
                task_dir,
                warnings=["Formula crop requires user confirmation."],
                crop_requests=[
                    {"page": core_pages[0], "bbox": [0.1, 0.2, 0.8, 0.9], "kind": "formula"}
                ],
            )
        else:
            _write_worker_result(task_dir)


def _advance_to_boundary(source_pdf: Path, run_dir: Path, visual_config: VisualPdfConfig) -> Path:
    _write_all_completed(run_dir)
    outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)
    assert isinstance(outcome, AgentActionRequiredOutcome)
    assert outcome.task_package == run_dir / "boundary-review"
    return outcome.task_package


def _write_boundary_result(task_package: Path, **changes: object) -> None:
    task = _read_json(task_package / "task.json")
    run = task["run"]
    items = task["items"]
    assert isinstance(run, dict)
    assert isinstance(items, list)
    checked_item_ids = []
    for item in items:
        assert isinstance(item, dict)
        checked_item_ids.append(item["item_id"])
    result = {
        "schema_version": "visual-boundary-review-result-v1",
        "run_id": run["run_id"],
        "candidate_sha256": run["candidate_sha256"],
        "decision": "pass",
        "checked_item_ids": checked_item_ids,
        "affected_chunk_ids": [],
        "unresolved_issues": [],
        "warnings": [],
    }
    result.update(changes)
    (task_package / "result.json").write_text(json.dumps(result), encoding="utf-8")


def _make_junction_or_skip(junction_path: Path, target_path: Path) -> None:
    command = f'mklink /J "{junction_path}" "{target_path}"'
    completed = subprocess.run(
        ["cmd", "/d", "/s", "/c", command],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.skip("当前 Windows 环境不允许创建 junction")


def test_missing_and_partial_worker_outputs_require_action_or_fail_without_retry(tmp_path):
    """两个结果都缺失时交接；只写一个或非法结果时立即失败且不重试。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path)
    missing_outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)
    assert isinstance(missing_outcome, AgentActionRequiredOutcome)
    assert missing_outcome.task_package == run_dir

    first_task = sorted((run_dir / "tasks").iterdir())[0]
    (first_task / "result.json").write_text("{}", encoding="utf-8")
    partial_outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)

    assert isinstance(partial_outcome, FailedConversionOutcome)
    assert partial_outcome.error.code == "visual_worker_result_invalid"
    assert not (run_dir / "attempts").exists()

    invalid_source, invalid_run, invalid_config = _start_run(tmp_path / "invalid")
    invalid_task = sorted((invalid_run / "tasks").iterdir())[0]
    (invalid_task / "result.json").write_text("{}", encoding="utf-8")
    (invalid_task / "result.md").write_text("", encoding="utf-8")
    invalid_outcome = prepareOrProgressVisualConversion(
        invalid_source, "# Candidate\n", invalid_config
    )

    assert isinstance(invalid_outcome, FailedConversionOutcome)
    assert invalid_outcome.error.code == "visual_worker_result_invalid"
    assert not (invalid_run / "attempts").exists()


def test_completed_chunks_progress_to_boundary_pass_ready_and_remain_idempotent(tmp_path):
    """所有块完成后先交给 Boundary；仅 pass 才进入 ready_to_adopt 且重复不重做。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path)
    boundary_package = _advance_to_boundary(source_pdf, run_dir, visual_config)
    assert loadVisualRun(run_dir).state == "running"
    _write_boundary_result(boundary_package)

    ready_outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)
    repeated_outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)

    assert isinstance(ready_outcome, ReadyConversionOutcome)
    assert ready_outcome.markdown == "Page 1 content.\nPage 2 content.\nPage 3 content.\n"
    assert isinstance(repeated_outcome, ReadyConversionOutcome)
    assert repeated_outcome == ready_outcome
    assert loadVisualRun(run_dir).state == "ready_to_adopt"
    assert all(chunk.state == "completed" for chunk in loadVisualRun(run_dir).chunks.values())


@pytest.mark.parametrize(
    "unsafe_fragment",
    ["\x01", "\ufffd", r"\n", r"\r", r"\t"],
    ids=["c0-control", "replacement-character", "literal-n", "literal-r", "literal-t"],
)
def test_boundary_pass_rejects_unsafe_full_document_markdown(tmp_path, unsafe_fragment):
    """Boundary pass 不能绕过最终合并 Markdown 的确定性全文卫生门。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path)
    _write_all_completed(run_dir)
    first_result = run_dir / "tasks" / "chunk-001" / "result.md"
    result_markdown = first_result.read_text(encoding="utf-8")
    first_result.write_text(
        result_markdown.replace(
            "Page 1 content.",
            f"Page 1 content.\n\n{unsafe_fragment}\n",
        ),
        encoding="utf-8",
    )
    boundary_outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)
    assert isinstance(boundary_outcome, AgentActionRequiredOutcome)
    _write_boundary_result(boundary_outcome.task_package)

    outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)

    assert isinstance(outcome, FailedConversionOutcome)
    assert outcome.error.code == "visual_quality_blocked"
    assert loadVisualRun(run_dir).state != "ready_to_adopt"


def test_explicit_warning_acceptance_adopts_real_run_and_remains_idempotent(tmp_path):
    """显式确认后采用真实 warning/crop 运行；重复确认不得重做或失败。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path)
    _write_all_completed(run_dir, warning_or_crop=True)
    boundary_package = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)
    assert isinstance(boundary_package, AgentActionRequiredOutcome)
    _write_boundary_result(boundary_package.task_package)

    first_outcome = prepareOrProgressVisualConversion(
        source_pdf,
        "# Candidate\n",
        visual_config,
        accept_visual_warnings=True,
    )
    repeated_outcome = prepareOrProgressVisualConversion(
        source_pdf,
        "# Candidate\n",
        visual_config,
        accept_visual_warnings=True,
    )

    assert isinstance(first_outcome, ReadyConversionOutcome)
    assert first_outcome.assets == ("./assets/visual-page-0001-formula-01.png",)
    assert "./assets/visual-page-0001-formula-01.png" in first_outcome.markdown
    assert (source_pdf.parent.parent / "assets" / "visual-page-0001-formula-01.png").is_file()
    assert repeated_outcome == first_outcome
    assert loadVisualRun(run_dir).state == "ready_to_adopt"


def test_retryable_failure_archives_once_then_exhausts_same_run(tmp_path):
    """retry=1 首次归档并续作；第二次同一临时错误必须耗尽而不新建运行。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path, retry=1)
    first_task = sorted((run_dir / "tasks").iterdir())[0]
    _write_worker_result(first_task, status="retryable_failure", failure_code="timeout")

    first_outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)
    first_run = loadVisualRun(run_dir)
    attempt_dir = run_dir / "attempts" / first_task.name / "retry-001"
    assert isinstance(first_outcome, AgentActionRequiredOutcome)
    assert first_outcome.task_package == run_dir
    assert first_run.chunks[first_task.name].state == "pending"
    assert first_run.chunks[first_task.name].retry_count == 1
    assert (attempt_dir / "result.md").is_file()
    assert (attempt_dir / "result.json").is_file()
    assert not (first_task / "result.md").exists()
    assert not (first_task / "result.json").exists()

    _write_worker_result(first_task, status="retryable_failure", failure_code="timeout")
    exhausted_outcome = prepareOrProgressVisualConversion(
        source_pdf, "# Candidate\n", visual_config
    )

    assert isinstance(exhausted_outcome, FailedConversionOutcome)
    assert exhausted_outcome.error.code == "visual_transient_failure_exhausted"
    assert exhausted_outcome.error.code != "visual_worker_result_invalid"
    assert [path.name for path in run_dir.parent.glob("*/run.json")] == ["run.json"]


def test_retry_archive_restores_complete_pair_if_second_unlink_fails(tmp_path, monkeypatch):
    """归档发布后第二个删除失败时，任务目录必须恢复完整且字节一致的结果对。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path, retry=1)
    task_dir = sorted((run_dir / "tasks").iterdir())[0]
    _write_worker_result(task_dir, status="retryable_failure", failure_code="timeout")
    result_markdown = task_dir / "result.md"
    result_json = task_dir / "result.json"
    original_markdown = result_markdown.read_bytes()
    original_json = result_json.read_bytes()
    original_unlink = Path.unlink

    def fail_after_actual_json_delete(path, *args, **kwargs):
        if path == result_json:
            original_unlink(path, *args, **kwargs)
            raise OSError("simulated result.json unlink failure after deletion")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_after_actual_json_delete)
    outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)

    attempt_dir = run_dir / "attempts" / task_dir.name / "retry-001"
    assert isinstance(outcome, FailedConversionOutcome)
    assert outcome.error.code == "visual_progress_failed"
    assert result_markdown.read_bytes() == original_markdown
    assert result_json.read_bytes() == original_json
    assert (attempt_dir / "result.md").read_bytes() == original_markdown
    assert (attempt_dir / "result.json").read_bytes() == original_json


def test_retry_rejects_junctioned_attempts_directory_when_supported(tmp_path):
    """attempts 根目录为 Windows junction 时不得向外部目标发布或删除结果。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path, retry=1)
    task_dir = sorted((run_dir / "tasks").iterdir())[0]
    _write_worker_result(task_dir, status="retryable_failure", failure_code="timeout")
    attempts_path = run_dir / "attempts"
    external_attempts = tmp_path / "external-attempts"
    external_attempts.mkdir()
    _make_junction_or_skip(attempts_path, external_attempts)

    try:
        outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)
    finally:
        if attempts_path.exists():
            attempts_path.rmdir()

    assert isinstance(outcome, FailedConversionOutcome)
    assert outcome.error.code == "visual_progress_failed"
    assert not list(external_attempts.rglob("result.*"))
    assert (task_dir / "result.md").is_file()
    assert (task_dir / "result.json").is_file()


def test_retry_zero_and_blocked_result_do_not_retry(tmp_path):
    """retry=0 与 worker 阻塞都不能归档后重试。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path / "retry-zero", retry=0)
    first_task = sorted((run_dir / "tasks").iterdir())[0]
    _write_worker_result(first_task, status="retryable_failure", failure_code="timeout")

    retry_zero_outcome = prepareOrProgressVisualConversion(
        source_pdf, "# Candidate\n", visual_config
    )
    assert isinstance(retry_zero_outcome, FailedConversionOutcome)
    assert retry_zero_outcome.error.code == "visual_transient_failure_exhausted"
    assert not (run_dir / "attempts").exists()

    blocked_source, blocked_run, blocked_config = _start_run(tmp_path / "blocked")
    blocked_task = sorted((blocked_run / "tasks").iterdir())[0]
    _write_worker_result(blocked_task, status="blocked")
    blocked_outcome = prepareOrProgressVisualConversion(
        blocked_source, "# Candidate\n", blocked_config
    )
    assert isinstance(blocked_outcome, FailedConversionOutcome)
    assert blocked_outcome.error.code == "visual_quality_blocked"
    assert not (blocked_run / "attempts").exists()


def test_active_host_lease_returns_action_without_altering_run(tmp_path):
    """有效的其他 Host Lease 必须保留运行现场，不得强占或状态迁移。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path)
    before = (run_dir / "run.json").read_bytes()
    lease = acquireRunLease(run_dir, "other-host", 30)
    try:
        outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)
    finally:
        releaseRunLease(run_dir, lease)

    assert isinstance(outcome, AgentActionRequiredOutcome)
    assert outcome.task_package == run_dir
    assert (run_dir / "run.json").read_bytes() == before


@pytest.mark.parametrize(
    ("decision", "changes", "expected_code"),
    [
        ("blocked", {"unresolved_issues": ["ambiguous formula"]}, "visual_quality_blocked"),
        ("pass", {"unknown": "schema drift"}, "visual_boundary_review_invalid"),
    ],
    ids=["boundary_blocked", "boundary_invalid"],
)
def test_boundary_blocked_or_invalid_never_marks_run_ready(
    tmp_path, decision, changes, expected_code
):
    """Boundary blocked 或非法结果必须失败，且不能把运行标成 ready_to_adopt。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path)
    boundary_package = _advance_to_boundary(source_pdf, run_dir, visual_config)
    _write_boundary_result(boundary_package, decision=decision, **changes)

    outcome = prepareOrProgressVisualConversion(
        source_pdf,
        "# Candidate\n",
        visual_config,
        accept_visual_warnings=True,
    )

    assert isinstance(outcome, FailedConversionOutcome)
    assert outcome.error.code == expected_code
    assert loadVisualRun(run_dir).state != "ready_to_adopt"


def test_boundary_rework_requeues_only_affected_completed_chunk(tmp_path):
    """rework 仅归档并回退被点名完成块，其他块结果保持可复用。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path)
    boundary_package = _advance_to_boundary(source_pdf, run_dir, visual_config)
    _write_boundary_result(
        boundary_package,
        decision="rework_required",
        affected_chunk_ids=["chunk-001"],
        unresolved_issues=["The first seam must be repaired."],
    )
    unaffected_result = (run_dir / "tasks" / "chunk-002" / "result.json").read_bytes()

    outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)
    run = loadVisualRun(run_dir)

    assert isinstance(outcome, AgentActionRequiredOutcome)
    assert outcome.task_package == run_dir
    assert run.chunks["chunk-001"].state == "pending"
    assert run.chunks["chunk-002"].state == "completed"
    assert not (run_dir / "tasks" / "chunk-001" / "result.json").exists()
    assert (run_dir / "tasks" / "chunk-002" / "result.json").read_bytes() == unaffected_result
    assert (run_dir / "attempts" / "chunk-001" / "rework-001" / "result.json").is_file()
    assert not (run_dir / "boundary-review").exists()


def test_warning_or_crop_returns_confirmation_after_boundary_pass(tmp_path):
    """worker warning/crop 在 Boundary pass 后仍必须进入人工确认，不能自动 Ready。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path)
    _write_all_completed(run_dir, warning_or_crop=True)
    boundary_outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)
    assert isinstance(boundary_outcome, AgentActionRequiredOutcome)
    _write_boundary_result(boundary_outcome.task_package)

    outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)

    assert isinstance(outcome, NeedsConfirmationOutcome)
    assert outcome.warnings
    assert loadVisualRun(run_dir).state == "ready_to_adopt"


def test_legacy_run_chunk_without_retry_count_loads_as_zero(tmp_path):
    """旧 run.json 没有 retry_count 时仍能加载，并默认从零开始计数。"""
    _, run_dir, _ = _start_run(tmp_path)
    run_data = _read_json(run_dir / "run.json")
    chunks = run_data["chunks"]
    assert isinstance(chunks, dict)
    for chunk in chunks.values():
        assert isinstance(chunk, dict)
        chunk.pop("retry_count", None)
    (run_dir / "run.json").write_text(json.dumps(run_data), encoding="utf-8")

    loaded = loadVisualRun(run_dir)

    assert all(chunk.retry_count == 0 for chunk in loaded.chunks.values())


def test_pdf_conversion_routes_always_to_progress_auto_to_audit_while_off_stays_local(monkeypatch):
    """always 进入 visual progress，auto 原样返回 audit 推进结果，off 保持回归。"""
    source_pdf = Path("paper.pdf")
    candidate_markdown = "# Candidate\n"
    progress_outcome = AgentActionRequiredOutcome(Path(".visual-runs") / "run-one")
    calls = []
    monkeypatch.setattr(pdf_conversion, "convert_pdf_to_markdown", lambda _: candidate_markdown)

    def fake_progress(actual_source, actual_candidate, actual_visual_config):
        calls.append((actual_source, actual_candidate, actual_visual_config.mode))
        return progress_outcome

    monkeypatch.setattr(pdf_conversion, "prepareOrProgressVisualConversion", fake_progress)
    always_config = PdfConversionConfig.model_validate(
        {"visual": {"mode": "always", "model": "host-model"}}
    )
    always_outcome = pdf_conversion.progressPdfConversion(source_pdf, always_config)

    expected_auto_outcome = AgentActionRequiredOutcome(
        Path("paper") / ".visual-auto-audit" / "audit-one"
    )
    audit_calls = []

    def fake_auto_audit(actual_source, actual_candidate, actual_visual_config):
        audit_calls.append((actual_source, actual_candidate, actual_visual_config.mode))
        return expected_auto_outcome

    monkeypatch.setattr(pdf_conversion, "prepareOrProgressPdfAutoAudit", fake_auto_audit)
    auto_config = PdfConversionConfig.model_validate(
        {"visual": {"mode": "auto", "model": "host-model"}}
    )
    auto_outcome = pdf_conversion.progressPdfConversion(source_pdf, auto_config)
    off_outcome = pdf_conversion.progressPdfConversion(source_pdf, PdfConversionConfig())

    assert always_outcome is progress_outcome
    assert auto_outcome is expected_auto_outcome
    assert calls == [
        (source_pdf, candidate_markdown, "always"),
    ]
    assert audit_calls == [(source_pdf, candidate_markdown, "auto")]
    assert isinstance(off_outcome, ReadyConversionOutcome)
    assert off_outcome.markdown == candidate_markdown
