"""视觉 PDF 转换接入普通 ingest 的集成契约测试。"""

from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

import paperbase.cli.commands.ingest as ingest_command
from paperbase.cli.main import main
from paperbase.core.identity import generate_storage_id, normalize_paper_id
from paperbase.core.manifest import load_manifest, save_manifest
from paperbase.core.paths import PaperPaths
from paperbase.core.pdf_conversion import (
    AgentActionRequiredOutcome,
    FailedConversionOutcome,
    NeedsConfirmationOutcome,
    PdfConversionError,
    ReadyConversionOutcome,
)
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState
from paperbase.utils.hash import sha256_file

PDF_BYTES = b"synthetic PDF fixture for visual ingest integration tests"
PAPER_DOI = "10.1234/visual-ingest-contract"
PAPER_ID = normalize_paper_id(PAPER_DOI)
STORAGE_ID = generate_storage_id(PAPER_ID)
CONVERTED_MARKDOWN = "# Visual ingest fixture\n\n" + ("body evidence. " * 120)


def _write_input_pdf(tmp_path: Path) -> Path:
    input_pdf = tmp_path / "incoming.pdf"
    input_pdf.write_bytes(PDF_BYTES)
    return input_pdf


def _metadata(_: Path) -> dict[str, object]:
    return {
        "title": "Visual ingest fixture",
        "authors": ["Ada Lovelace"],
        "year": 2026,
        "doi": PAPER_DOI,
        "abstract": "A synthetic record used only for the ingest contract.",
    }


def _paths(base_dir: Path) -> PaperPaths:
    return PaperPaths(storage_id=STORAGE_ID, base_dir=base_dir)


def _invoke(base_dir: Path, input_pdf: Path, *extra_args: str):
    return CliRunner().invoke(
        main,
        [
            "--base-dir",
            str(base_dir),
            "ingest",
            "--file",
            str(input_pdf),
            *extra_args,
        ],
    )


def _install_metadata_stub(monkeypatch) -> None:
    monkeypatch.setattr(ingest_command, "extract_pdf_metadata", _metadata)


def _write_always_visual_config(base_dir: Path) -> None:
    config_path = base_dir / "config" / "paperbase.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        """conversion:
  pdf:
    visual:
      mode: always
      model: host-selected-model
      chunk_pages: 2
      retry: 0
