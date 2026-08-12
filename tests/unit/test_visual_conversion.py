"""Visual PDF conversion 的真实运行目录与续作边界测试。"""

import json
import os
import subprocess
from pathlib import Path

import pymupdf
import pytest

from paperbase.config.models import PdfConversionConfig
from paperbase.core import pdf_conversion, visual_conversion
from paperbase.core.pdf_conversion import (
    AgentActionRequiredOutcome,
    FailedConversionOutcome,
    progressPdfConversion,
)
from paperbase.core.visual_conversion import prepareVisualConversion


def _write_multipage_pdf(source_pdf: Path, page_count: int = 5) -> None:
    source_pdf.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    try:
        for page_number in range(1, page_count + 1):
            page = document.new_page()
            page.insert_text((72, 72), f"Page {page_number}")
        document.save(source_pdf)
    finally:
        document.close()


def _visual_config(model: str, chunk_pages: int = 2) -> PdfConversionConfig:
    return PdfConversionConfig.model_validate(
        {
            "visual": {
                "mode": "always",
                "model": model,
                "chunk_pages": chunk_pages,
            }
        }
    )


def _task_data(run_dir: Path) -> list[tuple[Path, dict[str, object]]]:
    task_paths = sorted((run_dir / "tasks").glob("*/task.json"))
    return [
        (task_path.parent, json.loads(task_path.read_text(encoding="utf-8")))
        for task_path in task_paths
    ]


def _run_dirs(paper_dir: Path) -> list[Path]:
    return sorted(path.parent for path in (paper_dir / ".visual-runs").glob("*/run.json"))


