"""Local raster crops for visual-fidelity fallback assets."""

from __future__ import annotations

# ruff: noqa: N802
import math
import os
import stat
from pathlib import Path
from typing import Sequence

import pymupdf

from paperbase.core.visual_repair_run import isPathReparsePoint


class VisualFallbackCropError(ValueError):
    """A rendered page or normalized crop rectangle is unsafe or unusable."""


def renderVisualFallbackCrop(source_path: Path, bbox: Sequence[float]) -> bytes:
    """Render one normalized crop from a local PNG without writing any files."""
    source = Path(source_path)
    _requireSafePng(source)
    left, top, right, bottom = _validateNormalizedBbox(bbox)
    try:
        document = pymupdf.open(source)
    except Exception as exc:
        raise VisualFallbackCropError("rendered page is not a valid PNG") from exc
    try:
        if len(document) != 1:
            raise VisualFallbackCropError("rendered PNG must contain exactly one page")
        page = document[0]
        page_rect = page.rect
        if page_rect.width <= 0 or page_rect.height <= 0:
            raise VisualFallbackCropError("rendered PNG has no drawable area")
        source_pixmap = pymupdf.Pixmap(source)
        if source_pixmap.width <= 0 or source_pixmap.height <= 0:
            raise VisualFallbackCropError("rendered PNG has no pixels")
        clip = pymupdf.Rect(
            page_rect.x0 + page_rect.width * left,
            page_rect.y0 + page_rect.height * top,
            page_rect.x0 + page_rect.width * right,
            page_rect.y0 + page_rect.height * bottom,
        )
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(
                source_pixmap.width / page_rect.width,
                source_pixmap.height / page_rect.height,
            ),
            clip=clip,
            alpha=False,
        )
        if pixmap.width <= 0 or pixmap.height <= 0:
            raise VisualFallbackCropError("normalized crop does not contain any pixels")
        crop_bytes = pixmap.tobytes("png")
    except VisualFallbackCropError:
        raise
    except Exception as exc:
        raise VisualFallbackCropError("cannot crop rendered PNG") from exc
    finally:
        document.close()
    if not crop_bytes:
        raise VisualFallbackCropError("rendered crop is empty")
    return crop_bytes


def _requireSafePng(path: Path) -> None:
    if path.suffix.lower() != ".png":
        raise VisualFallbackCropError("rendered page must use the .png extension")
    if isPathReparsePoint(path) or isPathReparsePoint(path.parent):
        raise VisualFallbackCropError("rendered page must not use a symbolic link or reparse point")
    try:
        path_stat = os.stat(path, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise VisualFallbackCropError("rendered page does not exist") from exc
    if not stat.S_ISREG(path_stat.st_mode) or path_stat.st_size <= 0:
        raise VisualFallbackCropError("rendered page must be a non-empty regular PNG")


def _validateNormalizedBbox(bbox: Sequence[float]) -> tuple[float, float, float, float]:
    if not isinstance(bbox, Sequence) or isinstance(bbox, (str, bytes)) or len(bbox) != 4:
        raise VisualFallbackCropError("crop bbox must contain four normalized coordinates")
    coordinates: list[float] = []
    for coordinate in bbox:
        if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
            raise VisualFallbackCropError("crop bbox coordinates must be numbers")
        normalized = float(coordinate)
        if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
            raise VisualFallbackCropError("crop bbox must stay within normalized page bounds")
        coordinates.append(normalized)
    left, top, right, bottom = coordinates
    if left >= right or top >= bottom:
        raise VisualFallbackCropError("crop bbox must have positive area")
    return left, top, right, bottom
