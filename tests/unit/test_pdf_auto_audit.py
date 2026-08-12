"""自动 PDF 文本审计的公开任务协议与路由回归测试。"""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pymupdf
import pytest

from paperbase.config.models import PdfConversionConfig
from paperbase.core import pdf_auto_audit, pdf_conversion
from paperbase.core.pdf_conversion import (
    AgentActionRequiredOutcome,
    FailedConversionOutcome,
    ReadyConversionOutcome,
    progressPdfConversion,
)


def _write_pdf(
    source_pdf: Path, *, double_column: bool = False, control_text: bool = False
) -> None:
    source_pdf.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    try:
        page = document.new_page(width=600, height=800)
        if double_column:
            for x_position, y_position, text in (
                (60, 180, "Left column first block."),
                (60, 340, "Left column second block."),
                (350, 180, "Right column first block."),
                (350, 340, "Right column second block."),
            ):
                page.insert_text((x_position, y_position), text, fontsize=12)
        else:
            page.insert_text((72, 180), "Single column first block.", fontsize=12)
            page.insert_text((72, 340), "Single column second block.", fontsize=12)
        if control_text:
            page.insert_text((72, 480), "Garbled control:\x01.", fontsize=12)
        document.save(source_pdf)
    finally:
        document.close()


def _auto_config(model: str = "host-model") -> PdfConversionConfig:
    return PdfConversionConfig.model_validate({"visual": {"mode": "auto", "model": model}})


def _start_auto_audit(
    source_pdf: Path,
    candidate_markdown: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    model: str = "host-model",
):
    monkeypatch.setattr(
        pdf_conversion,
        "convert_pdf_to_markdown",
        lambda actual_source_pdf: candidate_markdown,
    )
    outcome = progressPdfConversion(source_pdf, _auto_config(model))
    assert isinstance(outcome, AgentActionRequiredOutcome)
    return outcome.task_package


