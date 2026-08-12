"""Zotero PDF 视觉质量门接入的外部行为测试。"""

from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

import paperbase.cli.commands.ingest as ingest_command
from paperbase.adapters.zotero_adapter import ZoteroItem
from paperbase.cli.main import main
from paperbase.core.identity import generate_storage_id, normalize_paper_id
from paperbase.core.manifest import load_manifest
from paperbase.core.paths import PaperPaths
from paperbase.core.pdf_conversion import (
    AgentActionRequiredOutcome,
    FailedConversionOutcome,
    NeedsConfirmationOutcome,
    PdfConversionError,
    ReadyConversionOutcome,
)
from paperbase.schemas.manifest import PaperState
from paperbase.utils.markdown import parse_frontmatter

PDF_BYTES = b"synthetic Zotero PDF fixture"


def _item(case_name: str) -> ZoteroItem:
    return ZoteroItem(
        key=f"ZOTERO-{case_name.upper()}",
        title="Zotero-authoritative title",
        authors=["Zotero Author"],
        year=2026,
        item_type="journalArticle",
        doi=f"10.1234/visual-zotero-{case_name}",
        arxiv_id=None,
        abstract="Zotero-authoritative abstract.",
        url="https://example.org/zotero-fixture",
    )


def _paths(base_dir: Path, item: ZoteroItem) -> PaperPaths:
    assert item.doi is not None
    paper_id = normalize_paper_id(item.doi)
    return PaperPaths(storage_id=generate_storage_id(paper_id), base_dir=base_dir)


def _write_visual_config(base_dir: Path) -> None:
    config_path = base_dir / "config" / "paperbase.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        """conversion:
  pdf:
    visual:
      mode: always
      model: host-model
      chunk_pages: 2
      retry: 0
