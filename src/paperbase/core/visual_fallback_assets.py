"""Run-local visual-fidelity assets and page-local Markdown injection."""

from __future__ import annotations

# ruff: noqa: N802
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from paperbase.adapters.visual_fallback_crop import (
    VisualFallbackCropError,
    renderVisualFallbackCrop,
)
from paperbase.core.visual_chunk_result import (
    VisualChunkResult,
    VisualChunkResultError,
    mergeVisualChunkResults,
    validateVisualChunkResult,
)
from paperbase.core.visual_repair_run import isPathReparsePoint


class VisualFallbackAssetsError(ValueError):
    """Fallback assets cannot be prepared from this visual-repair run."""


@dataclass(frozen=True)
class VisualFallbackAsset:
    """One run-local crop and its eventual Canonical relative path."""

    source_path: Path
    canonical_relative_path: str
    page: int
    kind: str


@dataclass(frozen=True)
class VisualFallbackAssets:
    """The final marker-free Markdown plus deferred local asset plan."""

    markdown: str
    assets: tuple[VisualFallbackAsset, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _CropPlan:
    page: int
    kind: str
    bbox: tuple[float, float, float, float]
    filename: str


def prepareVisualFallbackAssets(run_dir: Path) -> VisualFallbackAssets:
    """Materialize run-local fallback crops and inject explicit Markdown references."""
    normalized_run_dir = _validateRunDir(run_dir)
    merged_markdown = _mergeCompletedChunks(normalized_run_dir)
    chunk_results = _loadCompletedChunkResults(normalized_run_dir)
    if not any(result.crop_requests for result in chunk_results):
        fallback_root = normalized_run_dir / "fallback-assets"
        if fallback_root.exists() or isPathReparsePoint(fallback_root):
            raise VisualFallbackAssetsError(_noCropResidualFallbackMessage(fallback_root))
        warnings = tuple(warning for result in chunk_results for warning in result.warnings)
        return VisualFallbackAssets(merged_markdown, (), warnings)

    crop_plans = _makeCropPlans(chunk_results)
    fallback_root = normalized_run_dir / "fallback-assets"
    crop_bytes = _renderCropBytes(normalized_run_dir, crop_plans)
    _materializeFallbackAssets(fallback_root, crop_bytes)
    assets = tuple(
        VisualFallbackAsset(
            source_path=fallback_root / crop_plan.filename,
            canonical_relative_path=f"./assets/{crop_plan.filename}",
            page=crop_plan.page,
            kind=crop_plan.kind,
        )
        for crop_plan in crop_plans
    )
    page_markdown = {
        page_number: markdown
        for result in chunk_results
        for page_number, markdown in result.page_markdown.items()
    }
    markdown = _mergeInjectedPages(page_markdown, assets)
    warnings = tuple(warning for result in chunk_results for warning in result.warnings) + tuple(
        f"Visual fidelity crop on page {asset.page} ({asset.kind}) requires user confirmation."
        for asset in assets
    )
    return VisualFallbackAssets(markdown, assets, warnings)


def _validateRunDir(run_dir: Path) -> Path:
    path = Path(run_dir)
    if isPathReparsePoint(path) or not path.is_dir() or path.parent.name != ".visual-runs":
        raise VisualFallbackAssetsError("run_dir must be a regular run directly under .visual-runs")
    return path.resolve()


def _mergeCompletedChunks(run_dir: Path) -> str:
    try:
        return mergeVisualChunkResults(run_dir)
    except VisualChunkResultError as exc:
        raise VisualFallbackAssetsError(
            "fallback assets require a mergeable completed run"
        ) from exc


def _loadCompletedChunkResults(run_dir: Path) -> tuple[VisualChunkResult, ...]:
    tasks_root = run_dir / "tasks"
    if isPathReparsePoint(tasks_root) or not tasks_root.is_dir():
        raise VisualFallbackAssetsError("visual run tasks directory is missing or unsafe")
    results: list[VisualChunkResult] = []
    for entry in sorted(os.scandir(tasks_root), key=lambda item: item.name):
        task_dir = Path(entry.path)
        if isPathReparsePoint(task_dir) or not entry.is_dir(follow_symlinks=False):
            raise VisualFallbackAssetsError("visual run tasks directory contains an unsafe entry")
        try:
            result = validateVisualChunkResult(task_dir)
        except VisualChunkResultError as exc:
            raise VisualFallbackAssetsError(
                "visual worker result cannot produce fallback assets"
            ) from exc
        if result.status != "completed":
            raise VisualFallbackAssetsError("fallback assets require every chunk to be completed")
        results.append(result)
    if not results:
        raise VisualFallbackAssetsError("visual run has no completed chunk results")
    return tuple(sorted(results, key=lambda result: result.core_pages[0]))


def _makeCropPlans(chunk_results: Sequence[VisualChunkResult]) -> tuple[_CropPlan, ...]:
    per_page_kind_count: dict[tuple[int, str], int] = {}
    plans: list[_CropPlan] = []
    for result in chunk_results:
        for request in result.crop_requests:
            counter_key = (request.page, request.kind)
            ordinal = per_page_kind_count.get(counter_key, 0) + 1
            per_page_kind_count[counter_key] = ordinal
            plans.append(
                _CropPlan(
                    page=request.page,
                    kind=request.kind,
                    bbox=request.bbox,
                    filename=f"visual-page-{request.page:04d}-{request.kind}-{ordinal:02d}.png",
                )
            )
    return tuple(plans)


def _renderCropBytes(run_dir: Path, crop_plans: Sequence[_CropPlan]) -> dict[str, bytes]:
    rendered_root = run_dir / "rendered"
    if isPathReparsePoint(rendered_root) or not rendered_root.is_dir():
        raise VisualFallbackAssetsError("rendered page directory is missing or unsafe")
    rendered_crops: dict[str, bytes] = {}
    for crop_plan in crop_plans:
        source_path = rendered_root / f"page-{crop_plan.page:04d}.png"
        try:
            rendered_crops[crop_plan.filename] = renderVisualFallbackCrop(
                source_path, crop_plan.bbox
            )
        except VisualFallbackCropError as exc:
            raise VisualFallbackAssetsError(
                f"cannot create fallback crop for page {crop_plan.page}"
            ) from exc
    return rendered_crops


def _materializeFallbackAssets(fallback_root: Path, expected_files: dict[str, bytes]) -> None:
    if fallback_root.exists() or isPathReparsePoint(fallback_root):
        _validateExistingFallbackAssets(fallback_root, expected_files)
        return
    try:
        fallback_root.mkdir()
    except FileExistsError:
        _validateExistingFallbackAssets(fallback_root, expected_files)
        return
    for filename, content in expected_files.items():
        _writeNewBytes(fallback_root / filename, content)


def _validateExistingFallbackAssets(fallback_root: Path, expected_files: dict[str, bytes]) -> None:
    if isPathReparsePoint(fallback_root) or not fallback_root.is_dir():
        raise VisualFallbackAssetsError("fallback-assets path is not a regular directory")
    actual_files: set[str] = set()
    with os.scandir(fallback_root) as entries:
        for entry in entries:
            path = Path(entry.path)
            if isPathReparsePoint(path):
                raise VisualFallbackAssetsError(
                    "fallback-assets contains a symbolic link or reparse point"
                )
            mode = entry.stat(follow_symlinks=False).st_mode
            if not stat.S_ISREG(mode):
                raise VisualFallbackAssetsError(
                    "fallback-assets contains an unexpected directory or path"
                )
            actual_files.add(entry.name)
    unexpected_files = actual_files - set(expected_files)
    if unexpected_files:
        unexpected_paths = tuple(sorted(f"fallback-assets/{name}" for name in unexpected_files))
        raise VisualFallbackAssetsError(
            "fallback-assets contains unexpected residual files from a previous "
            f"conversion attempt: {_formatResidualFileList(unexpected_paths)}. "
            "Fix: delete the listed residual files inside the run's fallback-assets/ "
            "directory, then retry visual warning adoption."
        )
    conflicting_files: list[str] = []
    for filename, expected_bytes in expected_files.items():
        asset_path = fallback_root / filename
        if not asset_path.exists():
            _writeNewBytes(asset_path, expected_bytes)
            continue
        if asset_path.read_bytes() != expected_bytes:
            conflicting_files.append(f"fallback-assets/{filename}")
    if conflicting_files:
        raise VisualFallbackAssetsError(
            "existing run-local fallback asset conflicts with the current crop: "
            f"{_formatResidualFileList(tuple(conflicting_files))} differ from the freshly "
            "rendered bytes. Fix: delete the listed stale files inside the run's "
            "fallback-assets/ directory, then retry visual warning adoption."
        )


def _noCropResidualFallbackMessage(fallback_root: Path) -> str:
    base_message = "fallback-assets exists although no crop requests are present"
    residual_names = _residualFallbackAssetNames(fallback_root)
    if not residual_names:
        return base_message
    residual_paths = tuple(f"fallback-assets/{name}" for name in residual_names)
    return (
        f"{base_message}: {_formatResidualFileList(residual_paths)} are leftover files from a "
        "previous conversion attempt. Fix: delete the listed residual files inside the run's "
        "fallback-assets/ directory, then retry visual warning adoption."
    )


def _residualFallbackAssetNames(fallback_root: Path) -> tuple[str, ...]:
    """Best-effort names inside an unexpected fallback-assets directory; empty when unsafe."""
    if isPathReparsePoint(fallback_root) or not fallback_root.is_dir():
        return ()
    try:
        with os.scandir(fallback_root) as entries:
            names = [entry.name for entry in entries]
    except OSError:
        return ()
    return tuple(sorted(names))


def _formatResidualFileList(residual_paths: Sequence[str]) -> str:
    preview = ", ".join(residual_paths[:10])
    if len(residual_paths) > 10:
        return f"{preview} (first 10 of {len(residual_paths)})"
    return preview


def _mergeInjectedPages(
    page_markdown: dict[int, str], assets: Sequence[VisualFallbackAsset]
) -> str:
    assets_by_page: dict[int, list[VisualFallbackAsset]] = {}
    for asset in assets:
        assets_by_page.setdefault(asset.page, []).append(asset)
    merged = ""
    for page_number in sorted(page_markdown):
        markdown = page_markdown[page_number]
        page_assets = assets_by_page.get(page_number, [])
        if page_assets:
            if markdown and not markdown.endswith("\n"):
                markdown += "\n"
            if markdown and not markdown.endswith("\n\n"):
                markdown += "\n"
            markdown += "\n".join(
                "![Visual fidelity crop of original "
                f"{asset.kind}; not machine-readable]({asset.canonical_relative_path})"
                for asset in page_assets
            )
            markdown += "\n"
        if not merged:
            merged = markdown
        elif merged.endswith("\n") or markdown.startswith("\n"):
            merged += markdown
        else:
            merged += "\n" + markdown
    return merged


def _writeNewBytes(path: Path, content: bytes) -> None:
    with path.open("xb") as output_file:
        output_file.write(content)
