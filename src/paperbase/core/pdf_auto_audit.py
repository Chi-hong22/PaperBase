"""Prepare and progress the host-neutral automatic PDF text audit."""

# ruff: noqa: N802
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from paperbase.core.visual_conversion import prepareVisualConversion  # noqa: F401
from paperbase.core.visual_repair_run import isPathReparsePoint

if TYPE_CHECKING:
    from paperbase.config.models import VisualPdfConfig
    from paperbase.core.pdf_conversion import PdfConversionOutcome


AUTO_AUDIT_VERSION = "pdf-auto-text-audit-v2"
LAYOUT_EVIDENCE_VERSION = "pdf-auto-layout-v1"
RESULT_KIND = "pdf_auto_text_audit_result"
MIN_COLUMN_BLOCKS_PER_SIDE = 2
MAIN_VERTICAL_TOP_RATIO = 0.15
MAIN_VERTICAL_BOTTOM_RATIO = 0.85
MIN_COLUMN_VERTICAL_OVERLAP_RATIO = 0.20
TEXT_PREVIEW_LIMIT = 120


class _AutoAuditResultError(ValueError):
    """The worker-owned result.json is absent, malformed, or incompatible."""


@dataclass(frozen=True)
class _AutoAuditResult:
    decision: str
    layout: str
    flagged_pages: tuple[int, ...]
    reasons: tuple[str, ...]


def prepareOrProgressPdfAutoAudit(  # noqa: N802
    source_pdf: Path,
    candidate_markdown: str,
    visual_config: VisualPdfConfig,
    *,
    accept_visual_warnings: bool = False,
) -> PdfConversionOutcome:
    """Return the next auto-routing outcome without invoking an Agent Host.

    PaperBase owns all files except ``result.json``.  A compatible audit is
    identified by the source PDF and Candidate hashes, so a model-name change
    can update only the task request without invalidating the worker result.
    """
    from paperbase.core.pdf_conversion import (
        AgentActionRequiredOutcome,
        FailedConversionOutcome,
        PdfConversionError,
        ReadyConversionOutcome,
    )

    source_path, paper_dir = _validateSavedSourcePdf(source_pdf)
    candidate_bytes = _encodeCandidate(candidate_markdown)
    source_sha256 = _calculateFileSha256(source_path)
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
    audit_dir = _auditDirectory(paper_dir, source_sha256, candidate_sha256)

    try:
        layout = _buildLayoutEvidence(source_path, source_sha256, candidate_sha256)
        _prepareAuditPackage(
            audit_dir,
            candidate_bytes,
            source_sha256,
            candidate_sha256,
            layout,
            visual_config.model,
        )
    except _AutoAuditResultError:
        return FailedConversionOutcome(
            error=PdfConversionError(
                code="visual_auto_audit_result_invalid",
                message="pdf auto audit result.json is not a valid compatible worker result",
            )
        )

    result_path = audit_dir / "result.json"
    if not result_path.exists() and not result_path.is_symlink():
        return AgentActionRequiredOutcome(task_package=audit_dir)

    try:
        result = _loadAndValidateResult(
            result_path,
            source_sha256,
            candidate_sha256,
            layout,
        )
    except _AutoAuditResultError:
        return FailedConversionOutcome(
            error=PdfConversionError(
                code="visual_auto_audit_result_invalid",
                message="pdf auto audit result.json is not a valid compatible worker result",
            )
        )

    if result.decision == "pass":
        return ReadyConversionOutcome(markdown=candidate_markdown, assets=())

    from paperbase.core.visual_progress import prepareOrProgressVisualConversion

    if accept_visual_warnings:
        return prepareOrProgressVisualConversion(
            source_path,
            candidate_markdown,
            visual_config,
            accept_visual_warnings=True,
        )
    return prepareOrProgressVisualConversion(source_path, candidate_markdown, visual_config)


