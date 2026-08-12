"""本地视觉保真裁剪适配器的公开行为测试。"""

from pathlib import Path

import pymupdf
import pytest

from paperbase.adapters.visual_fallback_crop import (
    VisualFallbackCropError,
    renderVisualFallbackCrop,
)


def _write_png(path: Path, width: int = 100, height: int = 80) -> None:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
    try:
        pixmap.clear_with(0x336699)
        pixmap.save(path)
    finally:
        pixmap = None


def test_render_crop_maps_normalized_bbox_to_source_pixels(tmp_path):
    """归一化 [0.1, 0.25, 0.6, 0.75] 应保留源图对应的 50×40 区域。"""
    source_path = tmp_path / "page-0001.png"
    _write_png(source_path)

    crop_bytes = renderVisualFallbackCrop(source_path, (0.1, 0.25, 0.6, 0.75))

    crop = pymupdf.Pixmap(crop_bytes)
    assert crop.width == 50
    assert crop.height == 40


def test_render_crop_rejects_empty_invalid_or_out_of_bounds_png_input(tmp_path):
    """裁剪器不能把空/坏 PNG 或越界 bbox 当作可保真资产。"""
    empty_png = tmp_path / "empty.png"
    empty_png.write_bytes(b"")
    invalid_png = tmp_path / "invalid.png"
    invalid_png.write_bytes(b"not a PNG")
    valid_png = tmp_path / "valid.png"
    _write_png(valid_png)

    with pytest.raises(VisualFallbackCropError):
        renderVisualFallbackCrop(empty_png, (0.0, 0.0, 1.0, 1.0))
    with pytest.raises(VisualFallbackCropError):
        renderVisualFallbackCrop(invalid_png, (0.0, 0.0, 1.0, 1.0))
    with pytest.raises(VisualFallbackCropError):
        renderVisualFallbackCrop(valid_png, (0.0, 0.0, 1.1, 1.0))