def _make_junction_or_skip(junction_path: Path, target_path: Path) -> None:
    target_path.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction_path), str(target_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("当前 Windows 环境不允许创建 junction")


def _remove_junction(junction_path: Path) -> None:
    subprocess.run(
        ["cmd", "/c", "rmdir", str(junction_path)],
        capture_output=True,
        text=True,
        check=True,
    )


def test_always_creates_reusable_full_document_visual_run(tmp_path, monkeypatch):
    paper_dir = tmp_path / "paper"
    source_pdf = paper_dir / "source" / "source.pdf"
    _write_multipage_pdf(source_pdf)
    candidate = {"markdown": "# Deterministic Candidate\n\nFull document body.\n"}
    monkeypatch.setattr(
        pdf_conversion,
        "convert_pdf_to_markdown",
        lambda _: candidate["markdown"],
    )

    first_outcome = progressPdfConversion(source_pdf, _visual_config("host-model-a"))

    assert isinstance(first_outcome, AgentActionRequiredOutcome)
    run_dir = first_outcome.task_package
    assert run_dir.is_dir()
    assert (run_dir / "candidate.md").read_text(encoding="utf-8") == candidate["markdown"]
    assert [path.name for path in sorted((run_dir / "rendered").glob("page-*.png"))] == [
        f"page-{page_number:04d}.png" for page_number in range(1, 6)
    ]

    task_data = _task_data(run_dir)
    assert [task_dir.name for task_dir, _ in task_data] == [
        "chunk-001",
        "chunk-002",
        "chunk-003",
    ]
    core_pages = [
        page_number for _, task in task_data for page_number in task["chunk"]["core_pages"]
    ]
    assert core_pages == list(range(1, 6))
    assert len(core_pages) == len(set(core_pages))
    for task_dir, task in task_data:
        chunk_core_pages = task["chunk"]["core_pages"]
        chunk_context_pages = task["chunk"]["context_pages"]
        assert 1 <= len(chunk_core_pages) <= 2
        assert chunk_core_pages == list(range(chunk_core_pages[0], chunk_core_pages[-1] + 1))
        assert not set(chunk_core_pages) & set(chunk_context_pages)
        assert (task_dir / "candidate-fragment.md").read_text(encoding="utf-8") == candidate[
            "markdown"
        ]
        assert task["candidate_fragment_scope"] == "full_document"
        assert task["requested_model"] == "host-model-a"
        context_inputs = task["inputs"]["context"]
        read_only_paths = task["read_only_boundary"]["paths"]
        assert set(context_inputs).issubset(read_only_paths)
        assert all(not Path(path).is_absolute() for path in read_only_paths)

    repeated_outcome = progressPdfConversion(source_pdf, _visual_config("host-model-a"))
    changed_model_outcome = progressPdfConversion(source_pdf, _visual_config("host-model-b"))

    assert isinstance(repeated_outcome, AgentActionRequiredOutcome)
    assert isinstance(changed_model_outcome, AgentActionRequiredOutcome)
    assert repeated_outcome.task_package == run_dir
    assert changed_model_outcome.task_package == run_dir
    assert {task["requested_model"] for _, task in _task_data(run_dir)} == {"host-model-b"}

    candidate["markdown"] = "# Changed Candidate\n"
    changed_candidate_outcome = progressPdfConversion(source_pdf, _visual_config("host-model-b"))
    changed_chunks_outcome = progressPdfConversion(source_pdf, _visual_config("host-model-b", 3))

    assert isinstance(changed_candidate_outcome, AgentActionRequiredOutcome)
    assert isinstance(changed_chunks_outcome, AgentActionRequiredOutcome)
    assert changed_candidate_outcome.task_package != run_dir
    assert changed_chunks_outcome.task_package not in {
        run_dir,
        changed_candidate_outcome.task_package,
    }
    assert len(_run_dirs(paper_dir)) == 3


def test_failed_task_preparation_reuses_run_and_revalidates_rendered_pages(tmp_path, monkeypatch):
    paper_dir = tmp_path / "paper"
    source_pdf = paper_dir / "source" / "source.pdf"
    _write_multipage_pdf(source_pdf)
    monkeypatch.setattr(
        pdf_conversion,
        "convert_pdf_to_markdown",
        lambda _: "# Deterministic Candidate\n",
    )
    render_calls = []
    real_renderer = visual_conversion.renderPdfPages

    def counting_renderer(*args, **kwargs):
        render_calls.append((args, kwargs))
        return real_renderer(*args, **kwargs)

    real_prepare = visual_conversion.prepareVisualTaskPackage
    preparation_attempts = []

    def fail_once(*args, **kwargs):
        preparation_attempts.append((args, kwargs))
        if len(preparation_attempts) == 1:
            raise RuntimeError("interrupted while preparing tasks")
        return real_prepare(*args, **kwargs)

    monkeypatch.setattr(visual_conversion, "renderPdfPages", counting_renderer)
    monkeypatch.setattr(visual_conversion, "prepareVisualTaskPackage", fail_once)

    first_outcome = progressPdfConversion(source_pdf, _visual_config("host-model"))

    assert isinstance(first_outcome, FailedConversionOutcome)
    run_dirs = _run_dirs(paper_dir)
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert (run_dir / "candidate.md").is_file()
    assert len(list((run_dir / "rendered").glob("page-*.png"))) == 5

    resumed_outcome = progressPdfConversion(source_pdf, _visual_config("host-model"))

    assert isinstance(resumed_outcome, AgentActionRequiredOutcome)
    assert resumed_outcome.task_package == run_dir
    assert [args[1] for args, _ in render_calls] == [run_dir / "rendered", run_dir / "rendered"]
    assert len(preparation_attempts) == 2


def test_visual_conversion_rejects_linked_saved_source_pdf(tmp_path):
    """Only the regular source/source.pdf file is eligible for visual work."""
    paper_dir = tmp_path / "paper"
    source_pdf = paper_dir / "source" / "source.pdf"
    target_pdf = tmp_path / "external-source.pdf"
    _write_multipage_pdf(target_pdf)
    source_pdf.parent.mkdir(parents=True)
    try:
        os.symlink(target_pdf, source_pdf, target_is_directory=False)
    except OSError:
        pytest.skip("file symlink creation is unavailable in this environment")

    with pytest.raises(ValueError, match="regular non-link file"):
        prepareVisualConversion(source_pdf, "# Candidate\n", _visual_config("host-model").visual)

    assert not (paper_dir / ".visual-runs").exists()


def test_visual_conversion_rejects_junctioned_paper_root_before_external_write(
    tmp_path, monkeypatch
):
    """A junctioned paper root must not receive any visual run files."""
    external_paper = tmp_path / "external-paper"
    source_pdf = external_paper / "source" / "source.pdf"
    _write_multipage_pdf(source_pdf)
    paper_link = tmp_path / "paper-link"
    _make_junction_or_skip(paper_link, external_paper)
    monkeypatch.setattr(
        pdf_conversion,
        "convert_pdf_to_markdown",
        lambda _: "# Candidate\n",
    )

    try:
        outcome = progressPdfConversion(
            paper_link / "source" / "source.pdf",
            _visual_config("host-model"),
        )

        assert isinstance(outcome, FailedConversionOutcome)
        assert outcome.error.code == "visual_preparation_failed"
        assert not (external_paper / ".visual-runs").exists()
    finally:
        _remove_junction(paper_link)
