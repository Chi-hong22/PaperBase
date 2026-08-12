"""视觉 Boundary Review 的任务包、结果契约和续作边界测试。"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from paperbase.core.visual_boundary_review import (
    BoundaryReviewActionRequired,
    BoundaryReviewError,
    ValidatedBoundaryReview,
    prepareOrValidateBoundaryReview,
)
from paperbase.core.visual_task_package import VisualChunkPlan, prepareVisualTaskPackage


def _write_completed_run(tmp_path: Path, *, three_chunks: bool = False) -> Path:
    """创建带两个完成核心块、真实任务包输入的最小视觉运行。"""
    run_dir = tmp_path / ".visual-runs" / "run-one"
    if three_chunks:
        chunk_plans = (
            VisualChunkPlan("chunk-001", (1,), (2,)),
            VisualChunkPlan("chunk-002", (2,), (1, 3)),
            VisualChunkPlan("chunk-003", (3,), (2,)),
        )
    else:
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
                        "page_count": 3,
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
                    plan.chunk_id: {"state": "completed", "lease_token": None}
                    for plan in chunk_plans
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
    for page_number in range(1, 4):
        page_path = rendered_dir / f"page-{page_number:04d}.png"
        page_path.write_bytes(f"rendered-page-{page_number}".encode("ascii"))
        rendered_pages[page_number] = page_path
    packages = prepareVisualTaskPackage(
        run_dir,
        3,
        chunk_plans,
        {plan.chunk_id: f"{plan.chunk_id} fragment" for plan in chunk_plans},
        rendered_pages,
        requested_model="host-model",
    )
    for task_dir in packages.values():
        _write_completed_chunk_result(task_dir)
    return run_dir


def _write_completed_chunk_result(task_dir: Path) -> None:
    task = _read_json(task_dir / "task.json")
    run = task["run"]
    chunk = task["chunk"]
    assert isinstance(run, dict)
    assert isinstance(chunk, dict)
    core_pages = chunk["core_pages"]
    assert isinstance(core_pages, list)
    result = {
        "schema_version": "visual-chunk-result-v1",
        "run_id": run["run_id"],
        "candidate_sha256": run["candidate_sha256"],
        "chunk_id": chunk["chunk_id"],
        "core_pages": core_pages,
        "status": "completed",
        "covered_pages": core_pages,
        "warnings": [],
        "unresolved_issues": [],
        "failure_code": None,
        "crop_requests": [],
    }
    result_markdown = "".join(
        f"<!-- paperbase:visual-page-start page={page_number} -->\n"
        f"Page {page_number} content.\n"
        f"<!-- paperbase:visual-page-end page={page_number} -->\n"
        for page_number in core_pages
    )
    (task_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (task_dir / "result.md").write_text(result_markdown, encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _prepare_review(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    run_dir = _write_completed_run(tmp_path)
    outcome = prepareOrValidateBoundaryReview(run_dir)
    assert isinstance(outcome, BoundaryReviewActionRequired)
    task_package = outcome.task_package
    return run_dir, task_package, _read_json(task_package / "task.json")


def _write_review_result(task_package: Path, **changes: object) -> None:
    task = _read_json(task_package / "task.json")
    run = task["run"]
    items = task["items"]
    assert isinstance(run, dict)
    assert isinstance(items, list)
    checked_item_ids = []
    for item in items:
        assert isinstance(item, dict)
        checked_item_ids.append(item["item_id"])
    result = {
        "schema_version": "visual-boundary-review-result-v1",
        "run_id": run["run_id"],
        "candidate_sha256": run["candidate_sha256"],
        "decision": "pass",
        "checked_item_ids": checked_item_ids,
        "affected_chunk_ids": [],
        "unresolved_issues": [],
        "warnings": [],
    }
    result.update(changes)
    (task_package / "result.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8"
    )


def _make_junction_or_skip(junction_path: Path, target_path: Path) -> None:
    command = f'mklink /J "{junction_path}" "{target_path}"'
    completed = subprocess.run(
        ["cmd", "/d", "/s", "/c", command],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.skip("当前 Windows 环境不允许创建 junction")


def test_boundary_review_prepares_required_items_page_inputs_and_write_boundary(tmp_path):
    """任务必须覆盖首尾、每个块接缝与参考文献尾页，并交付逐页图文输入。"""
    _, task_package, task = _prepare_review(tmp_path)
    items = task["items"]
    inputs = task["inputs"]
    assert isinstance(items, list)
    assert isinstance(inputs, dict)

    assert [item["item_id"] for item in items] == [
        "document-start",
        "document-end",
        "chunk-seam-chunk-001-chunk-002",
        "reference-tail",
    ]
    assert task["allowed_outputs"] == ["result.json"]
    assert task["write_boundary"]["only_paths"] == ["result.json"]
    assert (task_package / inputs["merged_markdown"]).is_file()
    assert [item["page"] for item in inputs["pages"]] == [1, 2, 3]
    for item in inputs["pages"]:
        assert (task_package / item["markdown"]).read_text(encoding="utf-8").strip()
        assert (task_package / item["image"]).read_bytes().startswith(b"rendered-page-")
    serialized_task = json.dumps(task, sort_keys=True)
    assert "page_sha256" not in serialized_task
    assert "prompt_sha256" not in serialized_task
    assert "call_sha256" not in serialized_task


def test_boundary_review_generates_one_seam_for_each_adjacent_chunk_pair(tmp_path):
    """三个连续块必须产生两个接缝检查项，不能因严格 zip 遗漏。"""
    run_dir = _write_completed_run(tmp_path, three_chunks=True)
    outcome = prepareOrValidateBoundaryReview(run_dir)
    assert isinstance(outcome, BoundaryReviewActionRequired)
    task = _read_json(outcome.task_package / "task.json")
    items = task["items"]
    assert isinstance(items, list)

    assert [item["item_id"] for item in items] == [
        "document-start",
        "document-end",
        "chunk-seam-chunk-001-chunk-002",
        "chunk-seam-chunk-002-chunk-003",
        "reference-tail",
    ]


def test_boundary_review_includes_chunks_with_retry_or_rework_history(tmp_path):
    """实际重试或返工过的块必须成为独立 Boundary Review 检查项。"""
    run_dir = _write_completed_run(tmp_path)
    run_json = _read_json(run_dir / "run.json")
    chunks = run_json["chunks"]
    assert isinstance(chunks, dict)
    first_chunk = chunks["chunk-001"]
    assert isinstance(first_chunk, dict)
    first_chunk["retry_count"] = 1
    (run_dir / "run.json").write_text(json.dumps(run_json), encoding="utf-8")
    rework_dir = run_dir / "attempts" / "chunk-002" / "rework-001"
    rework_dir.mkdir(parents=True)
    (rework_dir / "result.md").write_text("old result", encoding="utf-8")
    (rework_dir / "result.json").write_text("{}", encoding="utf-8")

    outcome = prepareOrValidateBoundaryReview(run_dir)

    assert isinstance(outcome, BoundaryReviewActionRequired)
    task = _read_json(outcome.task_package / "task.json")
    items = task["items"]
    assert isinstance(items, list)
    attempt_items = [item for item in items if item["kind"] == "retry_or_rework_chunk"]
    assert attempt_items == [
        {
            "item_id": "chunk-attempt-chunk-001",
            "kind": "retry_or_rework_chunk",
            "pages": [1, 2],
            "chunk_ids": ["chunk-001"],
        },
        {
            "item_id": "chunk-attempt-chunk-002",
            "kind": "retry_or_rework_chunk",
            "pages": [3],
            "chunk_ids": ["chunk-002"],
        },
    ]


def test_boundary_review_reuses_compatible_package_without_result(tmp_path):
    """同一已完成运行重复调用不重写输入，仍返回可交接的等待状态。"""
    run_dir, task_package, _ = _prepare_review(tmp_path)
    input_bytes = {
        path.relative_to(task_package).as_posix(): path.read_bytes()
        for path in task_package.rglob("*")
        if path.is_file()
    }

    repeated_outcome = prepareOrValidateBoundaryReview(run_dir)

    assert isinstance(repeated_outcome, BoundaryReviewActionRequired)
    assert repeated_outcome.task_package == task_package
    assert {
        path.relative_to(task_package).as_posix(): path.read_bytes()
        for path in task_package.rglob("*")
        if path.is_file()
    } == input_bytes


@pytest.mark.parametrize(
    "relative_path", ["merged.md", "pages/page-0001.md", "rendered/page-0001.png"]
)
def test_boundary_review_rejects_existing_input_byte_conflict(tmp_path, relative_path):
    """已有 review 包的任一 PaperBase 输入变化都必须拒绝，不能覆盖或续接错输入。"""
    run_dir, task_package, _ = _prepare_review(tmp_path)
    (task_package / relative_path).write_bytes(b"conflicting boundary input")

    with pytest.raises(BoundaryReviewError):
        prepareOrValidateBoundaryReview(run_dir)


def test_boundary_review_valid_pass_result_is_returned(tmp_path):
    """合法 pass 结果经同一入口验证后成为已验证状态。"""
    run_dir, task_package, _ = _prepare_review(tmp_path)
    _write_review_result(task_package)

    outcome = prepareOrValidateBoundaryReview(run_dir)

    assert isinstance(outcome, ValidatedBoundaryReview)
    assert outcome.task_package == task_package
    assert outcome.result.decision == "pass"
    assert outcome.result.affected_chunk_ids == ()
    assert outcome.result.unresolved_issues == ()


def test_boundary_review_rework_is_limited_to_run_chunks(tmp_path):
    """rework 只能指向当前 run 的块，且必须同时说明未解决问题。"""
    run_dir, task_package, _ = _prepare_review(tmp_path)
    _write_review_result(
        task_package,
        decision="rework_required",
        affected_chunk_ids=["chunk-001"],
        unresolved_issues=["The seam loses a paragraph."],
    )

    outcome = prepareOrValidateBoundaryReview(run_dir)

    assert isinstance(outcome, ValidatedBoundaryReview)
    assert outcome.result.affected_chunk_ids == ("chunk-001",)


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": "rework_required", "affected_chunk_ids": [], "unresolved_issues": ["seam"]},
        {
            "decision": "rework_required",
            "affected_chunk_ids": ["chunk-999"],
            "unresolved_issues": ["seam"],
        },
        {
            "decision": "rework_required",
            "affected_chunk_ids": ["chunk-001"],
            "unresolved_issues": [],
        },
        {"decision": "blocked", "unresolved_issues": []},
    ],
    ids=["empty_affected", "outside_run", "missing_issue", "blocked_without_issue"],
)
def test_boundary_review_rejects_invalid_rework_or_blocked_result(tmp_path, changes):
    """rework 与 blocked 的问题/影响块边界都必须显式且可验证。"""
    run_dir, task_package, _ = _prepare_review(tmp_path)
    _write_review_result(task_package, **changes)

    with pytest.raises(BoundaryReviewError):
        prepareOrValidateBoundaryReview(run_dir)


@pytest.mark.parametrize("mode", ["missing", "extra", "duplicate"])
def test_boundary_review_rejects_incomplete_extra_or_duplicate_checked_items(tmp_path, mode):
    """worker 必须按任务次序且恰好一次确认全部检查项。"""
    run_dir, task_package, task = _prepare_review(tmp_path)
    items = task["items"]
    assert isinstance(items, list)
    item_ids = [item["item_id"] for item in items]
    if mode == "missing":
        checked_item_ids = item_ids[:-1]
    elif mode == "extra":
        checked_item_ids = [*item_ids, "unexpected-item"]
    else:
        checked_item_ids = [item_ids[0], item_ids[0], *item_ids[1:]]
    _write_review_result(task_package, checked_item_ids=checked_item_ids)

    with pytest.raises(BoundaryReviewError):
        prepareOrValidateBoundaryReview(run_dir)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("run_id", "other-run"),
        ("candidate_sha256", "0" * 64),
        ("unknown", "schema drift"),
    ],
    ids=["run_identity", "candidate_identity", "unknown_field"],
)
def test_boundary_review_rejects_identity_or_schema_mismatch(tmp_path, field_name, value):
    """worker 结果不得伪造运行身份或扩展严格结果 schema。"""
    run_dir, task_package, _ = _prepare_review(tmp_path)
    _write_review_result(task_package, **{field_name: value})

    with pytest.raises(BoundaryReviewError):
        prepareOrValidateBoundaryReview(run_dir)


def test_boundary_review_rejects_non_utf8_result(tmp_path):
    """结果必须为 UTF-8 JSON，不能按本机默认编码解释。"""
    run_dir, task_package, _ = _prepare_review(tmp_path)
    (task_package / "result.json").write_bytes(b"\xff")

    with pytest.raises(BoundaryReviewError):
        prepareOrValidateBoundaryReview(run_dir)


def test_boundary_review_rejects_result_symlink_when_supported(tmp_path):
    """worker 唯一输出仍须是 review 目录内的普通文件。"""
    run_dir, task_package, _ = _prepare_review(tmp_path)
    external_result = tmp_path / "external-result.json"
    external_result.write_text("{}", encoding="utf-8")
    try:
        (task_package / "result.json").symlink_to(external_result)
    except OSError as exc:
        pytest.skip(f"当前 Windows 环境不允许创建符号链接: {exc}")

    with pytest.raises(BoundaryReviewError):
        prepareOrValidateBoundaryReview(run_dir)


def test_boundary_review_rejects_extra_worker_output(tmp_path):
    """除了 result.json 外，review worker 不得在任务目录留下任何文件。"""
    run_dir, task_package, _ = _prepare_review(tmp_path)
    (task_package / "worker-notes.md").write_text("outside the contract", encoding="utf-8")

    with pytest.raises(BoundaryReviewError):
        prepareOrValidateBoundaryReview(run_dir)


def test_boundary_review_rejects_junctioned_package_when_supported(tmp_path):
    """Windows junction 也不得把 review 包重定向到运行目录外。"""
    run_dir, task_package, _ = _prepare_review(tmp_path)
    external_package = tmp_path / "external-boundary-review"
    task_package.rename(external_package)
    _make_junction_or_skip(task_package, external_package)

    try:
        with pytest.raises(BoundaryReviewError):
            prepareOrValidateBoundaryReview(run_dir)
    finally:
        if task_package.exists():
            task_package.rmdir()
