"""视觉分块 worker 结果的公开协议与合并行为测试。"""

import hashlib
import json
from pathlib import Path

import pytest

from paperbase.core.visual_chunk_result import (
    CropRequest,
    VisualChunkResultError,
    mergeVisualChunkResults,
    validateVisualChunkResult,
)
from paperbase.core.visual_task_package import VisualChunkPlan, prepareVisualTaskPackage


def _write_run(
    run_dir: Path,
    page_count: int = 3,
    chunk_plans: tuple[VisualChunkPlan, ...] | None = None,
) -> dict[int, Path]:
    if chunk_plans is None:
        chunk_plans = (
            VisualChunkPlan("chunk-001", (1, 2), (3,)),
            VisualChunkPlan("chunk-002", (3,), (2,)),
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
                        "page_count": page_count,
                        "chunk_pages": 2,
                        "chunks": [
                            {
                                "chunk_id": plan.chunk_id,
                                "core_pages": list(plan.core_pages),
                                "context_pages": list(plan.context_pages),
                            }
                            for plan in chunk_plans
                        ],
                    },
                },
                "state": "prepared",
                "chunks": {
                    plan.chunk_id: {"state": "pending", "lease_token": None} for plan in chunk_plans
                },
                "created_at": "2026-08-11T00:00:00+00:00",
                "updated_at": "2026-08-11T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    rendered_dir = run_dir / "rendered"
    rendered_dir.mkdir()
    rendered_pages: dict[int, Path] = {}
    for page_number in range(1, page_count + 1):
        page_path = rendered_dir / f"page-{page_number:04d}.png"
        page_path.write_bytes(f"rendered-page-{page_number}".encode("ascii"))
        rendered_pages[page_number] = page_path
    return rendered_pages