def _validateSavedSourcePdf(source_pdf: Path) -> tuple[Path, Path]:
    source_path = Path(source_pdf)
    if source_path.name != "source.pdf" or source_path.parent.name != "source":
        raise ValueError("pdf auto audit requires <paper_dir>/source/source.pdf")
    paper_dir = source_path.parent.parent
    if any(isPathReparsePoint(path) for path in (paper_dir, source_path.parent, source_path)):
        raise ValueError("pdf auto audit source path must not contain a reparse point")
    if not _isRegularFile(source_path):
        raise ValueError("pdf auto audit source PDF must be a regular file")
    return source_path, paper_dir


def _encodeCandidate(candidate_markdown: str) -> bytes:
    if not isinstance(candidate_markdown, str):
        raise TypeError("candidate_markdown must be text")
    try:
        return candidate_markdown.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("candidate_markdown must be UTF-8 encodable") from exc


def _calculateFileSha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _auditDirectory(paper_dir: Path, source_sha256: str, candidate_sha256: str) -> Path:
    audit_root = paper_dir / ".visual-auto-audit"
    _ensureDirectory(audit_root, "pdf auto audit root")
    audit_id = f"{source_sha256[:12]}-{candidate_sha256[:12]}-{AUTO_AUDIT_VERSION}"
    audit_dir = audit_root / audit_id
    _ensureDirectory(audit_dir, "pdf auto audit directory")
    return audit_dir


def _ensureDirectory(path: Path, label: str) -> None:
    if path.exists() or isPathReparsePoint(path):
        if isPathReparsePoint(path) or not path.is_dir():
            raise ValueError(f"{label} must be a regular non-reparse directory")
        return
    path.mkdir()
    if isPathReparsePoint(path) or not path.is_dir():
        raise ValueError(f"{label} must be a regular non-reparse directory")


def _buildLayoutEvidence(
    source_pdf: Path,
    source_sha256: str,
    candidate_sha256: str,
) -> dict[str, Any]:
    import pymupdf

    try:
        document = pymupdf.open(source_pdf)
    except Exception as exc:
        raise ValueError("cannot open source PDF for automatic layout audit") from exc

    try:
        pages = [
            _buildPageLayout(page, page_number) for page_number, page in enumerate(document, 1)
        ]
    finally:
        document.close()

    if not pages:
        raise ValueError("source PDF has no renderable pages")
    return {
        "kind": "pdf_auto_layout_evidence",
        "version": LAYOUT_EVIDENCE_VERSION,
        "source_pdf_sha256": source_sha256,
        "candidate_sha256": candidate_sha256,
        "page_count": len(pages),
        "pages": pages,
    }


def _buildPageLayout(page: Any, page_number: int) -> dict[str, Any]:
    width = float(page.rect.width)
    height = float(page.rect.height)
    page_text = str(page.get_text("text"))
    text_blocks = _extractTextBlocks(page)
    column_suspected, column_evidence = _detectSuspectedColumns(text_blocks, width, height)
    return {
        "page_number": page_number,
        "width": width,
        "height": height,
        "is_empty": not page_text.strip(),
        "char_count": len(page_text),
        "replacement_char_count": page_text.count("\ufffd"),
        "control_char_count": _countControlCharacters(page_text),
        "text_blocks": text_blocks,
        "column_suspected": column_suspected,
        "column_evidence": column_evidence,
    }


def _extractTextBlocks(page: Any) -> list[dict[str, Any]]:
    text_blocks: list[dict[str, Any]] = []
    for block in page.get_text("blocks"):
        if len(block) < 5 or (len(block) > 6 and block[6] != 0):
            continue
        raw_text = block[4]
        if not isinstance(raw_text, str) or not raw_text:
            continue
        compact_text = " ".join(raw_text.split())
        text_blocks.append(
            {
                "bbox": [float(value) for value in block[:4]],
                "char_count": len(raw_text),
                "line_count": raw_text.count("\n") + (1 if raw_text else 0),
                "text_preview": compact_text[:TEXT_PREVIEW_LIMIT],
            }
        )
    return text_blocks


def _countControlCharacters(text: str) -> int:
    return sum(
        1 for character in text if ord(character) < 32 and character not in {"\n", "\r", "\t"}
    )


