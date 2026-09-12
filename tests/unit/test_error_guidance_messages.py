"""采纳资产冲突与 references_unparseable 错误信息的指路能力测试。"""

import pytest

from paperbase.core.canonical_adoption_gate import (
    CanonicalAdoptionGateError,
    validateCanonicalAdoption,
)
from paperbase.core.reference_extractor import count_unnumbered_reference_lines
from paperbase.core.visual_adoption import (
    VisualAdoptionError,
    adoptConfirmedVisualWarnings,
)
from paperbase.core.visual_fallback_assets import (
    VisualFallbackAssetsError,
    prepareVisualFallbackAssets,
)
from tests.unit.test_canonical_adoption_gate import PAPER_ID, STORAGE_ID, _canonical
from tests.unit.test_visual_adoption import _mark_ready_with_boundary_pass
from tests.unit.test_visual_fallback_assets import _write_completed_run, _write_png

# ---------------------------------------------------------------------------
# 缺陷 1a：论文 assets/ 采纳目标侧的残留冲突必须列出具体相对路径
# ---------------------------------------------------------------------------


def test_asset_target_conflict_error_lists_each_conflicting_path(tmp_path):
    """采纳目标残留旧裁剪时，错误信息必须列出冲突的 ./assets/ 相对路径与修复动作。"""
    run_dir = _write_completed_run(
        tmp_path / "paper",
        {
            "chunk-001": [{"page": 1, "bbox": [0.0, 0.0, 0.5, 0.5], "kind": "formula"}],
            "chunk-002": [{"page": 2, "bbox": [0.0, 0.0, 0.5, 0.5], "kind": "table"}],
        },
    )
    _mark_ready_with_boundary_pass(run_dir)
    assets_root = run_dir.parent.parent / "assets"
    assets_root.mkdir()
    (assets_root / "visual-page-0001-formula-01.png").write_bytes(b"stale bytes one")
    (assets_root / "visual-page-0002-table-01.png").write_bytes(b"stale bytes two")

    with pytest.raises(VisualAdoptionError) as exc_info:
        adoptConfirmedVisualWarnings(run_dir)

    message = str(exc_info.value)
    assert "./assets/visual-page-0001-formula-01.png" in message
    assert "./assets/visual-page-0002-table-01.png" in message
    assert "conflicts" in message
    assert "delete" in message.lower()


def test_asset_target_conflict_error_caps_listing_at_ten_with_total(tmp_path):
    """冲突文件超过 10 个时只列前 10 个并附总数。"""
    crop_requests = {
        "chunk-001": [
            {"page": 1, "bbox": [0.0, 0.0, 0.01 * index, 0.5], "kind": "formula"}
            for index in range(1, 12)
        ]
    }
    run_dir = _write_completed_run(tmp_path / "paper", crop_requests)
    _mark_ready_with_boundary_pass(run_dir)
    assets_root = run_dir.parent.parent / "assets"
    assets_root.mkdir()
    for index in range(1, 12):
        (assets_root / f"visual-page-0001-formula-{index:02d}.png").write_bytes(b"stale")

    with pytest.raises(VisualAdoptionError) as exc_info:
        adoptConfirmedVisualWarnings(run_dir)

    message = str(exc_info.value)
    assert "first 10 of 11" in message
    assert message.count("./assets/visual-page-") == 10
    assert "./assets/visual-page-0001-formula-11.png" not in message


def test_idempotent_same_bytes_targets_are_not_reported_as_conflicts(tmp_path):
    """同名同字节目标属于幂等复用，不得出现在冲突清单里。"""
    crop_request = {"chunk-001": [{"page": 1, "bbox": [0.0, 0.0, 0.5, 0.5], "kind": "formula"}]}
    run_dir = _write_completed_run(tmp_path / "paper", crop_request)
    _mark_ready_with_boundary_pass(run_dir)

    first = adoptConfirmedVisualWarnings(run_dir)
    second = adoptConfirmedVisualWarnings(run_dir)

    assert second == first


# ---------------------------------------------------------------------------
# 缺陷 1b：run 局部 fallback-assets/ 侧的残留冲突必须列出具体文件
# ---------------------------------------------------------------------------


def test_run_local_unexpected_residual_files_are_listed(tmp_path):
    """fallback-assets 内残留无关文件时，错误信息必须列出具体文件路径与修复动作。"""
    crop_request = {"chunk-001": [{"page": 1, "bbox": [0.0, 0.0, 0.5, 0.5], "kind": "formula"}]}
    run_dir = _write_completed_run(tmp_path, crop_request)
    prepareVisualFallbackAssets(run_dir)
    (run_dir / "fallback-assets" / "stale-leftover.txt").write_text("stale", encoding="utf-8")

    with pytest.raises(VisualFallbackAssetsError) as exc_info:
        prepareVisualFallbackAssets(run_dir)

    message = str(exc_info.value)
    assert "fallback-assets/stale-leftover.txt" in message
    assert "delete" in message.lower()


