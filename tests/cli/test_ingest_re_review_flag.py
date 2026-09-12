"""ingest --re-review 视觉返工重审入口的 CLI 契约测试。"""

from dataclasses import dataclass
from pathlib import Path

from click.testing import CliRunner

import paperbase.cli.commands.ingest as ingest_command
from paperbase.cli.main import main
from paperbase.core.identity import generate_storage_id, normalize_paper_id
from paperbase.core.manifest import load_manifest
from paperbase.core.paths import PaperPaths
from paperbase.core.pdf_conversion import (
    AgentActionRequiredOutcome,
    FailedConversionOutcome,
    PdfConversionError,
    ReadyConversionOutcome,
)
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState

PAPER_DOI = "10.1234/re-review-flag"
PAPER_ID = normalize_paper_id(PAPER_DOI)
STORAGE_ID = generate_storage_id(PAPER_ID)
CONVERTED_MARKDOWN = "# Re-review fixture\n\n" + ("body evidence. " * 120)
PDF_BYTES = b"synthetic PDF fixture for re-review flag tests"
REVIEW_MESSAGE = (
    "visual re-review requires a ready_to_adopt run; "
    "remove --re-review and re-run ingest to progress the run normally"
)


def _write_input_pdf(tmp_path: Path) -> Path:
    input_pdf = tmp_path / "incoming.pdf"
    input_pdf.write_bytes(PDF_BYTES)
    return input_pdf


def _metadata(_: Path) -> dict[str, object]:
    return {
        "title": "Re-review fixture",
        "authors": ["Ada Lovelace"],
        "year": 2026,
        "doi": PAPER_DOI,
        "abstract": "A synthetic record used only for the re-review contract.",
    }


def _paths(base_dir: Path) -> PaperPaths:
    return PaperPaths(storage_id=STORAGE_ID, base_dir=base_dir)


def _invoke(base_dir: Path, input_pdf: Path, *extra_args: str):
    return CliRunner().invoke(
        main,
        ["--base-dir", str(base_dir), "ingest", "--file", str(input_pdf), *extra_args],
    )


def _invoke_zotero(base_dir: Path, item_key: str, *extra_args: str):
    return CliRunner().invoke(
        main,
        ["--base-dir", str(base_dir), "ingest", "--zotero-key", item_key, *extra_args],
    )


def _ready_then_agent_action(calls: list[dict[str, object]], task_package: Path):
    def staged_progress(
        source_pdf,
        conversion_config,
        *,
        accept_visual_warnings=False,
        re_review=False,
    ):
        calls.append({"re_review": re_review, "source_pdf": source_pdf})
        if len(calls) == 1:
            return ReadyConversionOutcome(CONVERTED_MARKDOWN)
        return AgentActionRequiredOutcome(task_package=task_package)

    return staged_progress


def test_re_review_reenters_conversion_for_existing_paper(monkeypatch, tmp_path):
    """--re-review 对已存在论文不短路：继续走转换路径并透传 re_review=True。"""
    base_dir = tmp_path / "paperbase"
    input_pdf = _write_input_pdf(tmp_path)
    task_package = base_dir / "agent-work" / "boundary-recheck"
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(ingest_command, "extract_pdf_metadata", _metadata)
    monkeypatch.setattr(
        ingest_command, "progressPdfConversion", _ready_then_agent_action(calls, task_package)
    )

    first = _invoke(base_dir, input_pdf, "--no-graph")
    assert first.exit_code == 0, first.output
    assert load_manifest(_paths(base_dir).manifest_json).state == PaperState.NORMALIZED
    with PaperRegistry(base_dir / "registry" / "papers.db") as registry:
        assert registry.get_paper(PAPER_ID) is not None

    second = _invoke(base_dir, input_pdf, "--re-review", "--no-graph")

    assert second.exit_code == 0, second.output
    assert [call["re_review"] for call in calls] == [False, True]
    assert all(call["source_pdf"] == _paths(base_dir).source_pdf for call in calls)
    assert "DOI 重复" not in second.output
    assert "跳过查重" in second.output
    manifest = load_manifest(_paths(base_dir).manifest_json)
    assert manifest.state == PaperState.BLOCKED
    assert manifest.canonical_md is None
    assert str(task_package) in second.output.replace("\n", "")