def _detectSuspectedColumns(
    text_blocks: list[dict[str, Any]],
    width: float,
    height: float,
) -> tuple[bool, dict[str, Any]]:
    main_top = height * MAIN_VERTICAL_TOP_RATIO
    main_bottom = height * MAIN_VERTICAL_BOTTOM_RATIO
    middle = width / 2
    left_blocks = [
        block
        for block in text_blocks
        if block["bbox"][2] <= middle
        and _overlapsVerticalRegion(block["bbox"], main_top, main_bottom)
    ]
    right_blocks = [
        block
        for block in text_blocks
        if block["bbox"][0] >= middle
        and _overlapsVerticalRegion(block["bbox"], main_top, main_bottom)
    ]
    vertical_overlap = _columnVerticalOverlap(left_blocks, right_blocks, main_top, main_bottom)
    minimum_overlap = height * MIN_COLUMN_VERTICAL_OVERLAP_RATIO
    column_suspected = (
        len(left_blocks) >= MIN_COLUMN_BLOCKS_PER_SIDE
        and len(right_blocks) >= MIN_COLUMN_BLOCKS_PER_SIDE
        and vertical_overlap >= minimum_overlap
    )
    return column_suspected, {
        "left_block_count": len(left_blocks),
        "right_block_count": len(right_blocks),
        "main_vertical_region": [main_top, main_bottom],
        "vertical_overlap": vertical_overlap,
        "minimum_vertical_overlap": minimum_overlap,
    }


def _overlapsVerticalRegion(bbox: list[float], top: float, bottom: float) -> bool:
    return bbox[3] > top and bbox[1] < bottom


def _columnVerticalOverlap(
    left_blocks: list[dict[str, Any]],
    right_blocks: list[dict[str, Any]],
    main_top: float,
    main_bottom: float,
) -> float:
    if not left_blocks or not right_blocks:
        return 0.0
    left_top = min(max(block["bbox"][1], main_top) for block in left_blocks)
    left_bottom = max(min(block["bbox"][3], main_bottom) for block in left_blocks)
    right_top = min(max(block["bbox"][1], main_top) for block in right_blocks)
    right_bottom = max(min(block["bbox"][3], main_bottom) for block in right_blocks)
    return max(0.0, min(left_bottom, right_bottom) - max(left_top, right_top))


def _prepareAuditPackage(
    audit_dir: Path,
    candidate_bytes: bytes,
    source_sha256: str,
    candidate_sha256: str,
    layout: Mapping[str, Any],
    requested_model: str,
) -> None:
    _validateAuditDirectoryEntries(audit_dir)
    _writeOrValidateBytes(audit_dir / "candidate.md", candidate_bytes, "candidate.md")
    _writeOrValidateJson(audit_dir / "layout.json", layout, "layout.json")
    layout_sha256 = _calculateFileSha256(audit_dir / "layout.json")
    expected_task = _makeTask(
        source_sha256,
        candidate_sha256,
        layout_sha256,
        requested_model,
        layout,
    )
    _writeOrUpdateTask(audit_dir / "task.json", expected_task)
    _validateAuditDirectoryEntries(audit_dir, require_inputs=True)


def _validateAuditDirectoryEntries(audit_dir: Path, *, require_inputs: bool = False) -> None:
    allowed_names = {"candidate.md", "layout.json", "task.json", "result.json"}
    actual_names = {entry.name for entry in audit_dir.iterdir()}
    unexpected_names = actual_names - allowed_names
    if unexpected_names:
        raise ValueError("pdf auto audit directory contains unexpected files")
    required_names = {"candidate.md", "layout.json", "task.json"} if require_inputs else set()
    if not required_names.issubset(actual_names):
        raise ValueError("pdf auto audit directory is missing required inputs")
    for name in actual_names:
        path = audit_dir / name
        if not _isRegularFile(path):
            if name == "result.json":
                raise _AutoAuditResultError("result.json must be a regular file")
            raise ValueError(f"{name} must be a regular file")