""",
        encoding="utf-8",
    )


def _output_without_line_breaks(output: str) -> str:
    """Rich 可能在 Windows 临时目录中间换行，保留路径字面量断言。"""
    return output.replace("\n", "")


def _assert_not_adopted(base_dir: Path) -> None:
    paths = _paths(base_dir)
    assert not paths.paper_md.exists()
    assert not paths.chunks_jsonl.exists()
    assert not (base_dir / "registry" / "papers.db").exists()
    assert not (base_dir / "index" / "fts.db").exists()
    assert not (base_dir / "graph").exists()


def _assert_saved_source_and_manifest(
    base_dir: Path, expected_state: PaperState = PaperState.BLOCKED
) -> None:
    paths = _paths(base_dir)
    manifest = load_manifest(paths.manifest_json)

    assert paths.source_pdf.read_bytes() == PDF_BYTES
    assert manifest.state == expected_state
    assert manifest.canonical_md is None
    assert manifest.source_pdf is not None
    assert manifest.source_pdf.path == "./source/source.pdf"
    assert manifest.source_pdf.sha256 == sha256_file(paths.source_pdf)


def test_default_off_ready_adopts_existing_canonical_registry_flow(monkeypatch, tmp_path):
    """默认配置仍走确定性转换，并保持原有采用与索引登记语义。"""
    base_dir = tmp_path / "paperbase"
    input_pdf = _write_input_pdf(tmp_path)
    calls: list[tuple[Path, object]] = []

    _install_metadata_stub(monkeypatch)

    def ready_from_saved_source(source_pdf, conversion_config):
        calls.append((source_pdf, conversion_config))
        return ReadyConversionOutcome(CONVERTED_MARKDOWN)

    monkeypatch.setattr(ingest_command, "progressPdfConversion", ready_from_saved_source)

    result = _invoke(base_dir, input_pdf, "--no-graph")

    assert result.exit_code == 0, result.output
    paths = _paths(base_dir)
    manifest = load_manifest(paths.manifest_json)
    with PaperRegistry(base_dir / "registry" / "papers.db") as registry:
        registered = registry.get_paper(PAPER_ID)

    assert len(calls) == 1
    saved_source, conversion_config = calls[0]
    assert saved_source == paths.source_pdf
    assert saved_source != input_pdf
    assert conversion_config.visual.mode == "off"
    assert conversion_config.visual.model == ""
    assert paths.paper_md.exists()
    assert paths.chunks_jsonl.exists()
    assert manifest.state == PaperState.NORMALIZED
    assert manifest.canonical_md is not None
    assert manifest.source_pdf is not None
    assert manifest.source_pdf.path == "./source/source.pdf"
    assert registered is not None
    assert registered["storage_id"] == STORAGE_ID
    assert registered["state"] == PaperState.NORMALIZED.value

    canonical_before = paths.paper_md.read_text(encoding="utf-8")
    manifest_before = paths.manifest_json.read_text(encoding="utf-8")
    normalized_duplicate = _invoke(base_dir, input_pdf, "--no-graph")
    assert normalized_duplicate.exit_code != 0
    assert "DOI 重复" in normalized_duplicate.output
    assert len(calls) == 1
    assert paths.paper_md.read_text(encoding="utf-8") == canonical_before
    assert paths.manifest_json.read_text(encoding="utf-8") == manifest_before

    manifest.state = PaperState.READY
    save_manifest(manifest, paths.manifest_json)
    with PaperRegistry(base_dir / "registry" / "papers.db") as registry:
        registry.update_state(PAPER_ID, PaperState.READY)
    ready_manifest_before = paths.manifest_json.read_text(encoding="utf-8")
    ready_duplicate = _invoke(base_dir, input_pdf, "--no-graph")
    assert ready_duplicate.exit_code != 0
    assert "DOI 重复" in ready_duplicate.output
    assert len(calls) == 1
    assert paths.paper_md.read_text(encoding="utf-8") == canonical_before
    assert paths.manifest_json.read_text(encoding="utf-8") == ready_manifest_before


def test_ready_candidate_failing_canonical_gate_stays_needs_review(monkeypatch, tmp_path):
    """Ready 只表示转换完成；采用前门失败不得写 Canonical 或 Registry。"""
    base_dir = tmp_path / "paperbase"
    input_pdf = _write_input_pdf(tmp_path)
    _install_metadata_stub(monkeypatch)
    monkeypatch.setattr(
        ingest_command,
        "progressPdfConversion",
        lambda source_pdf, conversion_config: ReadyConversionOutcome("short body"),
    )

    result = _invoke(base_dir, input_pdf, "--no-graph")

    assert result.exit_code == 0, result.output
    _assert_saved_source_and_manifest(base_dir, PaperState.NEEDS_REVIEW)
    _assert_not_adopted(base_dir)
    assert "canonical_adoption_gate_failed" in result.output


def test_agent_action_required_blocks_without_adoption_and_prints_host_handoff(
    monkeypatch, tmp_path
):
    """Agent Host 接手前必须只落源 PDF、manifest 与真实任务包交接。"""
    base_dir = tmp_path / "paperbase"
    input_pdf = _write_input_pdf(tmp_path)
    captured_sources: list[Path] = []
    graph_handoff = Mock()
    task_package = base_dir / "agent-work" / "run-001"
    task_package.mkdir(parents=True)
    config_path = base_dir / "config" / "paperbase.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        """conversion:
  pdf:
    visual:
      mode: always
      model: host-selected-model
      chunk_pages: 3
      retry: 0
