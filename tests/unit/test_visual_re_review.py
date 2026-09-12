"""ready_to_adopt 视觉运行 --re-review 重审入口的外部行为测试。"""

import json
from pathlib import Path

import pymupdf

from paperbase.config.models import PdfConversionConfig, VisualPdfConfig
from paperbase.core import pdf_conversion
from paperbase.core.pdf_conversion import (
    AgentActionRequiredOutcome,
    FailedConversionOutcome,
    NeedsConfirmationOutcome,
)
from paperbase.core.visual_conversion import prepareVisualConversion
from paperbase.core.visual_progress import prepareOrProgressVisualConversion
from paperbase.core.visual_repair_run import loadVisualRun


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


def _visual_config() -> VisualPdfConfig:
    return VisualPdfConfig.model_validate(
        {"mode": "always", "model": "host-model", "chunk_pages": 2, "retry": 1}
    )


def _read_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _write_worker_result(
    task_dir: Path,
    *,
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
    result = {
        "schema_version": "visual-chunk-result-v1",
        "run_id": run["run_id"],
        "candidate_sha256": run["candidate_sha256"],
        "chunk_id": chunk["chunk_id"],
        "core_pages": core_pages,
        "status": "completed",
        "covered_pages": core_pages,
        "warnings": warnings or [],
        "unresolved_issues": [],
        "failure_code": None,
        "crop_requests": crop_requests or [],
    }
    markdown = "".join(
        f"<!-- paperbase:visual-page-start page={page_number} -->\n"
        f"Page {page_number} content.\n"
        f"<!-- paperbase:visual-page-end page={page_number} -->\n"
        for page_number in core_pages
    )
    (task_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (task_dir / "result.md").write_text(markdown, encoding="utf-8")


def _write_all_completed(run_dir: Path, *, with_crop: bool = False) -> None:
    for index, task_dir in enumerate(sorted((run_dir / "tasks").iterdir())):
        if with_crop and index == 0:
            _write_worker_result(
                task_dir,
                warnings=["Formula crop requires user confirmation."],
                crop_requests=[
                    {"page": 1, "bbox": [0.1, 0.2, 0.8, 0.9], "kind": "formula"}
                ],
            )
        else:
            _write_worker_result(task_dir)


def _start_run(tmp_path: Path) -> tuple[Path, Path, VisualPdfConfig]:
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    _write_source_pdf(source_pdf)
    visual_config = _visual_config()
    outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)
    assert isinstance(outcome, AgentActionRequiredOutcome)
    assert outcome.task_package.parent.name == ".visual-runs"
    return source_pdf, outcome.task_package, visual_config


def _drive_to_ready_with_crop(
    source_pdf: Path, run_dir: Path, visual_config: VisualPdfConfig
) -> NeedsConfirmationOutcome:
    _write_all_completed(run_dir, with_crop=True)
    boundary_package = prepareOrProgressVisualConversion(
        source_pdf, "# Candidate\n", visual_config
    )
    assert isinstance(boundary_package, AgentActionRequiredOutcome)
    assert boundary_package.task_package == run_dir / "boundary-review"
    _write_boundary_result(boundary_package.task_package)
    ready_outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)
    assert isinstance(ready_outcome, NeedsConfirmationOutcome)
    run = loadVisualRun(run_dir)
    assert run.state == "ready_to_adopt"
    assert all(chunk.state == "completed" for chunk in run.chunks.values())
    return ready_outcome


def _write_boundary_result(task_package: Path) -> None:
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
    (task_package / "result.json").write_text(json.dumps(result), encoding="utf-8")


def _edit_last_chunk_result(run_dir: Path) -> None:
    """模拟 Agent 在两次 ingest 之间直接修补 chunk 结果（如补参考文献编号）。"""
    last_task = sorted((run_dir / "tasks").iterdir())[-1]
    assert last_task.name == "chunk-002"
    result_md = last_task / "result.md"
    result_md.write_text(
        result_md.read_text(encoding="utf-8").replace(
            "Page 3 content.",
            "Page 3 content.\n[1] Renumbered reference entry.",
        ),
        encoding="utf-8",
    )