def _makeTask(
    source_sha256: str,
    candidate_sha256: str,
    layout_sha256: str,
    requested_model: str,
    layout: Mapping[str, Any],
) -> dict[str, Any]:
    deterministic_quality_gate = _deterministicQualityGate(layout)
    return {
        "kind": "pdf_auto_text_audit",
        "version": AUTO_AUDIT_VERSION,
        "requested_model": requested_model,
        "inputs": {
            "source_pdf": {
                "path": "../../source/source.pdf",
                "sha256": source_sha256,
            },
            "candidate": {
                "path": "candidate.md",
                "sha256": candidate_sha256,
            },
            "layout": {
                "path": "layout.json",
                "sha256": layout_sha256,
            },
        },
        "worker_output": {
            "path": "result.json",
            "schema": {
                "kind": RESULT_KIND,
                "version": AUTO_AUDIT_VERSION,
                "source_pdf_sha256": source_sha256,
                "candidate_sha256": candidate_sha256,
                "decision": ["pass", "visual_required"],
                "layout": ["single_column", "multi_column", "uncertain"],
                "flagged_pages": "unique ascending page numbers within page_count",
                "reasons": "non-empty list of non-empty strings",
                "deterministic_rule": (
                    "flagged_pages must include every page listed in "
                    "deterministic_quality_gate.flagged_pages; pass is forbidden when that list is non-empty"
                ),
            },
        },
        "deterministic_quality_gate": deterministic_quality_gate,
        "instructions": [
            "Review candidate.md together with layout.json; do not treat layout evidence as a final judgement.",
            "Two-column reading-order errors are not necessarily garbled text and cannot be excluded from Markdown alone.",
            "Return visual_required for multi_column, uncertain, or any reading-order symptom; this first version upgrades the whole document.",
            "Return pass only for a single-column reading order with no flagged pages.",
            "Pages in deterministic_quality_gate.flagged_pages contain locally measured bad-text signals; include all of them in result.json flagged_pages and never return pass when this gate is non-empty.",
            "Include the source_pdf_sha256 and candidate_sha256 values from inputs in result.json.",
            "Write only result.json. Do not modify candidate.md, layout.json, task.json, source PDF, Canonical data, or manifests.",
        ],
    }


def _writeOrValidateBytes(path: Path, expected: bytes, label: str) -> None:
    if path.exists() or path.is_symlink():
        if not _isRegularFile(path):
            raise ValueError(f"{label} must be a regular file")
        if path.read_bytes() != expected:
            raise ValueError(f"{label} does not match current automatic audit inputs")
        return
    _writeBytesAtomically(path, expected)


def _writeOrValidateJson(path: Path, expected: Mapping[str, Any], label: str) -> None:
    if path.exists() or path.is_symlink():
        if not _isRegularFile(path):
            raise ValueError(f"{label} must be a regular file")
        if _readJsonObject(path, label) != dict(expected):
            raise ValueError(f"{label} does not match current automatic audit inputs")
        return
    _writeJsonAtomically(path, expected)


def _writeOrUpdateTask(path: Path, expected: Mapping[str, Any]) -> None:
    if not path.exists() and not path.is_symlink():
        _writeJsonAtomically(path, expected)
        return
    if not _isRegularFile(path):
        raise ValueError("task.json must be a regular file")
    existing = _readJsonObject(path, "task.json")
    if set(existing) != set(expected) or _withoutRequestedModel(existing) != _withoutRequestedModel(
        expected
    ):
        raise ValueError("task.json does not match current automatic audit inputs")
    if existing != dict(expected):
        _writeJsonAtomically(path, expected)


def _withoutRequestedModel(task: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in task.items() if key != "requested_model"}


