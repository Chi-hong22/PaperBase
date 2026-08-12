"""运行内视觉保真资产计划与 Markdown 注入的公开行为测试。"""

import hashlib
import json
import subprocess
from pathlib import Path

import pymupdf
import pytest

from paperbase.core.visual_fallback_assets import (
    VisualFallbackAssetsError,
    prepareVisualFallbackAssets,
)
from paperbase.core.visual_task_package import VisualChunkPlan, prepareVisualTaskPackage


def _write_png(path: Path, color: int) -> Path:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 80), False)
    try:
        pixmap.clear_with(color)
        pixmap.save(path)
    finally:
        pixmap = None
    return path


def _write_completed_run(
    tmp_path: Path, crop_requests: dict[str, list[dict[str, object]]] | None = None
) -> Path:
    crop_requests = crop_requests or {}
    run_dir = tmp_path / ".visual-runs" / "run-one"
    plans = (
        VisualChunkPlan("chunk-001", (1,), (2,)),
        VisualChunkPlan("chunk-002", (2,), (1,)),
    )
    run_dir.mkdir(parents=True)
    candidate_path = run_dir / "candidate.md"
    candidate_path.write_text("candidate body\n", encoding="utf-8")
    candidate_sha256 = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "compatibility": {
                    "candidate_sha256": candidate_sha256,
                    "template_version": "visual-v1",
                    "chunking_scheme": {
                        "version": "contiguous-core-adjacent-context-v1",
                        "page_count": 2,
                        "chunk_pages": 1,
                        "chunks": [
                            {
                                "chunk_id": plan.chunk_id,
                                "core_pages": list(plan.core_pages),
                                "context_pages": list(plan.context_pages),
                            }
                            for plan in plans
                        ],
                    },
                },
                "state": "prepared",
                "chunks": {
                    plan.chunk_id: {"state": "completed", "lease_token": None} for plan in plans
                },
                "created_at": "2026-08-11T00:00:00+00:00",
                "updated_at": "2026-08-11T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    rendered_dir = run_dir / "rendered"
    rendered_dir.mkdir()
    rendered_pages = {
        1: _write_png(rendered_dir / "page-0001.png", 0x336699),
        2: _write_png(rendered_dir / "page-0002.png", 0x663399),
    }
    packages = prepareVisualTaskPackage(
        run_dir,
        2,
        plans,
        {plan.chunk_id: plan.chunk_id for plan in plans},
        rendered_pages,
        requested_model="host-model",
    )
    for chunk_id, task_dir in packages.items():
        task = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
        run = task["run"]
        chunk = task["chunk"]
        assert isinstance(run, dict)
        assert isinstance(chunk, dict)
        core_pages = chunk["core_pages"]
        assert isinstance(core_pages, list)
        requested_crops = crop_requests.get(chunk_id, [])
        result = {
            "schema_version": "visual-chunk-result-v1",
            "run_id": run["run_id"],
            "candidate_sha256": run["candidate_sha256"],
            "chunk_id": chunk["chunk_id"],
            "core_pages": core_pages,
            "status": "completed",
            "covered_pages": core_pages,
            "warnings": ["A fidelity crop needs user confirmation."] if requested_crops else [],
            "unresolved_issues": [],
            "failure_code": None,
            "crop_requests": requested_crops,
        }
        marked_markdown = "".join(
            f"<!-- paperbase:visual-page-start page={page_number} -->\n"
            f"Page {page_number} content.\n"
            f"<!-- paperbase:visual-page-end page={page_number} -->\n"
            for page_number in core_pages
        )
        (task_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
        (task_dir / "result.md").write_text(marked_markdown, encoding="utf-8")
    return run_dir


def test_no_crop_keeps_normal_merge_and_creates_no_fallback_directory(tmp_path):
    """没有 crop request 时，不应产生资产或改变正常无标记合并。"""
    run_dir = _write_completed_run(tmp_path)

    output = prepareVisualFallbackAssets(run_dir)

    assert output.markdown == "Page 1 content.\nPage 2 content.\n"
    assert output.assets == ()
    assert output.warnings == ()
    assert not (run_dir / "fallback-assets").exists()


def test_multiple_page_crops_are_run_local_and_injected_at_each_page_end(tmp_path):
    """多页多 crop 依请求顺序命名、留在 run 内，并在所属页末尾注入保真说明。"""
    run_dir = _write_completed_run(
        tmp_path,
        {
            "chunk-001": [
                {"page": 1, "bbox": [0.0, 0.0, 0.5, 0.5], "kind": "formula"},
                {"page": 1, "bbox": [0.5, 0.0, 1.0, 0.5], "kind": "table"},
            ],
            "chunk-002": [{"page": 2, "bbox": [0.0, 0.5, 1.0, 1.0], "kind": "image"}],
        },
    )

    output = prepareVisualFallbackAssets(run_dir)

    assert [asset.source_path.name for asset in output.assets] == [
        "visual-page-0001-formula-01.png",
        "visual-page-0001-table-01.png",
        "visual-page-0002-image-01.png",
    ]
    assert [asset.canonical_relative_path for asset in output.assets] == [
        "./assets/visual-page-0001-formula-01.png",
        "./assets/visual-page-0001-table-01.png",
        "./assets/visual-page-0002-image-01.png",
    ]
    assert all(asset.source_path.parent == run_dir / "fallback-assets" for asset in output.assets)
    assert all(asset.source_path.is_file() for asset in output.assets)
    assert len(output.warnings) == 5
    assert output.warnings.count("A fidelity crop needs user confirmation.") == 2
    assert sum("requires user confirmation" in warning for warning in output.warnings) == 3
    assert (
        output.markdown.index("Page 1 content.")
        < output.markdown.index("visual-page-0001-formula-01.png")
        < output.markdown.index("visual-page-0001-table-01.png")
        < output.markdown.index("Page 2 content.")
        < output.markdown.index("visual-page-0002-image-01.png")
    )
    assert "Visual fidelity crop" in output.markdown
    assert "not machine-readable" in output.markdown
    assert "paperbase:visual-page" not in output.markdown


def test_repeated_identical_crop_reuses_bytes_but_changed_source_refuses_conflict(tmp_path):
    """同输入重跑复用原字节；源渲染页变化时不能静默覆盖同名裁剪。"""
    run_dir = _write_completed_run(
        tmp_path,
        {"chunk-001": [{"page": 1, "bbox": [0.0, 0.0, 0.5, 0.5], "kind": "formula"}]},
    )

    first = prepareVisualFallbackAssets(run_dir)
    first_bytes = first.assets[0].source_path.read_bytes()
    second = prepareVisualFallbackAssets(run_dir)

    assert second.assets[0].source_path.read_bytes() == first_bytes
    _write_png(run_dir / "rendered" / "page-0001.png", 0x993333)
    with pytest.raises(VisualFallbackAssetsError, match="conflicts"):
        prepareVisualFallbackAssets(run_dir)


def test_unexpected_fallback_file_or_bad_rendered_png_is_rejected(tmp_path):
    """运行内已有无关文件或无法裁剪的 PNG 都不能静默继续。"""
    crop_request = {"chunk-001": [{"page": 1, "bbox": [0.0, 0.0, 0.5, 0.5], "kind": "formula"}]}
    run_with_extra = _write_completed_run(tmp_path / "extra", crop_request)
    prepareVisualFallbackAssets(run_with_extra)
    (run_with_extra / "fallback-assets" / "unexpected.txt").write_text("no", encoding="utf-8")
    with pytest.raises(VisualFallbackAssetsError, match="unexpected"):
        prepareVisualFallbackAssets(run_with_extra)

    run_with_bad_png = _write_completed_run(tmp_path / "bad-png", crop_request)
    (run_with_bad_png / "rendered" / "page-0001.png").write_bytes(b"not a PNG")
    with pytest.raises(VisualFallbackAssetsError, match="cannot create"):
        prepareVisualFallbackAssets(run_with_bad_png)


def test_reparse_fallback_directory_is_rejected_when_windows_allows_junction(tmp_path):
    """fallback-assets junction 不能把写入重定向到 run 外。"""
    run_dir = _write_completed_run(
        tmp_path,
        {"chunk-001": [{"page": 1, "bbox": [0.0, 0.0, 0.5, 0.5], "kind": "formula"}]},
    )
    target = tmp_path / "outside"
    target.mkdir()
    junction = run_dir / "fallback-assets"
    creation = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if creation.returncode != 0:
        pytest.skip("当前 Windows 环境不允许创建 junction")

    with pytest.raises(VisualFallbackAssetsError):
        prepareVisualFallbackAssets(run_dir)