def test_re_review_rolls_ready_run_back_and_rebuilds_boundary_package(tmp_path):
    """ready_to_adopt + re_review：状态回 running、产物目录重建、chunk 保持 completed。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path)
    _drive_to_ready_with_crop(source_pdf, run_dir, visual_config)
    old_merged = (run_dir / "boundary-review" / "merged.md").read_text(encoding="utf-8")
    assert (run_dir / "fallback-assets" / "visual-page-0001-formula-01.png").is_file()
    _edit_last_chunk_result(run_dir)

    re_review_outcome = prepareOrProgressVisualConversion(
        source_pdf,
        "# Candidate\n",
        visual_config,
        re_review=True,
    )

    assert isinstance(re_review_outcome, AgentActionRequiredOutcome)
    assert re_review_outcome.task_package == run_dir / "boundary-review"
    run = loadVisualRun(run_dir)
    assert run.state == "running"
    assert all(chunk.state == "completed" for chunk in run.chunks.values())
    assert not (run_dir / "fallback-assets").exists()
    assert not (run_dir / "lease.json").exists()
    new_merged = (run_dir / "boundary-review" / "merged.md").read_text(encoding="utf-8")
    assert "[1] Renumbered reference entry." in new_merged
    assert "[1] Renumbered reference entry." not in old_merged

    _write_boundary_result(re_review_outcome.task_package)
    final_outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)

    assert isinstance(final_outcome, NeedsConfirmationOutcome)
    assert loadVisualRun(run_dir).state == "ready_to_adopt"
    assert (run_dir / "fallback-assets" / "visual-page-0001-formula-01.png").is_file()


def test_re_review_without_ready_run_fails_with_next_step_guidance(tmp_path):
    """非 ready_to_adopt（running 与全新 prepared）一律返回可执行的 visual_re_review_invalid。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path)
    assert loadVisualRun(run_dir).state == "running"
    run_json_before = (run_dir / "run.json").read_bytes()

    running_outcome = prepareOrProgressVisualConversion(
        source_pdf,
        "# Candidate\n",
        visual_config,
        re_review=True,
    )

    assert isinstance(running_outcome, FailedConversionOutcome)
    assert running_outcome.error.code == "visual_re_review_invalid"
    assert "ready_to_adopt" in running_outcome.error.message
    assert "remove --re-review" in running_outcome.error.message
    assert (run_dir / "run.json").read_bytes() == run_json_before

    fresh_source = tmp_path / "fresh" / "paper" / "source" / "source.pdf"
    _write_source_pdf(fresh_source)
    fresh_run_dir = prepareVisualConversion(fresh_source, "# Candidate\n", _visual_config())
    assert loadVisualRun(fresh_run_dir).state == "prepared"

    prepared_outcome = prepareOrProgressVisualConversion(
        fresh_source,
        "# Candidate\n",
        _visual_config(),
        re_review=True,
    )

    assert isinstance(prepared_outcome, FailedConversionOutcome)
    assert prepared_outcome.error.code == "visual_re_review_invalid"
    assert loadVisualRun(fresh_run_dir).state == "prepared"


def test_without_flag_ready_run_remains_idempotent_and_stale_boundary_still_fails(tmp_path):
    """不带旗标时 ready_to_adopt 行为逐字节不变：幂等返回，陈旧边界仍报原错误。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path)
    first = _drive_to_ready_with_crop(source_pdf, run_dir, visual_config)

    repeated = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)

    assert repeated == first
    assert loadVisualRun(run_dir).state == "ready_to_adopt"
    assert (run_dir / "boundary-review" / "result.json").is_file()
    assert (run_dir / "fallback-assets" / "visual-page-0001-formula-01.png").is_file()

    _edit_last_chunk_result(run_dir)
    stale_outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)

    assert isinstance(stale_outcome, FailedConversionOutcome)
    assert stale_outcome.error.code == "visual_boundary_review_invalid"
    assert loadVisualRun(run_dir).state == "ready_to_adopt"


def test_warning_adoption_failure_surfaces_underlying_conflict_details(tmp_path):
    """显式确认采纳失败时，错误 message 必须携带底层冲突文件清单与修复指引。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path)
    _drive_to_ready_with_crop(source_pdf, run_dir, visual_config)
    assets_root = source_pdf.parent.parent / "assets"
    assets_root.mkdir()
    (assets_root / "visual-page-0001-formula-01.png").write_bytes(b"stale asset bytes")

    outcome = prepareOrProgressVisualConversion(
        source_pdf,
        "# Candidate\n",
        visual_config,
        accept_visual_warnings=True,
    )

    assert isinstance(outcome, FailedConversionOutcome)
    assert outcome.error.code == "visual_warning_adoption_failed"
    assert "./assets/visual-page-0001-formula-01.png" in outcome.error.message
    assert "Fix:" in outcome.error.message


