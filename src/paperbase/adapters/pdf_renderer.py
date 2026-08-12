# ruff: noqa: N802
"""将已保存的 PDF 确定性渲染为逐页 PNG。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf

from paperbase.core.visual_repair_run import isPathReparsePoint

DEFAULT_RENDER_ZOOM = 2.0
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PROVENANCE_FILENAME = ".paperbase-render.json"
TEMP_PROVENANCE_FILENAME = ".paperbase-render.json.tmp"


def renderPdfPages(
    source_pdf: Path,
    rendered_dir: Path,
) -> dict[int, Path]:
    """渲染 ``source_pdf`` 的全部页面到 ``rendered_dir``。

    使用固定 2.0 zoom（约 144 DPI），在不引入运行编排参数的前提下提供适合视觉
    worker 阅读的清晰度。已存在完整页集时直接复用；任何部分输出或非预期文件都会
    报错，避免静默覆盖运行现场。
    """
    source_path = Path(source_pdf)
    output_path = Path(rendered_dir)

    _validateSourcePdf(source_path)
    source_sha256 = _calculateFileSha256(source_path)

    try:
        document = pymupdf.open(source_path)
    except Exception as exc:
        raise ValueError(f"无法打开 PDF: {source_path}") from exc

    try:
        page_count = len(document)
        if page_count == 0:
            raise ValueError(f"PDF 不包含可渲染页面: {source_path}")

        rendered_root = _prepareRenderedDir(output_path)
        page_paths = {
            page_number: rendered_root / f"page-{page_number:04d}.png"
            for page_number in range(1, page_count + 1)
        }
        provenance = {
            "page_count": page_count,
            "render_zoom": DEFAULT_RENDER_ZOOM,
            "source_pdf_sha256": source_sha256,
        }
        completed_page_numbers = _getCompletedPageNumbers(
            rendered_root,
            page_paths,
            provenance,
        )

        if not (rendered_root / PROVENANCE_FILENAME).exists():
            _writeProvenanceAtomically(rendered_root, provenance)

        matrix = pymupdf.Matrix(DEFAULT_RENDER_ZOOM, DEFAULT_RENDER_ZOOM)
        for page_number, page_path in page_paths.items():
            if page_number in completed_page_numbers:
                continue
            _ensureWithinRenderedRoot(page_path, rendered_root)
            pixmap = document[page_number - 1].get_pixmap(matrix=matrix, alpha=False)
            _writePixmapAtomically(pixmap, page_path, rendered_root)

        return page_paths
    finally:
        document.close()


def _validateSourcePdf(source_path: Path) -> None:
    if not source_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {source_path}")
    _requireNoReparseAncestor(source_path, "PDF 路径")
    if not source_path.is_file():
        raise ValueError(f"PDF 路径不是文件: {source_path}")


def _calculateFileSha256(source_path: Path) -> str:
    digest = hashlib.sha256()
    with source_path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepareRenderedDir(output_path: Path) -> Path:
    _requireNoReparseAncestor(output_path.parent, "rendered 输出父目录")
    if isPathReparsePoint(output_path):
        raise ValueError(f"rendered 输出目录不能是 reparse point: {output_path}")
    if output_path.exists() and not output_path.is_dir():
        raise ValueError(f"rendered 输出路径不是目录: {output_path}")

    output_path.mkdir(parents=True, exist_ok=True)
    if (
        isPathReparsePoint(output_path.parent)
        or isPathReparsePoint(output_path)
        or not output_path.is_dir()
    ):
        raise ValueError(f"rendered 输出目录不能是 reparse point: {output_path}")
    return output_path.resolve()


def _requireNoReparseAncestor(path: Path, label: str) -> None:
    current = Path(path)
    while True:
        if isPathReparsePoint(current):
            raise ValueError(f"{label}不能包含 reparse point: {current}")
        if current.parent == current:
            return
        current = current.parent


def _getCompletedPageNumbers(
    rendered_root: Path,
    page_paths: dict[int, Path],
    expected_provenance: dict[str, str | float | int],
) -> set[int]:
    _removeTemporaryFiles(rendered_root, page_paths)
    existing_entries = list(rendered_root.iterdir())
    if not existing_entries:
        return set()

    expected_names = {page_path.name for page_path in page_paths.values()}
    expected_names.add(PROVENANCE_FILENAME)
    existing_names = {entry.name for entry in existing_entries}
    if not existing_names.issubset(expected_names):
        raise FileExistsError(f"rendered 目录包含冲突文件: {rendered_root}")

    if any(not entry.is_file() or isPathReparsePoint(entry) for entry in existing_entries):
        raise FileExistsError(f"rendered 目录包含非普通文件: {rendered_root}")

    completed_page_numbers = set()
    for page_number, page_path in page_paths.items():
        if not page_path.exists():
            continue
        with page_path.open("rb") as image_file:
            signature = image_file.read(len(PNG_SIGNATURE))
        if signature != PNG_SIGNATURE:
            raise FileExistsError(f"rendered 目录包含无效页图像: {rendered_root}")
        completed_page_numbers.add(page_number)

    provenance_path = rendered_root / PROVENANCE_FILENAME
    if not provenance_path.exists():
        raise FileExistsError(f"rendered 目录包含冲突文件且缺少 provenance: {rendered_root}")
    if _readProvenance(provenance_path) != expected_provenance:
        raise ValueError(f"rendered provenance 不匹配，拒绝复用: {rendered_root}")

    return completed_page_numbers


def _removeTemporaryFiles(rendered_root: Path, page_paths: dict[int, Path]) -> None:
    temporary_paths = {rendered_root / TEMP_PROVENANCE_FILENAME}
    temporary_paths.update(_temporaryPagePath(page_path) for page_path in page_paths.values())

    for temporary_path in temporary_paths:
        if not temporary_path.exists() and not isPathReparsePoint(temporary_path):
            continue
        if isPathReparsePoint(temporary_path) or not temporary_path.is_file():
            raise FileExistsError(f"rendered 目录包含非普通临时文件: {temporary_path}")
        temporary_path.unlink()


def _readProvenance(provenance_path: Path) -> dict[str, str | float | int]:
    try:
        with provenance_path.open("r", encoding="utf-8") as provenance_file:
            provenance = json.load(provenance_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise FileExistsError(f"rendered provenance 无效: {provenance_path}") from exc

    if not isinstance(provenance, dict):
        raise FileExistsError(f"rendered provenance 无效: {provenance_path}")
    return provenance


def _writeProvenanceAtomically(
    rendered_root: Path,
    provenance: dict[str, str | float | int],
) -> None:
    provenance_path = rendered_root / PROVENANCE_FILENAME
    temporary_path = rendered_root / TEMP_PROVENANCE_FILENAME
    _ensureWithinRenderedRoot(provenance_path, rendered_root)
    _ensureWithinRenderedRoot(temporary_path, rendered_root)

    with temporary_path.open("xb") as temporary_file:
        temporary_file.write(json.dumps(provenance, sort_keys=True).encode("utf-8"))
    temporary_path.rename(provenance_path)


def _writePixmapAtomically(pixmap: pymupdf.Pixmap, page_path: Path, rendered_root: Path) -> None:
    temporary_path = _temporaryPagePath(page_path)
    _ensureWithinRenderedRoot(temporary_path, rendered_root)

    with temporary_path.open("xb") as temporary_file:
        temporary_file.write(pixmap.tobytes("png"))
    temporary_path.rename(page_path)


def _temporaryPagePath(page_path: Path) -> Path:
    return page_path.with_name(f".{page_path.name}.tmp")


def _ensureWithinRenderedRoot(page_path: Path, rendered_root: Path) -> None:
    try:
        page_path.resolve().relative_to(rendered_root)
    except ValueError as exc:
        raise ValueError(f"渲染输出越出 rendered 根目录: {page_path}") from exc
