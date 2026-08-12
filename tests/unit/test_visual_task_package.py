import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from paperbase.core.visual_task_package import (
    TaskPackageConflictError,
    VisualChunkPlan,
    WorkerBoundaryViolationError,
    captureWorkerBoundary,
    prepareVisualTaskPackage,
    validateWorkerBoundary,
)


def _write_run(run_dir: Path, page_count: int = 3) -> dict[int, Path]:
    run_dir.mkdir(parents=True)
    candidate = run_dir / "candidate.md"
    candidate.write_text("candidate body\n", encoding="utf-8")
    candidate_sha256 = hashlib.sha256(candidate.read_bytes()).hexdigest()
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "compatibility": {
                    "candidate_sha256": candidate_sha256,
                    "template_version": "visual-v1",
                },
            }
        ),
        encoding="utf-8",
    )
    rendered_dir = run_dir / "rendered"
    rendered_dir.mkdir()
    return {
        page_number: _write_page(rendered_dir / f"page-{page_number:04d}.png", page_number)
        for page_number in range(1, page_count + 1)
    }


def _write_page(path: Path, page_number: int) -> Path:
    path.write_bytes(f"not-a-real-png-{page_number}".encode("ascii"))
    return path


def _make_junction_or_skip(link_path: Path, target_path: Path) -> None:
    target_path.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link_path), str(target_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("当前 Windows 环境不允许创建 junction")


def _remove_junction(link_path: Path) -> None:
    subprocess.run(
        ["cmd.exe", "/d", "/c", "rmdir", str(link_path)],
        capture_output=True,
        text=True,
        check=True,
    )


def _plans() -> tuple[VisualChunkPlan, VisualChunkPlan]:
    return (
        VisualChunkPlan("chunk-001", (1, 2), (3,)),
        VisualChunkPlan("chunk-002", (3,), (2,)),
    )


def _prepare(
    tmp_path: Path,
    *,
    requested_model: str | None = "model-a",
    candidate_fragment_scope: str = "page_fragment",
) -> tuple[Path, dict[str, Path]]:
    run_dir = tmp_path / ".visual-runs" / "run-one"
    rendered_pages = _write_run(run_dir)
    packages = prepareVisualTaskPackage(
        run_dir,
        3,
        _plans(),
        {"chunk-001": "fragment one", "chunk-002": "fragment two"},
        rendered_pages,
        requested_model=requested_model,
        candidate_fragment_scope=candidate_fragment_scope,
    )
    return run_dir, packages


def test_prepare_creates_host_neutral_relative_task_inputs(tmp_path):
    run_dir, packages = _prepare(tmp_path)
    first_task = packages["chunk-001"]
    task_data = json.loads((first_task / "task.json").read_text(encoding="utf-8"))

    assert task_data["run"]["run_id"] == "run-one"
    assert task_data["chunk"] == {
        "chunk_id": "chunk-001",
        "core_pages": [1, 2],
        "context_pages": [3],
    }
    assert task_data["template_version"] == "visual-v1"
    assert task_data["requested_model"] == "model-a"
    assert task_data["allowed_outputs"] == ["result.md", "result.json"]
    assert task_data["write_boundary"]["only_paths"] == ["result.md", "result.json"]
    output_contract = task_data["output_contract"]
    assert output_contract["result_schema_version"] == "visual-chunk-result-v1"
    assert set(output_contract["result_json"]["required_fields"]) == {
        "candidate_sha256",
        "chunk_id",
        "core_pages",
        "covered_pages",
        "crop_requests",
        "failure_code",
        "run_id",
        "schema_version",
        "status",
        "unresolved_issues",
        "warnings",
    }
    assert output_contract["result_markdown"]["page_start_marker"] == (
        "<!-- paperbase:visual-page-start page={page} -->"
    )
    assert output_contract["result_markdown"]["page_end_marker"] == (
        "<!-- paperbase:visual-page-end page={page} -->"
    )
    assert task_data["candidate_fragment"] == "candidate-fragment.md"
    assert task_data["candidate_fragment_scope"] == "page_fragment"
    assert task_data["inputs"]["core"] == [
        "inputs/core/page-0001.png",
        "inputs/core/page-0002.png",
    ]
    assert all(not Path(path).is_absolute() for path in task_data["read_only_boundary"]["paths"])
    assert (first_task / "candidate-fragment.md").read_text(encoding="utf-8") == "fragment one"
    assert (
        (first_task / "inputs" / "core" / "page-0001.png")
        .read_bytes()
        .startswith(b"not-a-real-png")
    )
    assert not any(path.suffix.lower() == ".pdf" for path in first_task.rglob("*"))
    assert run_dir / "candidate.md" != first_task / "candidate-fragment.md"


def test_prepare_requires_run_directly_under_visual_runs(tmp_path):
    run_dir = tmp_path / "arbitrary-run"
    rendered_pages = _write_run(run_dir)

    with pytest.raises(FileNotFoundError, match=".visual-runs"):
        prepareVisualTaskPackage(
            run_dir,
            3,
            _plans(),
            {"chunk-001": "fragment one", "chunk-002": "fragment two"},
            rendered_pages,
        )

    assert not (run_dir / "tasks").exists()


def test_prepare_rejects_junctioned_tasks_root_without_writing_target(tmp_path):
    run_dir = tmp_path / ".visual-runs" / "run-one"
    rendered_pages = _write_run(run_dir)
    external_target = tmp_path / "external-tasks"
    _make_junction_or_skip(run_dir / "tasks", external_target)
    try:
        with pytest.raises(TaskPackageConflictError, match="reparse"):
            prepareVisualTaskPackage(
                run_dir,
                3,
                _plans(),
                {"chunk-001": "fragment one", "chunk-002": "fragment two"},
                rendered_pages,
            )

        assert list(external_target.iterdir()) == []
    finally:
        _remove_junction(run_dir / "tasks")


def test_prepare_rejects_run_under_junctioned_paper_root(tmp_path):
    external_paper = tmp_path / "external-paper"
    external_run = external_paper / ".visual-runs" / "run-one"
    rendered_pages = _write_run(external_run)
    paper_link = tmp_path / "paper"
    _make_junction_or_skip(paper_link, external_paper)
    linked_run = paper_link / ".visual-runs" / "run-one"
    linked_pages = {
        page: linked_run / "rendered" / path.name for page, path in rendered_pages.items()
    }
    try:
        with pytest.raises(FileNotFoundError, match="不安全"):
            prepareVisualTaskPackage(
                linked_run,
                3,
                _plans(),
                {"chunk-001": "fragment one", "chunk-002": "fragment two"},
                linked_pages,
            )

        assert not (external_run / "tasks").exists()
    finally:
        _remove_junction(paper_link)


@pytest.mark.parametrize(
    "plans",
    [
        (VisualChunkPlan("chunk-001", (1, 2)), VisualChunkPlan("chunk-002", (2, 3))),
        (VisualChunkPlan("chunk-001", (1,)), VisualChunkPlan("chunk-002", (3,))),
        (VisualChunkPlan("chunk-001", (1, 3)), VisualChunkPlan("chunk-002", (2,))),
        (VisualChunkPlan("chunk-001", (1, 2)), VisualChunkPlan("chunk-002", (4,))),
    ],
)
def test_page_plan_rejects_overlap_gap_noncontinuous_and_out_of_range(tmp_path, plans):
    run_dir = tmp_path / ".visual-runs" / "run-one"
    rendered_pages = _write_run(run_dir)

    with pytest.raises(ValueError):
        prepareVisualTaskPackage(
            run_dir,
            3,
            plans,
            {"chunk-001": "one", "chunk-002": "two"},
            rendered_pages,
        )


def test_invalid_chunk_id_rejects_path_traversal(tmp_path):
    run_dir = tmp_path / ".visual-runs" / "run-one"
    rendered_pages = _write_run(run_dir)

    with pytest.raises(ValueError):
        prepareVisualTaskPackage(
            run_dir,
            3,
            (VisualChunkPlan("../outside", (1, 2, 3)),),
            {"../outside": "fragment"},
            rendered_pages,
        )


def test_model_change_updates_pending_package_without_creating_a_new_run(tmp_path):
    run_dir, packages = _prepare(tmp_path, requested_model="model-a")

    packages_after = prepareVisualTaskPackage(
        run_dir,
        3,
        _plans(),
        {"chunk-001": "fragment one", "chunk-002": "fragment two"},
        {
            page_number: run_dir / "rendered" / f"page-{page_number:04d}.png"
            for page_number in (1, 2, 3)
        },
        requested_model="model-b",
    )

    task_data = json.loads((packages_after["chunk-001"] / "task.json").read_text(encoding="utf-8"))
    assert packages_after == packages
    assert task_data["requested_model"] == "model-b"


def test_model_change_keeps_completed_chunk_task_record_and_results(tmp_path):
    run_dir, packages = _prepare(tmp_path, requested_model="model-a")
    result_markdown = packages["chunk-001"] / "result.md"
    result_json = packages["chunk-001"] / "result.json"
    result_markdown.write_text("worker result", encoding="utf-8")
    result_json.write_text('{"status": "ok"}', encoding="utf-8")

    prepareVisualTaskPackage(
        run_dir,
        3,
        _plans(),
        {"chunk-001": "fragment one", "chunk-002": "fragment two"},
        {
            page_number: run_dir / "rendered" / f"page-{page_number:04d}.png"
            for page_number in (1, 2, 3)
        },
        requested_model="model-b",
    )

    task_data = json.loads((packages["chunk-001"] / "task.json").read_text(encoding="utf-8"))
    assert task_data["requested_model"] == "model-a"
    assert result_markdown.read_text(encoding="utf-8") == "worker result"
    assert result_json.read_text(encoding="utf-8") == '{"status": "ok"}'


def test_candidate_fragment_scope_is_an_immutable_task_input(tmp_path):
    run_dir, packages = _prepare(tmp_path, candidate_fragment_scope="full_document")

    with pytest.raises(TaskPackageConflictError):
        prepareVisualTaskPackage(
            run_dir,
            3,
            _plans(),
            {"chunk-001": "fragment one", "chunk-002": "fragment two"},
            {
                page_number: run_dir / "rendered" / f"page-{page_number:04d}.png"
                for page_number in (1, 2, 3)
            },
            requested_model="model-a",
            candidate_fragment_scope="page_fragment",
        )

    task_data = json.loads((packages["chunk-001"] / "task.json").read_text(encoding="utf-8"))
    assert task_data["candidate_fragment_scope"] == "full_document"


def test_other_input_conflict_fails_without_touching_worker_result(tmp_path):
    run_dir, packages = _prepare(tmp_path)
    result_path = packages["chunk-001"] / "result.md"
    result_path.write_text("finished", encoding="utf-8")

    with pytest.raises(TaskPackageConflictError):
        prepareVisualTaskPackage(
            run_dir,
            3,
            _plans(),
            {"chunk-001": "changed fragment", "chunk-002": "fragment two"},
            {
                page_number: run_dir / "rendered" / f"page-{page_number:04d}.png"
                for page_number in (1, 2, 3)
            },
            requested_model="model-b",
        )

    assert result_path.read_text(encoding="utf-8") == "finished"


def test_legal_current_chunk_results_pass_boundary_validation(tmp_path):
    run_dir, packages = _prepare(tmp_path)
    snapshot = captureWorkerBoundary(run_dir, ("chunk-001",))
    (packages["chunk-001"] / "result.md").write_text("worker result", encoding="utf-8")
    (packages["chunk-001"] / "result.json").write_text('{"pages": [1, 2]}', encoding="utf-8")

    validateWorkerBoundary(snapshot)


def test_parallel_active_chunk_results_pass_boundary_validation(tmp_path):
    run_dir, packages = _prepare(tmp_path)
    snapshot = captureWorkerBoundary(run_dir, ("chunk-001", "chunk-002"))
    for chunk_id in ("chunk-001", "chunk-002"):
        (packages[chunk_id] / "result.md").write_text(f"{chunk_id} result", encoding="utf-8")
        (packages[chunk_id] / "result.json").write_text('{"status": "ok"}', encoding="utf-8")

    validateWorkerBoundary(snapshot)


def test_boundary_rejects_non_active_chunk_result(tmp_path):
    run_dir, packages = _prepare(tmp_path)
    snapshot = captureWorkerBoundary(run_dir, ("chunk-001",))
    (packages["chunk-002"] / "result.md").write_text("other worker", encoding="utf-8")

    with pytest.raises(WorkerBoundaryViolationError):
        validateWorkerBoundary(snapshot)


def test_boundary_allows_orchestrator_lease_renewal(tmp_path):
    run_dir, _ = _prepare(tmp_path)
    (run_dir / "lease.json").write_text('{"expires_at": "before"}', encoding="utf-8")
    snapshot = captureWorkerBoundary(run_dir, ("chunk-001",))
    (run_dir / "lease.json").write_text('{"expires_at": "later"}', encoding="utf-8")

    validateWorkerBoundary(snapshot)


@pytest.mark.parametrize(
    "mutation",
    ["candidate", "run_json", "rendered", "other_chunk", "shared_file"],
)
def test_boundary_detects_actual_protected_file_mutations(tmp_path, mutation):
    run_dir, packages = _prepare(tmp_path)
    snapshot = captureWorkerBoundary(run_dir, ("chunk-001",))

    if mutation == "candidate":
        (run_dir / "candidate.md").write_text("changed candidate", encoding="utf-8")
    elif mutation == "run_json":
        (run_dir / "run.json").write_text("{}", encoding="utf-8")
    elif mutation == "rendered":
        (run_dir / "rendered" / "page-0001.png").write_bytes(b"changed rendered page")
    elif mutation == "other_chunk":
        (packages["chunk-002"] / "candidate-fragment.md").write_text("changed", encoding="utf-8")
    else:
        (run_dir / "shared-state.json").write_text("{}", encoding="utf-8")

    with pytest.raises(WorkerBoundaryViolationError):
        validateWorkerBoundary(snapshot)


def test_boundary_rejects_symlink_when_supported(tmp_path):
    run_dir, packages = _prepare(tmp_path)
    target = packages["chunk-001"] / "result.md"
    external = tmp_path / "external-result.md"
    external.write_text("outside", encoding="utf-8")
    try:
        os.symlink(external, target)
    except OSError:
        pytest.skip("当前 Windows 环境不允许创建 symlink")

    with pytest.raises(WorkerBoundaryViolationError):
        captureWorkerBoundary(run_dir, ("chunk-001",))