def _prepare_run(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    run_dir = tmp_path / ".visual-runs" / "run-one"
    chunk_plans = (
        VisualChunkPlan("chunk-001", (1, 2), (3,)),
        VisualChunkPlan("chunk-002", (3,), (2,)),
    )
    rendered_pages = _write_run(run_dir, chunk_plans=chunk_plans)
    packages = prepareVisualTaskPackage(
        run_dir,
        3,
        chunk_plans,
        {"chunk-001": "first fragment", "chunk-002": "second fragment"},
        rendered_pages,
        requested_model="host-model",
    )
    return run_dir, packages


def _task(task_dir: Path) -> dict[str, object]:
    return json.loads((task_dir / "task.json").read_text(encoding="utf-8"))


def _result_payload(
    task_dir: Path,
    *,
    status: str = "completed",
    covered_pages: list[int] | None = None,
    **changes: object,
) -> dict[str, object]:
    task_data = _task(task_dir)
    run = task_data["run"]
    chunk = task_data["chunk"]
    assert isinstance(run, dict)
    assert isinstance(chunk, dict)
    core_pages = chunk["core_pages"]
    assert isinstance(core_pages, list)
    if covered_pages is None:
        covered_pages = list(core_pages) if status == "completed" else []
    result = {
        "schema_version": "visual-chunk-result-v1",
        "run_id": run["run_id"],
        "candidate_sha256": run["candidate_sha256"],
        "chunk_id": chunk["chunk_id"],
        "core_pages": core_pages,
        "status": status,
        "covered_pages": covered_pages,
        "warnings": [],
        "unresolved_issues": [],
        "failure_code": None,
        "crop_requests": [],
    }
    result.update(changes)
    return result


def _marked_pages(page_numbers: list[int]) -> str:
    return "".join(
        f"<!-- paperbase:visual-page-start page={page_number} -->\n"
        f"Page {page_number} content.\n"
        f"<!-- paperbase:visual-page-end page={page_number} -->\n"
        for page_number in page_numbers
    )


def _write_worker_result(
    task_dir: Path,
    *,
    status: str = "completed",
    covered_pages: list[int] | None = None,
    marked_pages: list[int] | None = None,
    **changes: object,
) -> None:
    result = _result_payload(
        task_dir,
        status=status,
        covered_pages=covered_pages,
        **changes,
    )
    if marked_pages is None:
        actual_covered = result["covered_pages"]
        assert isinstance(actual_covered, list)
        marked_pages = actual_covered
    (task_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    (task_dir / "result.md").write_text(_marked_pages(marked_pages), encoding="utf-8")


def test_completed_result_requires_task_identity_core_coverage_and_markers(tmp_path):
    """合法 completed 必须精确声明任务身份、核心页覆盖和逐页 Markdown。"""
    _, packages = _prepare_run(tmp_path)
    task_dir = packages["chunk-001"]
    _write_worker_result(
        task_dir,
        warnings=["Formula crop must be reviewed by a human."],
        crop_requests=[{"page": 1, "bbox": [0.1, 0.2, 0.8, 0.9], "kind": "formula"}],
    )

    result = validateVisualChunkResult(task_dir)

    assert result.status == "completed"
    assert result.chunk_id == "chunk-001"
    assert result.core_pages == (1, 2)
    assert result.covered_pages == (1, 2)
    assert result.page_markdown == {1: "Page 1 content.\n", 2: "Page 2 content.\n"}
    assert result.crop_requests == (CropRequest(1, (0.1, 0.2, 0.8, 0.9), "formula"),)


@pytest.mark.parametrize(
    ("covered_pages", "marked_pages"),
    [
        ([1, 2], [1, 3]),
        ([1, 2], [1, 4]),
        ([1, 2], [1, 1, 2]),
        ([1], [1]),
        ([1, 2], [2, 1]),
    ],
    ids=["context_page", "out_of_range_page", "duplicate_page", "missing_page", "wrong_order"],
)
def test_result_markdown_rejects_invalid_core_page_ownership_or_order(
    tmp_path, covered_pages, marked_pages
):
    """结果 Markdown 只能恰好一次、按顺序包裹每个核心页。"""
    _, packages = _prepare_run(tmp_path)
    task_dir = packages["chunk-001"]
    _write_worker_result(
        task_dir,
        covered_pages=covered_pages,
        marked_pages=marked_pages,
    )

    with pytest.raises(VisualChunkResultError):
        validateVisualChunkResult(task_dir)


def test_merge_completed_chunks_uses_core_page_order_and_strips_markers(tmp_path):
    """多块合并按核心页全局顺序输出，不保留运行时页标记。"""
    run_dir, packages = _prepare_run(tmp_path)
    _write_worker_result(packages["chunk-001"])
    _write_worker_result(packages["chunk-002"])

    merged = mergeVisualChunkResults(run_dir)

    assert merged == "Page 1 content.\nPage 2 content.\nPage 3 content.\n"
    assert "paperbase:visual-page" not in merged


def test_single_core_page_without_context_can_reuse_task_package(tmp_path):
    """单页无 context 也必须是可重复准备的合法任务包。"""
    run_dir = tmp_path / ".visual-runs" / "single-page-run"
    chunk_plans = (VisualChunkPlan("chunk-001", (1,), ()),)
    rendered_pages = _write_run(run_dir, page_count=1, chunk_plans=chunk_plans)
    first_packages = prepareVisualTaskPackage(
        run_dir,
        1,
        chunk_plans,
        {"chunk-001": "single page fragment"},
        rendered_pages,
        requested_model="host-model",
    )
    second_packages = prepareVisualTaskPackage(
        run_dir,
        1,
        chunk_plans,
        {"chunk-001": "single page fragment"},
        rendered_pages,
        requested_model="host-model",
    )

    task_data = _task(first_packages["chunk-001"])
    assert second_packages == first_packages
    assert task_data["chunk"]["context_pages"] == []
    assert task_data["inputs"]["context"] == []


@pytest.mark.parametrize(
    "mutation", ["missing_task", "extra_task", "missing_tail_page", "task_plan_mismatch"]
)
def test_merge_rejects_task_set_or_run_plan_inconsistency(tmp_path, mutation):
    """合并前必须同时核对任务集合、页覆盖和 task/run 分块计划。"""
    run_dir, packages = _prepare_run(tmp_path)
    _write_worker_result(packages["chunk-001"])
    _write_worker_result(packages["chunk-002"])
    run_json_path = run_dir / "run.json"
    run_data = json.loads(run_json_path.read_text(encoding="utf-8"))

    if mutation == "missing_task":
        packages["chunk-002"].rename(run_dir / "omitted-chunk")
    elif mutation == "extra_task":
        (run_dir / "tasks" / "chunk-extra").mkdir()
    elif mutation == "missing_tail_page":
        run_data["chunks"] = {"chunk-001": run_data["chunks"]["chunk-001"]}
        run_data["compatibility"]["chunking_scheme"]["chunks"] = [
            run_data["compatibility"]["chunking_scheme"]["chunks"][0]
        ]
        run_json_path.write_text(json.dumps(run_data), encoding="utf-8")
    else:
        run_data["compatibility"]["chunking_scheme"]["chunks"][0]["context_pages"] = []
        run_json_path.write_text(json.dumps(run_data), encoding="utf-8")

    with pytest.raises(VisualChunkResultError):
        mergeVisualChunkResults(run_dir)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("unexpected", "schema drift"),
        ("run_id", "other-run"),
        ("candidate_sha256", "0" * 64),
        ("chunk_id", "chunk-999"),
        ("core_pages", [2, 1]),
    ],
    ids=["unknown_field", "run_identity", "candidate_identity", "chunk_identity", "core_identity"],
)
def test_result_rejects_unknown_fields_and_identity_mismatch(tmp_path, field_name, value):
    """worker 不得扩展 schema，也不得伪造运行、Candidate、块或核心页身份。"""
    _, packages = _prepare_run(tmp_path)
    task_dir = packages["chunk-001"]
    _write_worker_result(task_dir, **{field_name: value})

    with pytest.raises(VisualChunkResultError):
        validateVisualChunkResult(task_dir)