""",
        encoding="utf-8",
    )


def _install_pdf_adapter(monkeypatch, tmp_path: Path, item: ZoteroItem) -> Path:
    source_pdf = tmp_path / f"{item.key}.pdf"
    source_pdf.write_bytes(PDF_BYTES)
    adapter = Mock()
    adapter.fetch_item.return_value = item
    adapter.get_pdf_path.return_value = str(source_pdf)
    monkeypatch.setattr(ingest_command, "_create_zotero_adapter", lambda ctx: adapter)
    monkeypatch.setattr(
        ingest_command,
        "extract_pdf_metadata",
        lambda path: {
            "title": "Conflicting PDF title",
            "authors": ["PDF Author"],
            "year": 1999,
            "doi": "10.9999/conflicting-pdf",
            "abstract": "Conflicting PDF abstract.",
        },
    )
    return source_pdf


def _invoke_key(base_dir: Path, item: ZoteroItem, *extra_args: str):
    return CliRunner().invoke(
        main,
        [
            "--base-dir",
            str(base_dir),
            "ingest",
            "--zotero-key",
            item.key,
            *extra_args,
        ],
    )


def _assert_incomplete(base_dir: Path, item: ZoteroItem, state: PaperState) -> None:
    paths = _paths(base_dir, item)
    manifest = load_manifest(paths.manifest_json)

    assert paths.source_pdf.read_bytes() == PDF_BYTES
    assert manifest.state == state
    assert manifest.canonical_md is None
    assert not paths.paper_md.exists()
    assert not paths.chunks_jsonl.exists()
    assert not (base_dir / "registry" / "papers.db").exists()
    assert not (base_dir / "index" / "fts.db").exists()
    assert not (base_dir / "graph").exists()


def test_zotero_pdf_is_saved_before_legacy_progress_action_handoff(monkeypatch, tmp_path):
    """默认无 flag 保持旧二参数 seam，并以已保存的 source.pdf 建立 Action 交接。"""
    base_dir = tmp_path / "paperbase"
    item = _item("action")
    _write_visual_config(base_dir)
    source_pdf = _install_pdf_adapter(monkeypatch, tmp_path, item)
    paths = _paths(base_dir, item)
    task_package = base_dir / "agent-task"
    task_package.mkdir(parents=True)
    calls: list[tuple[Path, object]] = []

    def legacy_action_progress(saved_source, conversion_config):
        calls.append((saved_source, conversion_config))
        assert saved_source == paths.source_pdf
        assert saved_source != source_pdf
        assert saved_source.read_bytes() == PDF_BYTES
        assert conversion_config.visual.mode == "always"
        return AgentActionRequiredOutcome(task_package)

    monkeypatch.setattr(ingest_command, "progressPdfConversion", legacy_action_progress)

    result = _invoke_key(base_dir, item, "--no-graph")

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    _assert_incomplete(base_dir, item, PaperState.BLOCKED)
    assert str(task_package) in result.output.replace("\n", "")


@pytest.mark.parametrize(
    ("case_name", "outcome", "expected_state"),
    [
        (
            "needs",
            NeedsConfirmationOutcome(("Visual crop needs confirmation.",)),
            PaperState.NEEDS_REVIEW,
        ),
        (
            "retryable",
            FailedConversionOutcome(
                PdfConversionError("visual_progress_failed", "temporary failure")
            ),
            PaperState.FAILED_RETRYABLE,
        ),
    ],
)
def test_zotero_pdf_nonready_outcomes_save_only_incomplete_state(
    monkeypatch, tmp_path, case_name, outcome, expected_state
):
    """Needs 与 Failed 均不得采用 Canonical、Registry、索引或图谱。"""
    base_dir = tmp_path / case_name / "paperbase"
    item = _item(case_name)
    _write_visual_config(base_dir)
    _install_pdf_adapter(monkeypatch, tmp_path / case_name, item)
    cleanup = Mock()

    def legacy_nonready_progress(saved_source, conversion_config):
        assert saved_source == _paths(base_dir, item).source_pdf
        assert conversion_config.visual.mode == "always"
        return outcome

    monkeypatch.setattr(ingest_command, "progressPdfConversion", legacy_nonready_progress)
    monkeypatch.setattr(ingest_command, "cleanupReadyVisualRuns", cleanup)

    result = _invoke_key(base_dir, item, "--no-graph")

    assert result.exit_code == 0, result.output
    _assert_incomplete(base_dir, item, expected_state)
    cleanup.assert_not_called()


def test_zotero_pdf_explicit_accept_adopts_safe_assets_and_keeps_zotero_metadata(
    monkeypatch, tmp_path
):
    """显式 flag 透传后采用已验证资产，且 Canonical 始终以 Zotero 元数据为准。"""
    base_dir = tmp_path / "paperbase"
    item = _item("ready")
    _write_visual_config(base_dir)
    _install_pdf_adapter(monkeypatch, tmp_path, item)
    paths = _paths(base_dir, item)
    cleanup = Mock(return_value=("run-001",))
    asset_reference = "./assets/visual-page-0001-formula-01.png"
    candidate_markdown = f"# Candidate\n\n![Visual crop]({asset_reference})\n\n" + (
        "body evidence. " * 120
    )
    forwarded: list[bool] = []

    def ready_after_accept(saved_source, conversion_config, *, accept_visual_warnings=False):
        assert saved_source == paths.source_pdf
        assert saved_source.read_bytes() == PDF_BYTES
        assert conversion_config.visual.mode == "always"
        forwarded.append(accept_visual_warnings)
        asset_path = saved_source.parent.parent / asset_reference.removeprefix("./")
        asset_path.parent.mkdir(exist_ok=True)
        asset_path.write_bytes(b"visual crop")
        return ReadyConversionOutcome(candidate_markdown, (asset_reference,))

    monkeypatch.setattr(ingest_command, "progressPdfConversion", ready_after_accept)
    monkeypatch.setattr(ingest_command, "cleanupReadyVisualRuns", cleanup)

    result = _invoke_key(
        base_dir,
        item,
        "--accept-visual-warnings",
        "--no-graph",
    )

    assert result.exit_code == 0, result.output
    manifest = load_manifest(paths.manifest_json)
    frontmatter, _ = parse_frontmatter(paths.paper_md.read_text(encoding="utf-8"))
    assert forwarded == [True]
    assert manifest.state == PaperState.NORMALIZED
    assert frontmatter["title"] == item.title
    assert [author["name"] for author in frontmatter["authors"]] == item.authors
    assert frontmatter["year"] == item.year
    assert frontmatter["abstract"] == item.abstract
    assert asset_reference in paths.paper_md.read_text(encoding="utf-8")
    assert (paths.paper_dir / asset_reference.removeprefix("./")).read_bytes() == b"visual crop"
    cleanup.assert_called_once_with(paths.paper_dir)


def test_zotero_ready_candidate_failing_canonical_gate_stays_needs_review(monkeypatch, tmp_path):
    """Zotero PDF 与本地 PDF 共用采用前门，失败时不降级为元数据成功。"""
    base_dir = tmp_path / "paperbase"
    item = _item("canonical-gate")
    _write_visual_config(base_dir)
    _install_pdf_adapter(monkeypatch, tmp_path, item)
    cleanup = Mock()
    monkeypatch.setattr(
        ingest_command,
        "progressPdfConversion",
        lambda saved_source, conversion_config: ReadyConversionOutcome("short body"),
    )
    monkeypatch.setattr(ingest_command, "cleanupReadyVisualRuns", cleanup)

    result = _invoke_key(base_dir, item, "--no-graph")

    assert result.exit_code == 0, result.output
    _assert_incomplete(base_dir, item, PaperState.NEEDS_REVIEW)
    assert "canonical_adoption_gate_failed" in result.output
    cleanup.assert_not_called()


@pytest.mark.parametrize("error_code", ["visual_boundary_review_invalid", "visual_quality_blocked"])
def test_zotero_pdf_accept_flag_cannot_bypass_invalid_or_quality_blocked_results(
    monkeypatch, tmp_path, error_code
):
    """accept 仅确认 warning，不能把非法或质量阻塞结果采用为 Canonical。"""
    base_dir = tmp_path / error_code / "paperbase"
    item = _item(error_code)
    _write_visual_config(base_dir)
    _install_pdf_adapter(monkeypatch, tmp_path / error_code, item)
    cleanup = Mock()
    forwarded: list[bool] = []

    def rejected_progress(saved_source, conversion_config, *, accept_visual_warnings=False):
        forwarded.append(accept_visual_warnings)
        return FailedConversionOutcome(PdfConversionError(error_code, "fixture"))

    monkeypatch.setattr(ingest_command, "progressPdfConversion", rejected_progress)
    monkeypatch.setattr(ingest_command, "cleanupReadyVisualRuns", cleanup)

    result = _invoke_key(
        base_dir,
        item,
        "--accept-visual-warnings",
        "--no-graph",
    )

    assert result.exit_code == 0, result.output
    assert forwarded == [True]
    _assert_incomplete(base_dir, item, PaperState.NEEDS_REVIEW)
    cleanup.assert_not_called()


def test_zotero_pdf_ready_assets_must_exist_before_adoption(monkeypatch, tmp_path):
    """即使传入 accept，缺失的视觉资产也必须停在 NEEDS_REVIEW。"""
    base_dir = tmp_path / "paperbase"
    item = _item("missing-asset")
    _write_visual_config(base_dir)
    _install_pdf_adapter(monkeypatch, tmp_path, item)
    cleanup = Mock()

    def missing_asset_progress(saved_source, conversion_config, *, accept_visual_warnings=False):
        assert accept_visual_warnings
        return ReadyConversionOutcome("# Candidate", ("./assets/missing-figure.png",))

    monkeypatch.setattr(ingest_command, "progressPdfConversion", missing_asset_progress)
    monkeypatch.setattr(ingest_command, "cleanupReadyVisualRuns", cleanup)

    result = _invoke_key(
        base_dir,
        item,
        "--accept-visual-warnings",
        "--no-graph",
    )

    assert result.exit_code == 0, result.output
    _assert_incomplete(base_dir, item, PaperState.NEEDS_REVIEW)
    cleanup.assert_not_called()


def test_zotero_metadata_only_never_enters_visual_progress(monkeypatch, tmp_path):
    """无 PDF 的 Zotero 条目保持元数据路径，不得触碰视觉转换或清理。"""
    base_dir = tmp_path / "paperbase"
    item = _item("metadata-only")
    adapter = Mock()
    adapter.fetch_item.return_value = item
    adapter.get_pdf_path.return_value = None
    progress = Mock(side_effect=AssertionError("metadata-only must not progress PDF"))
    cleanup = Mock()
    monkeypatch.setattr(ingest_command, "_create_zotero_adapter", lambda ctx: adapter)
    monkeypatch.setattr(ingest_command, "progressPdfConversion", progress)
    monkeypatch.setattr(ingest_command, "cleanupReadyVisualRuns", cleanup)

    result = _invoke_key(base_dir, item, "--accept-visual-warnings", "--no-graph")

    assert result.exit_code == 0, result.output
    assert _paths(base_dir, item).paper_md.exists()
    progress.assert_not_called()
    cleanup.assert_not_called()


def test_zotero_recent_forwards_accept_flag_and_counts_incomplete_as_failure(monkeypatch, tmp_path):
    """recent 将用户 flag 传给单篇导入，incomplete 不能误计入成功数。"""
    first_item = _item("recent-one")
    second_item = _item("recent-two")
    adapter = Mock()
    adapter.list_recent.return_value = [first_item, second_item]
    calls: list[tuple[str, bool, bool, bool]] = []

    def incomplete_single(
        ctx,
        item_key,
        no_graph,
        headless_graph,
        *,
        accept_visual_warnings=False,
    ):
        calls.append((item_key, no_graph, headless_graph, accept_visual_warnings))
        return "incomplete"

    monkeypatch.setattr(ingest_command, "_create_zotero_adapter", lambda ctx: adapter)
    monkeypatch.setattr(ingest_command, "_ingest_from_zotero", incomplete_single)

    result = CliRunner().invoke(
        main,
        [
            "--base-dir",
            str(tmp_path / "paperbase"),
            "ingest",
            "--zotero-recent",
            "2",
            "--accept-visual-warnings",
            "--no-graph",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        (first_item.key, True, False, True),
        (second_item.key, True, False, True),
    ]
    assert "成功: 0 篇" in result.output
    assert "失败: 2 篇" in result.output
