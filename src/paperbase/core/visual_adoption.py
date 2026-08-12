"""Explicit-confirmation adoption of validated visual fallback assets."""

from __future__ import annotations

# ruff: noqa: N802
import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from paperbase.core.visual_boundary_review import (
    BoundaryReviewError,
    ValidatedBoundaryReview,
    prepareOrValidateBoundaryReview,
)
from paperbase.core.visual_fallback_assets import (
    VisualFallbackAssetsError,
    prepareVisualFallbackAssets,
)
from paperbase.core.visual_repair_run import (
    LeaseConflictError,
    RunLease,
    cleanupVisualRun,
    isPathReparsePoint,
    loadVisualRun,
)


class VisualAdoptionError(ValueError):
    """Explicit visual-warning adoption cannot safely proceed."""


@dataclass(frozen=True)
class VisualAdoption:
    """Confirmed marker-free Markdown and paths projected for Canonical adoption."""

    markdown: str
    assets: tuple[str, ...]
    warnings: tuple[str, ...]


def adoptConfirmedVisualWarnings(run_dir: Path) -> VisualAdoption:
    """Project a ready, warning-bearing visual run's assets into its paper directory."""
    normalized_run_dir = _validateReadyRun(run_dir)
    boundary = _validateBoundaryPass(normalized_run_dir)
    try:
        fallback = prepareVisualFallbackAssets(normalized_run_dir)
    except VisualFallbackAssetsError as exc:
        raise VisualAdoptionError("visual fallback plan is invalid") from exc
    warnings = tuple(dict.fromkeys((*boundary.result.warnings, *fallback.warnings)))
    if not warnings:
        raise VisualAdoptionError("explicit adoption requires existing visual warnings")
    if "paperbase:visual-page" in fallback.markdown:
        raise VisualAdoptionError("fallback Markdown still contains temporary page markers")

    paper_dir = normalized_run_dir.parent.parent
    _copyFallbackAssets(paper_dir, normalized_run_dir, fallback.assets)
    return VisualAdoption(
        markdown=fallback.markdown,
        assets=tuple(asset.canonical_relative_path for asset in fallback.assets),
        warnings=warnings,
    )


def cleanupReadyVisualRuns(paper_dir: Path) -> tuple[str, ...]:
    """Delete only safe, lease-free ``ready_to_adopt`` runs after full success."""
    root = Path(paper_dir) / ".visual-runs"
    if not root.exists() and not isPathReparsePoint(root):
        return ()
    if isPathReparsePoint(root) or not root.is_dir():
        raise VisualAdoptionError("visual runs root is unsafe")

    cleanup_candidates: list[tuple[str, Path]] = []
    for entry in sorted(os.scandir(root), key=lambda item: item.name):
        run_dir = Path(entry.path)
        if isPathReparsePoint(run_dir):
            raise VisualAdoptionError("visual runs root contains a symbolic link or reparse point")
        if not entry.is_dir(follow_symlinks=False):
            continue
        try:
            run = loadVisualRun(run_dir)
        except (FileNotFoundError, ValueError, KeyError):
            continue
        if run.state != "ready_to_adopt" or _hasActiveLease(run_dir):
            continue
        _assertTreeHasNoReparsePoints(run_dir)
        cleanup_candidates.append((run.run_id, run_dir))

    cleaned_run_ids: list[str] = []
    for run_id, _ in cleanup_candidates:
        try:
            cleanupVisualRun(paper_dir, run_id)
        except LeaseConflictError:
            continue
        cleaned_run_ids.append(run_id)
    return tuple(cleaned_run_ids)


def _validateReadyRun(run_dir: Path) -> Path:
    try:
        run = loadVisualRun(run_dir)
    except Exception as exc:
        raise VisualAdoptionError("visual run is missing or unsafe") from exc
    if run.state != "ready_to_adopt":
        raise VisualAdoptionError("visual run is not ready_to_adopt")
    return Path(run_dir).resolve()