def test_fallback_residual_conflict_surfaces_specific_file_in_failure(tmp_path):
    """fallback-assets 残留冲突时，quality_blocked 失败必须列出具体冲突文件。"""
    source_pdf, run_dir, visual_config = _start_run(tmp_path)
    _write_all_completed(run_dir, with_crop=True)
    boundary_package = prepareOrProgressVisualConversion(
        source_pdf, "# Candidate\n", visual_config
    )
    assert isinstance(boundary_package, AgentActionRequiredOutcome)
    fallback_root = run_dir / "fallback-assets"
    fallback_root.mkdir()
    (fallback_root / "stale-leftover.txt").write_text("stale", encoding="utf-8")
    _write_boundary_result(boundary_package.task_package)

    outcome = prepareOrProgressVisualConversion(source_pdf, "# Candidate\n", visual_config)

    assert isinstance(outcome, FailedConversionOutcome)
    assert outcome.error.code == "visual_quality_blocked"
    assert "fallback-assets/stale-leftover.txt" in outcome.error.message
    assert "Fix:" in outcome.error.message


def test_progress_pdf_conversion_forwards_re_review_only_when_explicit(monkeypatch):
    """默认与 accept 路径保持旧调用形状；只有显式 re_review 才透传关键字。"""
    source_pdf = Path("paper.pdf")
    candidate_markdown = "# Candidate\n"
    visual_config = PdfConversionConfig.model_validate(
        {"visual": {"mode": "always", "model": "host-model"}}
    )
    expected_outcome = AgentActionRequiredOutcome(Path("visual-run"))
    calls: list[tuple[bool, bool]] = []

    monkeypatch.setattr(pdf_conversion, "convert_pdf_to_markdown", lambda _: candidate_markdown)

    def fake_progress(
        actual_source,
        actual_candidate,
        actual_config,
        *,
        accept_visual_warnings=False,
        re_review=False,
    ):
        calls.append((accept_visual_warnings, re_review))
        return expected_outcome

    monkeypatch.setattr(pdf_conversion, "prepareOrProgressVisualConversion", fake_progress)

    assert pdf_conversion.progressPdfConversion(source_pdf, visual_config) is expected_outcome
    assert (
        pdf_conversion.progressPdfConversion(
            source_pdf, visual_config, accept_visual_warnings=True
        )
        is expected_outcome
    )
    assert (
        pdf_conversion.progressPdfConversion(source_pdf, visual_config, re_review=True)
        is expected_outcome
    )
    assert (
        pdf_conversion.progressPdfConversion(
            source_pdf,
            visual_config,
            accept_visual_warnings=True,
            re_review=True,
        )
        is expected_outcome
    )

    assert calls == [(False, False), (True, False), (False, True), (True, True)]


def test_auto_mode_forwards_re_review_only_when_explicit(monkeypatch):
    """progressPdfConversion 的 auto 分支同样只在显式时透传 re_review。"""
    source_pdf = Path("paper.pdf")
    visual_config = PdfConversionConfig.model_validate(
        {"visual": {"mode": "auto", "model": "host-model"}}
    )
    expected_outcome = AgentActionRequiredOutcome(Path("audit-package"))
    calls: list[dict[str, bool]] = []

    monkeypatch.setattr(pdf_conversion, "convert_pdf_to_markdown", lambda _: "# Candidate\n")

    def fake_auto_audit(actual_source, actual_candidate, actual_config, **kwargs):
        calls.append(dict(kwargs))
        return expected_outcome

    monkeypatch.setattr(pdf_conversion, "prepareOrProgressPdfAutoAudit", fake_auto_audit)

    assert pdf_conversion.progressPdfConversion(source_pdf, visual_config) is expected_outcome
    assert calls[-1] == {}
    assert (
        pdf_conversion.progressPdfConversion(
            source_pdf, visual_config, accept_visual_warnings=True
        )
        is expected_outcome
    )
    assert calls[-1] == {"accept_visual_warnings": True}
    assert (
        pdf_conversion.progressPdfConversion(source_pdf, visual_config, re_review=True)
        is expected_outcome
    )
    assert calls[-1] == {"accept_visual_warnings": False, "re_review": True}