def test_duplicate_paper_still_aborts_without_re_review(monkeypatch, tmp_path):
    """不带 --re-review 时，已存在论文仍被查重短路，转换 seam 不被再次调用。"""
    base_dir = tmp_path / "paperbase"
    input_pdf = _write_input_pdf(tmp_path)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(ingest_command, "extract_pdf_metadata", _metadata)
    monkeypatch.setattr(
        ingest_command,
        "progressPdfConversion",
        _ready_then_agent_action(calls, base_dir / "unused" / "package"),
    )

    first = _invoke(base_dir, input_pdf, "--no-graph")
    assert first.exit_code == 0, first.output
    duplicate = _invoke(base_dir, input_pdf, "--no-graph")

    assert duplicate.exit_code != 0
    assert "DOI 重复" in duplicate.output
    assert len(calls) == 1


def test_visual_re_review_invalid_failure_maps_to_needs_review(monkeypatch, tmp_path):
    """visual_re_review_invalid 失败映射为 NEEDS_REVIEW，且指路信息透出到输出。"""
    base_dir = tmp_path / "paperbase"
    input_pdf = _write_input_pdf(tmp_path)
    calls: list[bool] = []
    monkeypatch.setattr(ingest_command, "extract_pdf_metadata", _metadata)

    def re_review_invalid_progress(
        source_pdf,
        conversion_config,
        *,
        accept_visual_warnings=False,
        re_review=False,
    ):
        calls.append(re_review)
        return FailedConversionOutcome(
            PdfConversionError(code="visual_re_review_invalid", message=REVIEW_MESSAGE)
        )

    monkeypatch.setattr(ingest_command, "progressPdfConversion", re_review_invalid_progress)

    result = _invoke(base_dir, input_pdf, "--re-review", "--no-graph")

    assert result.exit_code == 0, result.output
    assert calls == [True]
    manifest = load_manifest(_paths(base_dir).manifest_json)
    assert manifest.state == PaperState.NEEDS_REVIEW
    assert manifest.canonical_md is None
    assert "visual_re_review_invalid" in result.output
    assert REVIEW_MESSAGE in result.output.replace("\n", "")


def test_canonical_gate_failure_prints_message_payload(monkeypatch, tmp_path):
    """采用前门禁失败时，除 reason 外还必须透出 message 载体内容。"""
    base_dir = tmp_path / "paperbase"
    input_pdf = _write_input_pdf(tmp_path)
    monkeypatch.setattr(ingest_command, "extract_pdf_metadata", _metadata)
    monkeypatch.setattr(
        ingest_command,
        "progressPdfConversion",
        lambda source_pdf, conversion_config: ReadyConversionOutcome(
            CONVERTED_MARKDOWN + "\n\\n\n"
        ),
    )

    result = _invoke(base_dir, input_pdf, "--no-graph")

    assert result.exit_code == 0, result.output
    assert load_manifest(_paths(base_dir).manifest_json).state == PaperState.NEEDS_REVIEW
    assert "standalone_literal_escape" in result.output
    assert "Markdown contains standalone literal escape fragments" in result.output


def _install_zotero_stubs(monkeypatch, pdf_path: Path) -> None:
    @dataclass
    class _FakeItem:
        key: str
        title: str
        authors: list[str]
        year: int | None
        doi: str | None
        arxiv_id: str | None
        abstract: str
        item_type: str
        url: str | None = None

    class _FakeAdapter:
        def fetch_item(self, item_key: str) -> _FakeItem:
            return _FakeItem(
                key=item_key,
                title="Re-review fixture",
                authors=["Ada Lovelace"],
                year=2026,
                doi=PAPER_DOI,
                arxiv_id=None,
                abstract="A synthetic record used only for the re-review contract.",
                item_type="journalArticle",
            )

        def get_pdf_path(self, item_key: str) -> str:
            return str(pdf_path)

    monkeypatch.setattr(ingest_command, "_create_zotero_adapter", lambda ctx: _FakeAdapter())
    monkeypatch.setattr(ingest_command, "extract_pdf_metadata", lambda _: {})