def test_run_local_changed_crop_conflict_lists_file(tmp_path):
    """已存在的 run 局部裁剪与当前渲染字节冲突时，错误信息必须列出该文件。"""
    run_dir = _write_completed_run(
        tmp_path, {"chunk-001": [{"page": 1, "bbox": [0.0, 0.0, 0.5, 0.5], "kind": "formula"}]}
    )
    prepareVisualFallbackAssets(run_dir)
    _write_png(run_dir / "rendered" / "page-0001.png", 0x993333)

    with pytest.raises(VisualFallbackAssetsError) as exc_info:
        prepareVisualFallbackAssets(run_dir)

    message = str(exc_info.value)
    assert "fallback-assets/visual-page-0001-formula-01.png" in message
    assert "conflicts" in message


def test_no_crop_residual_fallback_assets_lists_leftover_files(tmp_path):
    """无 crop 请求却存在残留 fallback-assets 时，错误信息必须列出残留文件。"""
    run_dir = _write_completed_run(tmp_path)
    residual_root = run_dir / "fallback-assets"
    residual_root.mkdir()
    (residual_root / "visual-page-0009-table-01.png").write_bytes(b"stale")

    with pytest.raises(VisualFallbackAssetsError) as exc_info:
        prepareVisualFallbackAssets(run_dir)

    message = str(exc_info.value)
    assert "no crop requests are present" in message
    assert "fallback-assets/visual-page-0009-table-01.png" in message


def test_run_local_residual_detail_survives_adoption_error_wrap(tmp_path):
    """run 局部冲突细节在 VisualAdoptionError 包装后仍保留，供上游展示。"""
    run_dir = _write_completed_run(
        tmp_path / "paper",
        {"chunk-001": [{"page": 1, "bbox": [0.0, 0.0, 0.5, 0.5], "kind": "formula"}]},
    )
    prepareVisualFallbackAssets(run_dir)
    (run_dir / "fallback-assets" / "stale-leftover.txt").write_text("stale", encoding="utf-8")
    _mark_ready_with_boundary_pass(run_dir)

    with pytest.raises(VisualAdoptionError) as exc_info:
        adoptConfirmedVisualWarnings(run_dir)

    message = str(exc_info.value)
    assert "visual fallback plan is invalid" in message
    assert "fallback-assets/stale-leftover.txt" in message


# ---------------------------------------------------------------------------
# 缺陷 2：references_unparseable 必须指路（仅支持 [n] 编号 + 修复动作）
# ---------------------------------------------------------------------------


def test_references_unparseable_message_points_to_numbered_format():
    """无编号（作者-年份式）文献被拒时，错误信息必须说明仅支持 [n] 编号并给出修复动作。"""
    body = (
        "body " * 120
        + "\n\n## References\n\n"
        + "Adler, M. J. (2020). How to read papers. Journal of Reading, 12(3), 1-10.\n"
        + "Baker, C. D. (2021). Another study on papers. Journal of Studies, 5(2), 20-30.\n"
    )

    with pytest.raises(CanonicalAdoptionGateError) as exc_info:
        validateCanonicalAdoption(
            _canonical(body),
            expected_paper_id=PAPER_ID,
            expected_storage_id=STORAGE_ID,
            minimum_body_chars=500,
        )

    assert exc_info.value.reason == "references_unparseable"
    message = str(exc_info.value)
    assert "[1]..[n]" in message
    assert "renumber" in message
    assert "detected 2" in message


def test_references_unparseable_message_without_unnumbered_lines_still_guides():
    """检测不到无编号行时仍给出编号格式说明与修复动作。"""
    body = "body " * 120 + "\n\n## References\n\n[1]\n"

    with pytest.raises(CanonicalAdoptionGateError) as exc_info:
        validateCanonicalAdoption(
            _canonical(body),
            expected_paper_id=PAPER_ID,
            expected_storage_id=STORAGE_ID,
            minimum_body_chars=500,
        )

    message = str(exc_info.value)
    assert "no [n]-numbered entry lines were detected" in message
    assert "[1]..[n]" in message
    assert "renumber" in message


def test_count_unnumbered_reference_lines_counts_unnumbered_lines():
    """诊断函数统计 References 段落内未以 [n] 编号开头的非空行。"""
    markdown = (
        "## References\n\n"
        "Adler, M. (2020). A study. Journal, 1, 1-10.\n"
        "\n"
        "Baker, C. (2021). Another. Journal, 2, 2-12.\n"
    )

    assert count_unnumbered_reference_lines(markdown) == 2


def test_count_unnumbered_reference_lines_returns_zero_or_none_otherwise():
    """编号段落返回 0；无 References 段落返回 None。"""
    assert count_unnumbered_reference_lines("## References\n\n[1] A. (2020). X.\n") == 0
    assert count_unnumbered_reference_lines("## Conclusion\n\nNo references here.\n") is None