def _loadAndValidateResult(
    result_path: Path,
    source_sha256: str,
    candidate_sha256: str,
    layout: Mapping[str, Any],
) -> _AutoAuditResult:
    if not _isRegularFile(result_path):
        raise _AutoAuditResultError("result.json must be a regular file")
    data = _readJsonObject(result_path, "result.json", result_error=True)
    expected_keys = {
        "kind",
        "version",
        "source_pdf_sha256",
        "candidate_sha256",
        "decision",
        "layout",
        "flagged_pages",
        "reasons",
    }
    if set(data) != expected_keys:
        raise _AutoAuditResultError("result.json schema does not match")
    if data["kind"] != RESULT_KIND or data["version"] != AUTO_AUDIT_VERSION:
        raise _AutoAuditResultError("result.json kind or version does not match")
    if data["source_pdf_sha256"] != source_sha256 or data["candidate_sha256"] != candidate_sha256:
        raise _AutoAuditResultError("result.json input identity does not match")
    if data["decision"] not in {"pass", "visual_required"}:
        raise _AutoAuditResultError("result.json decision is invalid")
    if data["layout"] not in {"single_column", "multi_column", "uncertain"}:
        raise _AutoAuditResultError("result.json layout is invalid")
    page_count = int(layout["page_count"])
    flagged_pages = _validateFlaggedPages(data["flagged_pages"], page_count)
    reasons = _validateReasons(data["reasons"])
    deterministic_flagged_pages = tuple(_deterministicQualityGate(layout)["flagged_pages"])
    if not set(deterministic_flagged_pages).issubset(flagged_pages):
        raise _AutoAuditResultError(
            "result.json flagged_pages omits deterministic bad-text signals"
        )
    if data["decision"] == "pass" and (data["layout"] != "single_column" or flagged_pages):
        raise _AutoAuditResultError("pass result must be single-column with no flagged pages")
    return _AutoAuditResult(
        decision=data["decision"],
        layout=data["layout"],
        flagged_pages=flagged_pages,
        reasons=reasons,
    )


def _deterministicQualityGate(layout: Mapping[str, Any]) -> dict[str, Any]:
    signals: dict[str, list[str]] = {}
    pages = layout.get("pages")
    if not isinstance(pages, list):
        raise ValueError("layout evidence pages must be a list")
    for page in pages:
        if not isinstance(page, Mapping):
            raise ValueError("layout evidence page must be an object")
        page_number = page.get("page_number")
        if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
            raise ValueError("layout evidence page_number must be a positive integer")
        page_signals: list[str] = []
        if _positiveSignalCount(page.get("replacement_char_count"), "replacement_char_count"):
            page_signals.append("replacement_characters")
        if _positiveSignalCount(page.get("control_char_count"), "control_char_count"):
            page_signals.append("control_characters")
        if page_signals:
            signals[str(page_number)] = page_signals
    return {
        "flagged_pages": sorted(int(page_number) for page_number in signals),
        "signals": signals,
    }


def _positiveSignalCount(value: Any, field_name: str) -> bool:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"layout evidence {field_name} must be a non-negative integer")
    return value > 0


def _validateFlaggedPages(value: Any, page_count: int) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise _AutoAuditResultError("result.json flagged_pages must be a list")
    if any(isinstance(page, bool) or not isinstance(page, int) for page in value):
        raise _AutoAuditResultError("result.json flagged_pages must contain integers")
    if any(page < 1 or page > page_count for page in value):
        raise _AutoAuditResultError("result.json flagged_pages is outside source page range")
    if value != sorted(set(value)):
        raise _AutoAuditResultError("result.json flagged_pages must be unique and ascending")
    return tuple(value)


def _validateReasons(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise _AutoAuditResultError("result.json reasons must be a non-empty list")
    if any(not isinstance(reason, str) or not reason.strip() for reason in value):
        raise _AutoAuditResultError("result.json reasons must contain non-empty strings")
    return tuple(value)


def _readJsonObject(
    path: Path,
    label: str,
    *,
    result_error: bool = False,
) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        if result_error:
            raise _AutoAuditResultError(f"{label} is not valid UTF-8 JSON") from exc
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        if result_error:
            raise _AutoAuditResultError(f"{label} must be a JSON object")
        raise ValueError(f"{label} must be a JSON object")
    return data


def _writeJsonAtomically(path: Path, data: Mapping[str, Any]) -> None:
    encoded = (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    _writeBytesAtomically(path, encoded)


def _writeBytesAtomically(path: Path, data: bytes) -> None:
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _isRegularFile(path: Path) -> bool:
    return path.is_file() and not isPathReparsePoint(path)