def test_zotero_re_review_reenters_conversion_for_existing_paper(monkeypatch, tmp_path):
    """Zotero 链路的 --re-review 同样豁免 skipped 短路并透传 re_review=True。"""
    base_dir = tmp_path / "paperbase"
    input_pdf = _write_input_pdf(tmp_path)
    task_package = base_dir / "agent-work" / "zotero-boundary-recheck"
    calls: list[dict[str, object]] = []
    _install_zotero_stubs(monkeypatch, input_pdf)
    monkeypatch.setattr(
        ingest_command, "progressPdfConversion", _ready_then_agent_action(calls, task_package)
    )

    first = _invoke_zotero(base_dir, "ZOTEROITEM1", "--no-graph")
    assert first.exit_code == 0, first.output
    assert load_manifest(_paths(base_dir).manifest_json).state == PaperState.NORMALIZED

    second = _invoke_zotero(base_dir, "ZOTEROITEM1", "--re-review", "--no-graph")

    assert second.exit_code == 0, second.output
    assert [call["re_review"] for call in calls] == [False, True]
    assert "跳过此论文" not in second.output
    assert "重入其视觉转换 run" in second.output
    assert load_manifest(_paths(base_dir).manifest_json).state == PaperState.BLOCKED


def test_doi_re_review_reenters_existing_paper(monkeypatch, tmp_path):
    """DOI 输入的 --re-review 用已存源 PDF 重入既有论文，不触发在线抓取。"""
    base_dir = tmp_path / "paperbase"
    stored_pdf = _paths(base_dir).source_pdf
    stored_pdf.parent.mkdir(parents=True, exist_ok=True)
    stored_pdf.write_bytes(PDF_BYTES)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(ingest_command, "extract_pdf_metadata", _metadata)
    monkeypatch.setattr(
        ingest_command,
        "progressPdfConversion",
        _ready_then_agent_action(calls, base_dir / "agent-work" / "boundary-recheck"),
    )

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(base_dir), "ingest", PAPER_DOI, "--re-review", "--no-graph"],
    )

    assert result.exit_code == 0, result.output
    assert [call["re_review"] for call in calls] == [True]
    assert calls[0]["source_pdf"] == stored_pdf
    assert "重入" in result.output
    assert load_manifest(_paths(base_dir).manifest_json).state == PaperState.NORMALIZED


def test_doi_re_review_without_stored_pdf_aborts_without_fetching(monkeypatch, tmp_path):
    """无已存源 PDF 的 DOI 重审直接失败，绝不触发 paper-fetch 在线抓取。"""
    base_dir = tmp_path / "paperbase"

    def _must_not_fetch(*args, **kwargs):
        raise AssertionError("PaperFetchAdapter must not be called for re-review")

    monkeypatch.setattr(ingest_command, "PaperFetchAdapter", _must_not_fetch)

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(base_dir), "ingest", PAPER_DOI, "--re-review", "--no-graph"],
    )

    assert result.exit_code != 0
    assert "已保存的源 PDF" in result.output


def test_doi_re_review_rejects_identity_mismatch(monkeypatch, tmp_path):
    """源 PDF 元数据推导的 paper_id 与查询解析不一致时拒绝重审，避免落错论文目录。"""
    base_dir = tmp_path / "paperbase"
    stored_pdf = _paths(base_dir).source_pdf
    stored_pdf.parent.mkdir(parents=True, exist_ok=True)
    stored_pdf.write_bytes(PDF_BYTES)
    monkeypatch.setattr(
        ingest_command,
        "extract_pdf_metadata",
        lambda _: {**_metadata(stored_pdf), "doi": "10.9999/other-paper"},
    )

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(base_dir), "ingest", PAPER_DOI, "--re-review", "--no-graph"],
    )

    assert result.exit_code != 0
    assert "身份不一致" in result.output