def _write_result(audit_dir: Path, **changes: object) -> None:
    task = json.loads((audit_dir / "task.json").read_text(encoding="utf-8"))
    schema = task["worker_output"]["schema"]
    result = {
        "kind": schema["kind"],
        "version": schema["version"],
        "source_pdf_sha256": schema["source_pdf_sha256"],
        "candidate_sha256": schema["candidate_sha256"],
        "decision": "pass",
        "layout": "single_column",
        "flagged_pages": [],
        "reasons": ["The candidate preserves the single-column reading order."],
    }
    result.update(changes)
    (audit_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def _make_junction_or_skip(link_path: Path, target_path: Path) -> None:
    target_path.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link_path), str(target_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("当前 Windows 环境不允许创建 junction")


def _remove_junction(link_path: Path) -> None:
    subprocess.run(
        ["cmd.exe", "/d", "/c", "rmdir", str(link_path)],
        capture_output=True,
        text=True,
        check=True,
    )


def test_auto_without_result_prepares_hash_bound_audit_handoff(tmp_path, monkeypatch):
    """auto 只生成 Candidate、布局证据和仅允许 result.json 的宿主交接。"""
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    candidate_markdown = "# Candidate\n\nDeterministic body.\n"
    _write_pdf(source_pdf, double_column=True)

    audit_dir = _start_auto_audit(
        source_pdf, candidate_markdown, monkeypatch, model="host/model:verbatim"
    )

    task = json.loads((audit_dir / "task.json").read_text(encoding="utf-8"))
    layout = json.loads((audit_dir / "layout.json").read_text(encoding="utf-8"))

    assert audit_dir.parent.name == ".visual-auto-audit"
    assert (audit_dir / "candidate.md").read_text(encoding="utf-8") == candidate_markdown
    assert {entry.name for entry in audit_dir.iterdir()} == {
        "candidate.md",
        "layout.json",
        "task.json",
    }
    assert task["kind"] == "pdf_auto_text_audit"
    assert task["requested_model"] == "host/model:verbatim"
    assert task["worker_output"]["path"] == "result.json"
    assert task["worker_output"]["schema"]["kind"] == "pdf_auto_text_audit_result"
    assert (
        task["worker_output"]["schema"]["source_pdf_sha256"]
        == task["inputs"]["source_pdf"]["sha256"]
    )
    assert (
        task["worker_output"]["schema"]["candidate_sha256"] == task["inputs"]["candidate"]["sha256"]
    )
    assert all(not Path(input_data["path"]).is_absolute() for input_data in task["inputs"].values())
    assert layout["source_pdf_sha256"] == task["inputs"]["source_pdf"]["sha256"]
    assert layout["candidate_sha256"] == task["inputs"]["candidate"]["sha256"]


def test_auto_layout_evidence_detects_columns_without_single_column_false_positive(
    tmp_path, monkeypatch
):
    """左右栏纵向重叠必须标记；单栏控制字符保留为实际乱码质量信号。"""
    double_source = tmp_path / "double" / "source" / "source.pdf"
    single_source = tmp_path / "single" / "source" / "source.pdf"
    _write_pdf(double_source, double_column=True)
    _write_pdf(single_source, control_text=True)

    double_audit = _start_auto_audit(double_source, "# Double\n", monkeypatch)
    single_audit = _start_auto_audit(single_source, "# Single\n", monkeypatch)
    double_page = json.loads((double_audit / "layout.json").read_text(encoding="utf-8"))["pages"][0]
    single_page = json.loads((single_audit / "layout.json").read_text(encoding="utf-8"))["pages"][0]

    assert double_page["column_suspected"] is True
    assert double_page["column_evidence"]["left_block_count"] >= 2
    assert double_page["column_evidence"]["right_block_count"] >= 2
    assert (
        double_page["column_evidence"]["vertical_overlap"]
        >= double_page["column_evidence"]["minimum_vertical_overlap"]
    )
    assert single_page["column_suspected"] is False
    assert single_page["column_evidence"]["right_block_count"] == 0
    assert single_page["replacement_char_count"] == 0
    assert single_page["control_char_count"] == 1


def test_auto_source_or_candidate_change_creates_new_audit(tmp_path, monkeypatch):
    """审计身份必须同时绑定来源 PDF 和 Candidate，任一变化都不能复用旧目录。"""
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    _write_pdf(source_pdf)

    first_audit = _start_auto_audit(source_pdf, "# Candidate one\n", monkeypatch)
    changed_candidate_audit = _start_auto_audit(source_pdf, "# Candidate two\n", monkeypatch)
    source_pdf.unlink()
    _write_pdf(source_pdf, double_column=True)
    changed_source_audit = _start_auto_audit(source_pdf, "# Candidate one\n", monkeypatch)

    assert len({first_audit, changed_candidate_audit, changed_source_audit}) == 3
    assert len(list((source_pdf.parents[1] / ".visual-auto-audit").iterdir())) == 3


def test_auto_repeated_compatible_call_reuses_existing_audit(tmp_path, monkeypatch):
    """同一 source、Candidate 与模型重复推进必须稳定复用同一审计任务。"""
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    _write_pdf(source_pdf)
    candidate_markdown = "# Candidate\n\nStable body.\n"

    first_audit = _start_auto_audit(source_pdf, candidate_markdown, monkeypatch)
    task_before = (first_audit / "task.json").read_bytes()
    repeated_outcome = progressPdfConversion(source_pdf, _auto_config())

    assert isinstance(repeated_outcome, AgentActionRequiredOutcome)
    assert repeated_outcome.task_package == first_audit
    assert (first_audit / "task.json").read_bytes() == task_before
    assert len(list((source_pdf.parents[1] / ".visual-auto-audit").iterdir())) == 1


def test_auto_model_change_reuses_audit_and_updates_only_task(tmp_path, monkeypatch):
    """模型名不属于审计兼容键；变更时仅更新交接任务的原样模型字段。"""
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    _write_pdf(source_pdf)
    candidate_markdown = "# Candidate\n\nStable body.\n"
    audit_dir = _start_auto_audit(source_pdf, candidate_markdown, monkeypatch, model="host-model-a")
    candidate_before = (audit_dir / "candidate.md").read_bytes()
    layout_before = (audit_dir / "layout.json").read_bytes()
    task_before = json.loads((audit_dir / "task.json").read_text(encoding="utf-8"))

    changed_model_outcome = progressPdfConversion(source_pdf, _auto_config("host-model-b"))
    task_after = json.loads((audit_dir / "task.json").read_text(encoding="utf-8"))

    assert isinstance(changed_model_outcome, AgentActionRequiredOutcome)
    assert changed_model_outcome.task_package == audit_dir
    assert task_before["requested_model"] == "host-model-a"
    assert task_after == {**task_before, "requested_model": "host-model-b"}
    assert (audit_dir / "candidate.md").read_bytes() == candidate_before
    assert (audit_dir / "layout.json").read_bytes() == layout_before
    assert len(list((source_pdf.parents[1] / ".visual-auto-audit").iterdir())) == 1


def test_auto_valid_pass_result_returns_ready_without_visual_run(tmp_path, monkeypatch):
    """合规的单栏 pass 直接采用 Candidate，不得静默启动视觉运行。"""
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    candidate_markdown = "# Candidate\n\nSingle column body.\n"
    _write_pdf(source_pdf)
    audit_dir = _start_auto_audit(source_pdf, candidate_markdown, monkeypatch)
    _write_result(audit_dir)
    result_before = (audit_dir / "result.json").read_bytes()

    outcome = progressPdfConversion(source_pdf, _auto_config())

    assert isinstance(outcome, ReadyConversionOutcome)
    assert outcome.markdown == candidate_markdown
    assert outcome.assets == ()
    assert not (source_pdf.parents[1] / ".visual-runs").exists()
    assert (audit_dir / "result.json").read_bytes() == result_before


def test_auto_control_character_signal_is_flagged_and_cannot_be_passed(tmp_path, monkeypatch):
    """本地确定性控制字符信号必须进入任务门禁，worker 空标记 pass 无权覆盖。"""
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    _write_pdf(source_pdf, control_text=True)
    audit_dir = _start_auto_audit(source_pdf, "# Candidate\n", monkeypatch)
    task = json.loads((audit_dir / "task.json").read_text(encoding="utf-8"))

    assert task["deterministic_quality_gate"]["flagged_pages"] == [1]
    assert task["deterministic_quality_gate"]["signals"] == {"1": ["control_characters"]}
    assert any("deterministic_quality_gate" in instruction for instruction in task["instructions"])
    _write_result(audit_dir, decision="pass", layout="single_column", flagged_pages=[])

    outcome = progressPdfConversion(source_pdf, _auto_config())

    assert isinstance(outcome, FailedConversionOutcome)
    assert outcome.error.code == "visual_auto_audit_result_invalid"
    assert not (source_pdf.parents[1] / ".visual-runs").exists()


def test_auto_replacement_character_signal_requires_worker_flag(tmp_path, monkeypatch):
    """replacement character 信号不能被 visual_required 的空 flagged_pages 丢弃。"""
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    _write_pdf(source_pdf)
    original_builder = pdf_auto_audit._buildLayoutEvidence

    def build_layout_with_replacement(*args, **kwargs):
        layout = original_builder(*args, **kwargs)
        layout["pages"][0]["replacement_char_count"] = 1
        return layout

    monkeypatch.setattr(pdf_auto_audit, "_buildLayoutEvidence", build_layout_with_replacement)
    audit_dir = _start_auto_audit(source_pdf, "# Candidate\n", monkeypatch)
    task = json.loads((audit_dir / "task.json").read_text(encoding="utf-8"))

    assert task["deterministic_quality_gate"]["flagged_pages"] == [1]
    assert task["deterministic_quality_gate"]["signals"] == {"1": ["replacement_characters"]}
    _write_result(
        audit_dir,
        decision="visual_required",
        layout="uncertain",
        flagged_pages=[],
    )

    outcome = progressPdfConversion(source_pdf, _auto_config())

    assert isinstance(outcome, FailedConversionOutcome)
    assert outcome.error.code == "visual_auto_audit_result_invalid"


@pytest.mark.parametrize("layout", ["multi_column", "uncertain"])
def test_auto_visual_required_result_creates_full_document_visual_task(
    tmp_path, monkeypatch, layout
):
    """multi_column 或 uncertain 的有效审计结论只能升级为全文视觉任务。"""
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    candidate_markdown = "# Candidate\n\nColumn-concatenated text.\n"
    _write_pdf(source_pdf, double_column=True)
    audit_dir = _start_auto_audit(source_pdf, candidate_markdown, monkeypatch)
    _write_result(
        audit_dir,
        decision="visual_required",
        layout=layout,
        flagged_pages=[1],
        reasons=["Two columns overlap vertically and need visual reading-order repair."],
    )

    outcome = progressPdfConversion(source_pdf, _auto_config())

    assert isinstance(outcome, AgentActionRequiredOutcome)
    assert outcome.task_package.parent.name == ".visual-runs"
    assert (outcome.task_package / "candidate.md").read_text(encoding="utf-8") == candidate_markdown
    assert list((outcome.task_package / "tasks").glob("*/task.json"))


@pytest.mark.parametrize(
    "changes",
    [
        {"unexpected": "schema drift"},
        {"decision": "pass", "flagged_pages": [1]},
        {"flagged_pages": [2]},
    ],
    ids=["unexpected_schema_key", "pass_with_flagged_page", "page_outside_range"],
)
def test_auto_rejects_invalid_result_without_starting_visual_run(tmp_path, monkeypatch, changes):
    """非法 schema、pass 标记页和越界页均不得被当作可视觉采用的结果。"""
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    _write_pdf(source_pdf)
    audit_dir = _start_auto_audit(source_pdf, "# Candidate\n", monkeypatch)
    _write_result(audit_dir, **changes)
    prepare_visual = Mock(side_effect=AssertionError("invalid result must not start visual work"))
    monkeypatch.setattr(pdf_auto_audit, "prepareVisualConversion", prepare_visual)

    outcome = progressPdfConversion(source_pdf, _auto_config())

    assert isinstance(outcome, FailedConversionOutcome)
    assert outcome.error.code == "visual_auto_audit_result_invalid"
    prepare_visual.assert_not_called()


@pytest.mark.parametrize("hash_field", ["source_pdf_sha256", "candidate_sha256"])
def test_auto_rejects_result_bound_to_old_inputs_without_starting_visual_run(
    tmp_path, monkeypatch, hash_field
):
    """完成结果必须与当前 source/Candidate 双哈希匹配，不能沿用旧审计结论。"""
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    _write_pdf(source_pdf)
    audit_dir = _start_auto_audit(source_pdf, "# Candidate\n", monkeypatch)
    _write_result(audit_dir)
    result_path = audit_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result[hash_field] = "0" * 64
    result_path.write_text(json.dumps(result), encoding="utf-8")
    prepare_visual = Mock(side_effect=AssertionError("old input result must not start visual work"))
    monkeypatch.setattr(pdf_auto_audit, "prepareVisualConversion", prepare_visual)

    outcome = progressPdfConversion(source_pdf, _auto_config())

    assert isinstance(outcome, FailedConversionOutcome)
    assert outcome.error.code == "visual_auto_audit_result_invalid"
    prepare_visual.assert_not_called()


def test_auto_rejects_symlinked_result_without_starting_visual_run(tmp_path, monkeypatch):
    """worker 结果必须是普通文件；符号链接不得绕过审计目录的写入边界。"""
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    _write_pdf(source_pdf)
    audit_dir = _start_auto_audit(source_pdf, "# Candidate\n", monkeypatch)
    result_path = audit_dir / "result.json"
    try:
        result_path.symlink_to(audit_dir / "candidate.md")
    except OSError as exc:
        pytest.skip(f"当前 Windows 环境不允许创建符号链接: {exc}")
    prepare_visual = Mock(side_effect=AssertionError("symlink result must not start visual work"))
    monkeypatch.setattr(pdf_auto_audit, "prepareVisualConversion", prepare_visual)

    outcome = progressPdfConversion(source_pdf, _auto_config())

    assert isinstance(outcome, FailedConversionOutcome)
    assert outcome.error.code == "visual_auto_audit_result_invalid"
    prepare_visual.assert_not_called()


def test_auto_rejects_junctioned_audit_root_without_writing_external_target(tmp_path, monkeypatch):
    """auto 审计根为 junction 时不得把任务包写到论文目录外。"""
    source_pdf = tmp_path / "paper" / "source" / "source.pdf"
    _write_pdf(source_pdf)
    monkeypatch.setattr(
        pdf_conversion,
        "convert_pdf_to_markdown",
        lambda actual_source_pdf: "# Candidate\n",
    )
    audit_root = source_pdf.parents[1] / ".visual-auto-audit"
    external_target = tmp_path / "external-audit"
    _make_junction_or_skip(audit_root, external_target)
    try:
        outcome = progressPdfConversion(source_pdf, _auto_config())

        assert isinstance(outcome, FailedConversionOutcome)
        assert outcome.error.code == "visual_auto_audit_preparation_failed"
        assert list(external_target.iterdir()) == []
    finally:
        _remove_junction(audit_root)


def test_auto_rejects_source_directory_junction(tmp_path, monkeypatch):
    """保存源目录经 junction 重定向时不得启动审计。"""
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    external_source = tmp_path / "external-source"
    _make_junction_or_skip(paper_dir / "source", external_source)
    source_pdf = external_source / "source.pdf"
    _write_pdf(source_pdf)
    monkeypatch.setattr(
        pdf_conversion,
        "convert_pdf_to_markdown",
        lambda actual_source_pdf: "# Candidate\n",
    )
    try:
        outcome = progressPdfConversion(paper_dir / "source" / "source.pdf", _auto_config())

        assert isinstance(outcome, FailedConversionOutcome)
        assert outcome.error.code == "visual_auto_audit_preparation_failed"
        assert not (paper_dir / ".visual-auto-audit").exists()
    finally:
        _remove_junction(paper_dir / "source")


def test_auto_rejects_junctioned_paper_root_without_writing_external_target(tmp_path, monkeypatch):
    """paper 根为 junction 时审计不得在外部目标创建任何运行文件。"""
    external_paper = tmp_path / "external-paper"
    source_pdf = external_paper / "source" / "source.pdf"
    _write_pdf(source_pdf)
    paper_link = tmp_path / "paper"
    _make_junction_or_skip(paper_link, external_paper)
    monkeypatch.setattr(
        pdf_conversion,
        "convert_pdf_to_markdown",
        lambda actual_source_pdf: "# Candidate\n",
    )
    try:
        outcome = progressPdfConversion(paper_link / "source" / "source.pdf", _auto_config())

        assert isinstance(outcome, FailedConversionOutcome)
        assert outcome.error.code == "visual_auto_audit_preparation_failed"
        assert not (external_paper / ".visual-auto-audit").exists()
    finally:
        _remove_junction(paper_link)