def _hasActiveLease(run_dir: Path) -> bool:
    lease_path = run_dir / "lease.json"
    if not lease_path.exists() and not isPathReparsePoint(lease_path):
        return False
    _requireRegularFile(lease_path, "run lease")
    try:
        data = json.loads(lease_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualAdoptionError("run lease is invalid") from exc
    if not isinstance(data, dict):
        raise VisualAdoptionError("run lease is invalid")
    try:
        lease = RunLease.fromDict(data)
        return not lease.isExpired(datetime.now(UTC))
    except ValueError as exc:
        raise VisualAdoptionError("run lease is invalid") from exc


def _validateBoundaryPass(run_dir: Path) -> ValidatedBoundaryReview:
    try:
        boundary = prepareOrValidateBoundaryReview(run_dir)
    except BoundaryReviewError as exc:
        raise VisualAdoptionError("Boundary Review is invalid") from exc
    if not isinstance(boundary, ValidatedBoundaryReview) or boundary.result.decision != "pass":
        raise VisualAdoptionError("Boundary Review must pass before visual adoption")
    return boundary


def _copyFallbackAssets(paper_dir: Path, run_dir: Path, assets: tuple[object, ...]) -> None:
    if not assets:
        return
    assets_root = paper_dir / "assets"
    _ensureAssetsRoot(assets_root)
    fallback_root = run_dir / "fallback-assets"
    if isPathReparsePoint(fallback_root) or not fallback_root.is_dir():
        raise VisualAdoptionError("run-local fallback-assets directory is missing or unsafe")
    for asset in assets:
        source_path = getattr(asset, "source_path", None)
        canonical_relative_path = getattr(asset, "canonical_relative_path", None)
        if not isinstance(source_path, Path) or not isinstance(canonical_relative_path, str):
            raise VisualAdoptionError("visual fallback asset plan is invalid")
        filename = _validateCanonicalAssetPath(canonical_relative_path)
        if source_path != fallback_root / filename:
            raise VisualAdoptionError(
                "visual fallback asset source does not match its run-local plan"
            )
        _copyOneAsset(source_path, assets_root / filename)


def _ensureAssetsRoot(assets_root: Path) -> None:
    if assets_root.exists() or isPathReparsePoint(assets_root):
        if isPathReparsePoint(assets_root) or not assets_root.is_dir():
            raise VisualAdoptionError("paper assets directory is unsafe")
        return
    try:
        assets_root.mkdir()
    except FileExistsError:
        _ensureAssetsRoot(assets_root)


def _copyOneAsset(source_path: Path, destination_path: Path) -> None:
    _requireRegularFile(source_path, "run-local fallback asset")
    if destination_path.exists() or isPathReparsePoint(destination_path):
        _requireRegularFile(destination_path, "paper asset target")
        if not _filesEqual(source_path, destination_path):
            raise VisualAdoptionError(
                "paper asset target conflicts with the run-local fallback asset"
            )
        return

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="xb",
            dir=destination_path.parent,
            prefix=f".{destination_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output_file:
            temporary_path = Path(output_file.name)
            with source_path.open("rb") as source_file:
                shutil.copyfileobj(source_file, output_file)
            output_file.flush()
            os.fsync(output_file.fileno())
        try:
            os.link(temporary_path, destination_path)
        except FileExistsError:
            _requireRegularFile(destination_path, "paper asset target")
            if not _filesEqual(source_path, destination_path):
                raise VisualAdoptionError(
                    "paper asset target conflicts with the run-local fallback asset"
                )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _requireRegularFile(path: Path, label: str) -> None:
    if isPathReparsePoint(path):
        raise VisualAdoptionError(f"{label} must not be a symbolic link or reparse point")
    try:
        mode = os.stat(path, follow_symlinks=False).st_mode
    except FileNotFoundError as exc:
        raise VisualAdoptionError(f"{label} must be an existing regular file") from exc
    if not stat.S_ISREG(mode):
        raise VisualAdoptionError(f"{label} must be an existing regular file")


def _filesEqual(first_path: Path, second_path: Path) -> bool:
    if first_path.stat().st_size != second_path.stat().st_size:
        return False
    with first_path.open("rb") as first_file, second_path.open("rb") as second_file:
        while True:
            first_block = first_file.read(1024 * 1024)
            second_block = second_file.read(1024 * 1024)
            if first_block != second_block:
                return False
            if not first_block:
                return True


def _validateCanonicalAssetPath(value: str) -> str:
    prefix = "./assets/"
    filename = value.removeprefix(prefix)
    if (
        not value.startswith(prefix)
        or not filename
        or "/" in filename
        or "\\" in filename
        or filename in {".", ".."}
    ):
        raise VisualAdoptionError("visual fallback asset must use a direct ./assets relative path")
    return filename


def _assertTreeHasNoReparsePoints(root: Path) -> None:
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                if isPathReparsePoint(path):
                    raise VisualAdoptionError(
                        "ready visual run contains a symbolic link or reparse point"
                    )
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    pending.append(path)
                elif not stat.S_ISREG(mode):
                    raise VisualAdoptionError("ready visual run contains an unsafe path")
