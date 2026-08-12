"""Prepare host-neutral visual conversion runs without mutating Canonical data."""

from __future__ import annotations

# ruff: noqa: N802
import hashlib
import os
from pathlib import Path
from typing import Any

from paperbase.adapters.pdf_renderer import renderPdfPages
from paperbase.config.models import VisualPdfConfig
from paperbase.core.visual_repair_run import isPathReparsePoint, prepareVisualRun
from paperbase.core.visual_task_package import VisualChunkPlan, prepareVisualTaskPackage

VISUAL_TEMPLATE_VERSION = "visual-pdf-v1"
CHUNKING_SCHEME_VERSION = "contiguous-core-adjacent-context-v1"


def prepareVisualConversion(  # noqa: N802
    source_pdf: Path,
    candidate_markdown: str,
    visual_config: VisualPdfConfig,
) -> Path:
    """Prepare or resume one visual run and return its complete task package root.

    Only the previously saved ``<paper_dir>/source/source.pdf`` is accepted.
    The function writes solely under ``<paper_dir>/.visual-runs`` and does not
    write Canonical Markdown, assets, manifests, or registry data.
    """
    source_path, paper_dir = _validateSavedSourcePdf(source_pdf)
    candidate_bytes = _encodeCandidate(candidate_markdown)
    source_sha256 = _calculateFileSha256(source_path)
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
    page_count = _getPdfPageCount(source_path)
    chunk_plans = _makeChunkPlans(page_count, visual_config.chunk_pages)
    chunking_scheme = _makeChunkingScheme(page_count, visual_config.chunk_pages, chunk_plans)

    run = prepareVisualRun(
        paper_dir,
        source_sha256,
        candidate_sha256,
        VISUAL_TEMPLATE_VERSION,
        chunking_scheme,
        [plan.chunk_id for plan in chunk_plans],
        model_name=visual_config.model,
    )
    run_dir = paper_dir / ".visual-runs" / run.run_id
    _writeOrValidateCandidate(run_dir / "candidate.md", candidate_bytes, candidate_sha256)

    rendered_pages = renderPdfPages(source_path, run_dir / "rendered")
    if len(rendered_pages) != page_count:
        raise ValueError("rendered PDF page count does not match the source page count")

    prepareVisualTaskPackage(
        run_dir,
        page_count,
        chunk_plans,
        {plan.chunk_id: candidate_markdown for plan in chunk_plans},
        rendered_pages,
        requested_model=visual_config.model,
        template_version=VISUAL_TEMPLATE_VERSION,
        candidate_fragment_scope="full_document",
    )
    return run_dir


def _validateSavedSourcePdf(source_pdf: Path) -> tuple[Path, Path]:
    source_path = Path(source_pdf)
    if source_path.name != "source.pdf" or source_path.parent.name != "source":
        raise ValueError("visual conversion requires <paper_dir>/source/source.pdf")
    paper_dir = source_path.parent.parent
    if (
        isPathReparsePoint(paper_dir)
        or isPathReparsePoint(source_path.parent)
        or isPathReparsePoint(source_path)
        or not source_path.is_file()
    ):
        raise ValueError("visual conversion source PDF must be a regular non-link file")
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


def _getPdfPageCount(source_pdf: Path) -> int:
    import pymupdf

    try:
        document = pymupdf.open(source_pdf)
    except Exception as exc:
        raise ValueError("cannot open source PDF for visual conversion") from exc
    try:
        page_count = len(document)
    finally:
        document.close()
    if page_count <= 0:
        raise ValueError("source PDF has no renderable pages")
    return page_count


def _makeChunkPlans(page_count: int, chunk_pages: int) -> tuple[VisualChunkPlan, ...]:
    if isinstance(chunk_pages, bool) or not isinstance(chunk_pages, int) or chunk_pages <= 0:
        raise ValueError("visual chunk_pages must be a positive integer")

    plans: list[VisualChunkPlan] = []
    for chunk_index, first_page in enumerate(range(1, page_count + 1, chunk_pages), start=1):
        last_page = min(first_page + chunk_pages - 1, page_count)
        context_pages = tuple(
            page_number
            for page_number in (first_page - 1, last_page + 1)
            if 1 <= page_number <= page_count
        )
        plans.append(
            VisualChunkPlan(
                chunk_id=f"chunk-{chunk_index:03d}",
                core_pages=tuple(range(first_page, last_page + 1)),
                context_pages=context_pages,
            )
        )
    return tuple(plans)


def _makeChunkingScheme(
    page_count: int,
    chunk_pages: int,
    chunk_plans: tuple[VisualChunkPlan, ...],
) -> dict[str, Any]:
    return {
        "version": CHUNKING_SCHEME_VERSION,
        "page_count": page_count,
        "chunk_pages": chunk_pages,
        "chunks": [
            {
                "chunk_id": plan.chunk_id,
                "core_pages": list(plan.core_pages),
                "context_pages": list(plan.context_pages),
            }
            for plan in chunk_plans
        ],
    }


def _writeOrValidateCandidate(
    candidate_path: Path,
    candidate_bytes: bytes,
    expected_sha256: str,
) -> None:
    if candidate_path.exists() or candidate_path.is_symlink():
        if not candidate_path.is_file() or candidate_path.is_symlink():
            raise ValueError("run-local candidate.md must be a regular file")
        existing_bytes = candidate_path.read_bytes()
        if existing_bytes != candidate_bytes:
            raise ValueError("run-local candidate.md does not match the requested candidate")
        if hashlib.sha256(existing_bytes).hexdigest() != expected_sha256:
            raise ValueError("run-local candidate.md SHA256 does not match the requested candidate")
        return

    try:
        with candidate_path.open("x", encoding="utf-8", newline="") as candidate_file:
            candidate_file.write(candidate_bytes.decode("utf-8"))
            candidate_file.flush()
            os.fsync(candidate_file.fileno())
    except FileExistsError:
        _writeOrValidateCandidate(candidate_path, candidate_bytes, expected_sha256)