""",
        encoding="utf-8",
    )

    _install_metadata_stub(monkeypatch)

    def request_agent_action(source_pdf, conversion_config):
        captured_sources.append(source_pdf)
        assert conversion_config.visual.mode == "always"
        assert conversion_config.visual.model == "host-selected-model"
        assert conversion_config.visual.chunk_pages == 3
        assert conversion_config.visual.retry == 0
        return AgentActionRequiredOutcome(task_package=task_package)

    monkeypatch.setattr(ingest_command, "progressPdfConversion", request_agent_action)
    monkeypatch.setattr(ingest_command, "_print_agent_graph_handoff", graph_handoff)
    monkeypatch.setattr(
        "paperbase.core.search_engine.SearchEngine",
        Mock(side_effect=AssertionError("BLOCKED 论文不得更新 FTS")),
    )

    result = _invoke(base_dir, input_pdf)

    assert result.exit_code == 0, result.output
    assert captured_sources == [_paths(base_dir).source_pdf]
    _assert_saved_source_and_manifest(base_dir)
    _assert_not_adopted(base_dir)
    graph_handoff.assert_not_called()
    assert str(task_package) in _output_without_line_breaks(result.output)
    assert "Agent Host" in result.output


def test_failed_or_confirmation_outcomes_remain_unadopted(monkeypatch, tmp_path):
    """能力失败与待确认警告均不得写入 Canonical、检索或 Registry。"""
    warning = "figure crop requires user confirmation"
    cases = [
        (
            "capability",
            FailedConversionOutcome(
                PdfConversionError(
                    code="visual_host_capability_missing",
                    message="Agent Host does not provide visual subagents",
                )
            ),
            PaperState.BLOCKED,
            "visual_host_capability_missing",
        ),
        (
            "confirmation",
            NeedsConfirmationOutcome((warning,)),
            PaperState.NEEDS_REVIEW,
            warning,
        ),
    ]

    _install_metadata_stub(monkeypatch)
    for case_name, outcome, expected_state, expected_output in cases:
        base_dir = tmp_path / case_name / "paperbase"
        input_pdf = tmp_path / case_name / "incoming.pdf"
        input_pdf.parent.mkdir(parents=True)
        input_pdf.write_bytes(PDF_BYTES)
        monkeypatch.setattr(
            ingest_command,
            "progressPdfConversion",
            lambda source_pdf, conversion_config, outcome=outcome: outcome,
        )

        result = _invoke(base_dir, input_pdf, "--no-graph")

        assert result.exit_code == 0, result.output
        _assert_saved_source_and_manifest(base_dir, expected_state)
        _assert_not_adopted(base_dir)
        assert expected_output in result.output


def test_blocked_ingest_resumes_same_saved_source_and_adopts_when_ready(monkeypatch, tmp_path):
    """重复 ingest 需推进同一 BLOCKED 论文，而不是创建第二个身份。"""
    base_dir = tmp_path / "paperbase"
    input_pdf = _write_input_pdf(tmp_path)
    calls: list[Path] = []
    task_packages: list[Path] = []
    _install_metadata_stub(monkeypatch)

    def resume_on_second_progress(source_pdf, conversion_config):
        calls.append(source_pdf)
        if len(calls) == 1:
            task_package = source_pdf.parents[1] / ".visual-runs" / "run-001"
            task_package.mkdir(parents=True)
            task_packages.append(task_package)
            return AgentActionRequiredOutcome(task_package=task_package)
        assert source_pdf == calls[0]
        assert task_packages == [source_pdf.parents[1] / ".visual-runs" / "run-001"]
        return ReadyConversionOutcome(CONVERTED_MARKDOWN)

    monkeypatch.setattr(ingest_command, "progressPdfConversion", resume_on_second_progress)

    first_result = _invoke(base_dir, input_pdf, "--no-graph")
    paths = _paths(base_dir)
    assert first_result.exit_code == 0, first_result.output
    _assert_saved_source_and_manifest(base_dir)
    assert str(task_packages[0]) in _output_without_line_breaks(first_result.output)

    second_result = _invoke(base_dir, input_pdf, "--no-graph")

    assert second_result.exit_code == 0, second_result.output
    assert calls == [paths.source_pdf, paths.source_pdf]
    assert len(list((base_dir / "library" / "papers").glob("p_*.md"))) == 1
    assert len(list((base_dir / "library" / "papers").glob("p_*"))) == 2
    manifest = load_manifest(paths.manifest_json)
    with PaperRegistry(base_dir / "registry" / "papers.db") as registry:
        registered = registry.get_paper(PAPER_ID)
    assert manifest.state == PaperState.NORMALIZED
    assert manifest.canonical_md is not None
    assert paths.paper_md.exists()
    assert paths.chunks_jsonl.exists()
    assert registered is not None
    assert registered["storage_id"] == STORAGE_ID


def test_default_visual_warning_uses_legacy_progress_seam_and_remains_needs_review(
    monkeypatch, tmp_path
):
    """未给 flag 时仍调用旧二参数 progress seam，并把 warning 留在 NEEDS_REVIEW。"""
    base_dir = tmp_path / "paperbase"
    input_pdf = _write_input_pdf(tmp_path)
    _write_always_visual_config(base_dir)
    _install_metadata_stub(monkeypatch)
    cleanup = Mock()
    calls: list[tuple[Path, object]] = []

    def legacy_warning_progress(source_pdf, conversion_config):
        calls.append((source_pdf, conversion_config))
        return NeedsConfirmationOutcome(("A visual crop still needs confirmation.",))

    monkeypatch.setattr(ingest_command, "progressPdfConversion", legacy_warning_progress)
    monkeypatch.setattr(ingest_command, "cleanupReadyVisualRuns", cleanup)

    result = _invoke(base_dir, input_pdf, "--no-graph")

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0][0] == _paths(base_dir).source_pdf
    assert calls[0][1].visual.mode == "always"
    _assert_saved_source_and_manifest(base_dir, PaperState.NEEDS_REVIEW)
    _assert_not_adopted(base_dir)
    cleanup.assert_not_called()


def test_explicit_visual_warning_flag_adopts_assets_and_cleans_ready_run(monkeypatch, tmp_path):
    """CLI flag 必须透传，并只在成功采用后清理已完成视觉运行。"""
    base_dir = tmp_path / "paperbase"
    input_pdf = _write_input_pdf(tmp_path)
    _write_always_visual_config(base_dir)
    _install_metadata_stub(monkeypatch)
    cleanup = Mock(return_value=("run-001",))
    calls: list[bool] = []
    asset_reference = "./assets/visual-page-0001-formula-01.png"
    candidate_markdown = (
        "# Visual ingest fixture\n\n"
        f"![Visual fidelity crop]({asset_reference})\n\n" + ("body evidence. " * 120)
    )

    def ready_after_explicit_accept(source_pdf, conversion_config, *, accept_visual_warnings=False):
        assert conversion_config.visual.mode == "always"
        calls.append(accept_visual_warnings)
        asset_path = source_pdf.parent.parent / asset_reference.removeprefix("./")
        asset_path.parent.mkdir(exist_ok=True)
        asset_path.write_bytes(b"synthetic visual crop")
        return ReadyConversionOutcome(candidate_markdown, (asset_reference,))

    monkeypatch.setattr(ingest_command, "progressPdfConversion", ready_after_explicit_accept)
    monkeypatch.setattr(ingest_command, "cleanupReadyVisualRuns", cleanup)

    result = _invoke(
        base_dir,
        input_pdf,
        "--accept-visual-warnings",
        "--no-graph",
    )

    assert result.exit_code == 0, result.output
    paths = _paths(base_dir)
    manifest = load_manifest(paths.manifest_json)
    assert calls == [True]
    assert manifest.state == PaperState.NORMALIZED
    assert paths.paper_md.exists()
    assert asset_reference in paths.paper_md.read_text(encoding="utf-8")
    assert (
        paths.paper_dir / asset_reference.removeprefix("./")
    ).read_bytes() == b"synthetic visual crop"
    cleanup.assert_called_once_with(paths.paper_dir)


@pytest.mark.parametrize(
    ("code", "expected_state"),
    [
        ("visual_host_capability_missing", PaperState.BLOCKED),
        ("visual_progress_failed", PaperState.FAILED_RETRYABLE),
        ("visual_transient_failure_exhausted", PaperState.FAILED_RETRYABLE),
        ("visual_boundary_review_invalid", PaperState.NEEDS_REVIEW),
        ("visual_preparation_failed", PaperState.FAILED_PERMANENT),
    ],
)
def test_visual_failure_codes_map_to_manifest_states_without_cleanup(
    monkeypatch, tmp_path, code, expected_state
):
    """失败分类保持可恢复、需审核和永久失败的外部状态边界。"""
    base_dir = tmp_path / code / "paperbase"
    input_pdf = tmp_path / code / "incoming.pdf"
    input_pdf.parent.mkdir(parents=True)
    input_pdf.write_bytes(PDF_BYTES)
    _write_always_visual_config(base_dir)
    _install_metadata_stub(monkeypatch)
    cleanup = Mock()

    def failed_progress(source_pdf, conversion_config):
        assert source_pdf == _paths(base_dir).source_pdf
        assert conversion_config.visual.mode == "always"
        return FailedConversionOutcome(PdfConversionError(code=code, message="fixture"))

    monkeypatch.setattr(ingest_command, "progressPdfConversion", failed_progress)
    monkeypatch.setattr(ingest_command, "cleanupReadyVisualRuns", cleanup)

    result = _invoke(base_dir, input_pdf, "--no-graph")

    assert result.exit_code == 0, result.output
    _assert_saved_source_and_manifest(base_dir, expected_state)
    _assert_not_adopted(base_dir)
    cleanup.assert_not_called()


@pytest.mark.parametrize("asset_mode", ["missing", "symlink"])
def test_ready_visual_assets_must_be_local_regular_files_before_adoption(
    monkeypatch, tmp_path, asset_mode
):
    """显式采用不能绕过不存在或链接资产的 Canonical 安全门。"""
    base_dir = tmp_path / asset_mode / "paperbase"
    input_pdf = tmp_path / asset_mode / "incoming.pdf"
    input_pdf.parent.mkdir(parents=True)
    input_pdf.write_bytes(PDF_BYTES)
    _write_always_visual_config(base_dir)
    _install_metadata_stub(monkeypatch)
    cleanup = Mock()
    asset_reference = "./assets/visual-page-0001-formula-01.png"

    def ready_with_unsafe_asset(source_pdf, conversion_config, *, accept_visual_warnings=False):
        assert accept_visual_warnings
        if asset_mode == "symlink":
            external_asset = tmp_path / asset_mode / "external-crop.png"
            external_asset.write_bytes(b"external crop")
            target_asset = source_pdf.parent.parent / asset_reference.removeprefix("./assets/")
            target_asset.parent.mkdir(exist_ok=True)
            try:
                target_asset.symlink_to(external_asset)
            except OSError:
                pytest.skip("当前 Windows 环境不允许创建 asset symlink")
        return ReadyConversionOutcome(CONVERTED_MARKDOWN, (asset_reference,))

    monkeypatch.setattr(ingest_command, "progressPdfConversion", ready_with_unsafe_asset)
    monkeypatch.setattr(ingest_command, "cleanupReadyVisualRuns", cleanup)

    result = _invoke(
        base_dir,
        input_pdf,
        "--accept-visual-warnings",
        "--no-graph",
    )

    assert result.exit_code == 0, result.output
    _assert_saved_source_and_manifest(base_dir, PaperState.NEEDS_REVIEW)
    _assert_not_adopted(base_dir)
    cleanup.assert_not_called()


def test_cleanup_failure_warns_but_keeps_successful_visual_adoption_normalized(
    monkeypatch, tmp_path
):
    """清理临时运行失败只能告警，不能回滚已成功采用的 Canonical。"""
    base_dir = tmp_path / "paperbase"
    input_pdf = _write_input_pdf(tmp_path)
    _write_always_visual_config(base_dir)
    _install_metadata_stub(monkeypatch)

    def ready_progress(source_pdf, conversion_config):
        assert source_pdf == _paths(base_dir).source_pdf
        assert conversion_config.visual.mode == "always"
        return ReadyConversionOutcome(CONVERTED_MARKDOWN)

    monkeypatch.setattr(ingest_command, "progressPdfConversion", ready_progress)
    monkeypatch.setattr(
        ingest_command,
        "cleanupReadyVisualRuns",
        Mock(side_effect=OSError("cleanup fixture failure")),
    )

    result = _invoke(base_dir, input_pdf, "--no-graph")

    assert result.exit_code == 0, result.output
    assert load_manifest(_paths(base_dir).manifest_json).state == PaperState.NORMALIZED
    assert _paths(base_dir).paper_md.exists()
    assert "清理失败" in result.output


def test_batch_forwards_explicit_visual_warning_flag_to_local_pdf_ingest(monkeypatch, tmp_path):
    """batch 以同一显式确认语义调用每个本地 PDF ingest。"""
    base_dir = tmp_path / "paperbase"
    input_pdf = _write_input_pdf(tmp_path)
    batch_file = tmp_path / "batch.txt"
    batch_file.write_text(f"{input_pdf}\n", encoding="utf-8")
    calls: list[tuple[Path, bool, bool, bool]] = []

    def capture_local_ingest(
        ctx,
        pdf_path,
        no_graph,
        headless_graph,
        *,
        accept_visual_warnings=False,
    ):
        calls.append((pdf_path, no_graph, headless_graph, accept_visual_warnings))

    monkeypatch.setattr(ingest_command, "_ingest_local_pdf", capture_local_ingest)

    result = CliRunner().invoke(
        main,
        [
            "--base-dir",
            str(base_dir),
            "ingest",
            "--batch",
            str(batch_file),
            "--accept-visual-warnings",
            "--no-graph",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [(input_pdf, True, False, True)]