def test_result_rejects_non_utf8_json(tmp_path):
    """result.json 必须使用 UTF-8，不能以平台默认编码隐式读取。"""
    _, packages = _prepare_run(tmp_path)
    task_dir = packages["chunk-001"]
    (task_dir / "result.json").write_bytes(b"\xff")
    (task_dir / "result.md").write_text(_marked_pages([1, 2]), encoding="utf-8")

    with pytest.raises(VisualChunkResultError):
        validateVisualChunkResult(task_dir)


def test_result_rejects_symlinked_worker_output_when_supported(tmp_path):
    """result.json 必须是本块内普通文件，不能用符号链接绕过边界。"""
    _, packages = _prepare_run(tmp_path)
    task_dir = packages["chunk-001"]
    external_result = tmp_path / "external-result.json"
    external_result.write_text("{}", encoding="utf-8")
    try:
        (task_dir / "result.json").symlink_to(external_result)
    except OSError as exc:
        pytest.skip(f"当前 Windows 环境不允许创建符号链接: {exc}")
    (task_dir / "result.md").write_text(_marked_pages([1, 2]), encoding="utf-8")

    with pytest.raises(VisualChunkResultError):
        validateVisualChunkResult(task_dir)


@pytest.mark.parametrize(
    ("status", "covered_pages", "marked_pages", "unresolved_issues", "failure_code"),
    [
        ("completed", [1, 2], [1, 2], ["needs review"], None),
        ("completed", [1, 2], [1, 2], [], "timeout"),
        ("retryable_failure", [], [], [], "not-a-temporary-code"),
        ("blocked", [], [], [], None),
    ],
    ids=[
        "completed_unresolved",
        "completed_failure",
        "invalid_retry_code",
        "blocked_without_issue",
    ],
)
def test_result_status_rules_reject_incompatible_failure_state(
    tmp_path, status, covered_pages, marked_pages, unresolved_issues, failure_code
):
    """completed、retryable_failure 与 blocked 均有不可替代的状态约束。"""
    _, packages = _prepare_run(tmp_path)
    task_dir = packages["chunk-001"]
    _write_worker_result(
        task_dir,
        status=status,
        covered_pages=covered_pages,
        marked_pages=marked_pages,
        unresolved_issues=unresolved_issues,
        failure_code=failure_code,
    )

    with pytest.raises(VisualChunkResultError):
        validateVisualChunkResult(task_dir)


@pytest.mark.parametrize(
    "crop_request",
    [
        {"page": 3, "bbox": [0.1, 0.2, 0.8, 0.9], "kind": "formula"},
        {"page": 1, "bbox": [0.1, 0.2, 1.1, 0.9], "kind": "formula"},
        {"page": 1, "bbox": [0.8, 0.2, 0.1, 0.9], "kind": "formula"},
        {"page": 1, "bbox": [0.1, 0.2, 0.8, 0.9], "kind": ""},
        {"page": 1, "bbox": [0.1, 0.2, 0.8, 0.9], "kind": "note"},
        {"page": 1, "bbox": [0.1, 0.2, 0.8, 0.9], "kind": "formula", "extra": "x"},
    ],
    ids=[
        "context_page",
        "out_of_bounds_bbox",
        "nonpositive_bbox",
        "empty_kind",
        "unsupported_kind",
        "unknown_field",
    ],
)
def test_result_crop_requests_stay_within_core_page_bbox_and_kind_contract(tmp_path, crop_request):
    """保真裁剪请求只能定位核心页内、面积为正的规范区域。"""
    _, packages = _prepare_run(tmp_path)
    task_dir = packages["chunk-001"]
    _write_worker_result(task_dir, crop_requests=[crop_request])

    with pytest.raises(VisualChunkResultError):
        validateVisualChunkResult(task_dir)


def test_result_crop_request_requires_warning(tmp_path):
    """保真裁剪会降低机器可读性，worker 必须显式留下人工确认警告。"""
    _, packages = _prepare_run(tmp_path)
    task_dir = packages["chunk-001"]
    _write_worker_result(
        task_dir,
        crop_requests=[{"page": 1, "bbox": [0.1, 0.2, 0.8, 0.9], "kind": "table"}],
    )

    with pytest.raises(VisualChunkResultError):
        validateVisualChunkResult(task_dir)
