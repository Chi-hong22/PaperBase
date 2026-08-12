"""Host-neutral visual-worker task packages and boundary checks.

This module deliberately prepares files only.  It does not call a model, merge
worker output, or advance the visual-repair state machine.
"""

from __future__ import annotations

# ruff: noqa: N802
import hashlib
import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from paperbase.core.visual_chunk_result import (
    PAGE_END_MARKER,
    PAGE_START_MARKER,
    RESULT_JSON_FIELDS,
    RESULT_SCHEMA_VERSION,
    RESULT_STATUSES,
    RETRYABLE_FAILURE_CODES,
)
from paperbase.core.visual_repair_run import isPathReparsePoint

PATH_COMPONENT_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)
ALLOWED_OUTPUTS = ("result.md", "result.json")
LEASE_RELATIVE_PATH = "lease.json"
CANDIDATE_FRAGMENT_SCOPES = frozenset({"page_fragment", "full_document"})


class TaskPackageConflictError(FileExistsError):
    """已有任务包与本次请求的不可变输入不一致。"""


class WorkerBoundaryViolationError(RuntimeError):
    """Worker 在任务包边界外修改了 Visual Repair Run。"""


@dataclass(frozen=True)
class VisualChunkPlan:
    """一个 Worker 独占的核心页与只读上下文页。"""

    chunk_id: str
    core_pages: tuple[int, ...]
    context_pages: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "core_pages", tuple(self.core_pages))
        object.__setattr__(self, "context_pages", tuple(self.context_pages))


@dataclass(frozen=True)
class ProtectedFile:
    """一次边界快照中受保护文件的可观察属性。"""

    relative_path: str
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class WorkerBoundarySnapshot:
    """仅保留在内存中的 Worker 前态快照。

    这不是安全沙箱：同大小且伪造 mtime 的恶意改写，以及 Host 重启后
    快照丢失，不属于此轻量级文件边界检查的保证范围。

    ``lease.json`` 不属于 Worker 边界比较范围，最终采用仍必须由 run
    store 重新验证有效 Lease。
    """

    run_dir: Path
    active_chunk_ids: tuple[str, ...]
    file_paths: frozenset[str]
    protected_files: tuple[ProtectedFile, ...]
    directory_paths: frozenset[str]
    candidate_sha256: str


def prepareVisualTaskPackage(  # noqa: PLR0913
    run_dir: Path,
    page_count: int,
    chunk_plans: Sequence[VisualChunkPlan],
    candidate_fragments: Mapping[str, str],
    rendered_pages: Mapping[int, Path],
    *,
    requested_model: str | None = None,
    template_version: str | None = None,
    candidate_fragment_scope: str = "page_fragment",
) -> dict[str, Path]:
    """准备或复用 Visual Worker 的本地任务包。

    ``template_version`` 默认取自既有 ``run.json``；若显式传入，必须与
    该运行的兼容键一致。模型名只记录在任务描述中，绝不参与兼容判断。
    """
    normalized_run_dir = _validateRunDir(run_dir)
    run_metadata = _loadRunMetadata(normalized_run_dir)
    candidate_path = normalized_run_dir / "candidate.md"
    _requireRegularFile(candidate_path, "candidate.md")
    actual_candidate_sha256 = _calculateFileSha256(candidate_path)
    if actual_candidate_sha256 != run_metadata.candidate_sha256:
        raise ValueError("candidate.md SHA256 与 run.json compatibility 不一致")

    actual_template_version = run_metadata.template_version
    if template_version is not None:
        if not isinstance(template_version, str) or not template_version:
            raise ValueError("template_version must be a non-empty string when provided")
        if template_version != actual_template_version:
            raise ValueError("template_version 与 run.json compatibility 不一致")
    if requested_model is not None and not isinstance(requested_model, str):
        raise ValueError("requested_model must be a string or null")
    normalized_fragment_scope = _validateCandidateFragmentScope(candidate_fragment_scope)

    normalized_plans = _validateChunkPlans(page_count, chunk_plans)
    normalized_fragments = _validateCandidateFragments(candidate_fragments, normalized_plans)
    normalized_rendered_pages = _validateRenderedPages(
        normalized_run_dir, page_count, rendered_pages
    )

    tasks_root = normalized_run_dir / "tasks"
    _prepareTasksRoot(tasks_root, {plan.chunk_id for plan in normalized_plans})
    task_dirs: dict[str, Path] = {}
    for plan in normalized_plans:
        task_dir = tasks_root / plan.chunk_id
        expected_task = _makeTaskDescription(
            run_metadata,
            plan,
            actual_template_version,
            requested_model,
            normalized_fragment_scope,
        )
        if task_dir.exists() or isPathReparsePoint(task_dir):
            _reuseExistingTaskPackage(
                task_dir,
                expected_task,
                normalized_fragments[plan.chunk_id],
                normalized_rendered_pages,
                plan,
            )
        else:
            _createTaskPackage(
                tasks_root,
                task_dir,
                expected_task,
                normalized_fragments[plan.chunk_id],
                normalized_rendered_pages,
                plan,
            )
        task_dirs[plan.chunk_id] = task_dir
    return task_dirs


def captureWorkerBoundary(run_dir: Path, active_chunk_ids: Sequence[str]) -> WorkerBoundarySnapshot:
    """捕获一批并行任务包的 in-memory 前态，用于 Worker 返回后复核。"""
    normalized_run_dir = _validateRunDir(run_dir)
    normalized_chunk_ids = _validateActiveChunkIds(normalized_run_dir, active_chunk_ids)

    run_metadata = _loadRunMetadata(normalized_run_dir)
    candidate_path = normalized_run_dir / "candidate.md"
    _requireRegularFile(candidate_path, "candidate.md")
    candidate_sha256 = _calculateFileSha256(candidate_path)
    if candidate_sha256 != run_metadata.candidate_sha256:
        raise WorkerBoundaryViolationError("candidate.md SHA256 与 run.json compatibility 不一致")

    files, directories = _collectRelativeTree(normalized_run_dir)
    files.pop(LEASE_RELATIVE_PATH, None)
    allowed_outputs = _allowedOutputPaths(normalized_chunk_ids)
    protected_files = tuple(
        ProtectedFile(relative_path, fingerprint.size, fingerprint.mtime_ns)
        for relative_path, fingerprint in sorted(files.items())
        if relative_path not in allowed_outputs
    )
    return WorkerBoundarySnapshot(
        run_dir=normalized_run_dir,
        active_chunk_ids=normalized_chunk_ids,
        file_paths=frozenset(files),
        protected_files=protected_files,
        directory_paths=frozenset(directories),
        candidate_sha256=candidate_sha256,
    )


def validateWorkerBoundary(snapshot: WorkerBoundarySnapshot) -> None:
    """验证 Worker 前后文件树；仅允许 active chunks 的结果文件发生变化。

    ``lease.json`` 由 orchestrator 管理，采用者仍必须通过 run store 校验
    当前 Lease；本函数不以文件边界检查替代该校验。
    """
    if not isinstance(snapshot, WorkerBoundarySnapshot):
        raise TypeError("snapshot must be a WorkerBoundarySnapshot")
    run_dir = _validateRunDir(snapshot.run_dir)
    allowed_outputs = _allowedOutputPaths(snapshot.active_chunk_ids)
    try:
        files, directories = _collectRelativeTree(run_dir)
    except ValueError as exc:
        raise WorkerBoundaryViolationError(str(exc)) from exc

    files.pop(LEASE_RELATIVE_PATH, None)
    if directories != snapshot.directory_paths:
        raise WorkerBoundaryViolationError("Worker 修改了任务包目录树")

    current_paths = frozenset(files)
    added_paths = current_paths - snapshot.file_paths
    removed_paths = snapshot.file_paths - current_paths
    if added_paths - allowed_outputs:
        raise WorkerBoundaryViolationError(
            f"Worker 新增了越界文件: {sorted(added_paths - allowed_outputs)}"
        )
    if removed_paths:
        raise WorkerBoundaryViolationError(f"Worker 删除了运行文件: {sorted(removed_paths)}")

    for relative_path in allowed_outputs & current_paths:
        if not _isRegularFile(run_dir / relative_path):
            raise WorkerBoundaryViolationError(f"Worker 输出不是普通文件: {relative_path}")

    protected = {item.relative_path: item for item in snapshot.protected_files}
    for relative_path, before in protected.items():
        after = files.get(relative_path)
        if after is None:
            raise WorkerBoundaryViolationError(f"Worker 删除了受保护文件: {relative_path}")
        if after.size != before.size or after.mtime_ns != before.mtime_ns:
            raise WorkerBoundaryViolationError(f"Worker 修改了受保护文件: {relative_path}")

    candidate_path = run_dir / "candidate.md"
    if not _isRegularFile(candidate_path):
        raise WorkerBoundaryViolationError("candidate.md 不是普通文件")
    if _calculateFileSha256(candidate_path) != snapshot.candidate_sha256:
        raise WorkerBoundaryViolationError("candidate.md SHA256 已变化")


@dataclass(frozen=True)
class _RunMetadata:
    run_id: str
    candidate_sha256: str
    template_version: str


@dataclass(frozen=True)
class _FileFingerprint:
    size: int
    mtime_ns: int


def _validateChunkPlans(
    page_count: int, chunk_plans: Sequence[VisualChunkPlan]
) -> tuple[VisualChunkPlan, ...]:
    if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count <= 0:
        raise ValueError("page_count must be a positive integer")
    plans = tuple(chunk_plans)
    if not plans:
        raise ValueError("chunk_plans must not be empty")

    covered_pages: list[int] = []
    chunk_ids: set[str] = set()
    normalized_plans: list[VisualChunkPlan] = []
    for plan in plans:
        if not isinstance(plan, VisualChunkPlan):
            raise TypeError("chunk_plans must contain VisualChunkPlan values")
        chunk_id = _validatePathComponent(plan.chunk_id, "chunk_id")
        if chunk_id in chunk_ids:
            raise ValueError("chunk_ids must be unique")
        chunk_ids.add(chunk_id)
        core_pages = _validatePages(plan.core_pages, page_count, "core_pages")
        context_pages = _validatePages(plan.context_pages, page_count, "context_pages")
        if not core_pages:
            raise ValueError("core_pages must not be empty")
        if core_pages != tuple(range(core_pages[0], core_pages[-1] + 1)):
            raise ValueError(f"core_pages must be continuous for chunk {chunk_id}")
        if len(context_pages) != len(set(context_pages)):
            raise ValueError(f"context_pages must not repeat pages for chunk {chunk_id}")
        if set(core_pages) & set(context_pages):
            raise ValueError(f"context_pages must not duplicate core_pages for chunk {chunk_id}")
        covered_pages.extend(core_pages)
        normalized_plans.append(VisualChunkPlan(chunk_id, core_pages, context_pages))

    if len(covered_pages) != len(set(covered_pages)):
        raise ValueError("core_pages must not overlap across chunks")
    if set(covered_pages) != set(range(1, page_count + 1)):
        raise ValueError("core_pages must cover every page exactly once")
    return tuple(normalized_plans)


def _validatePages(pages: Sequence[int], page_count: int, field_name: str) -> tuple[int, ...]:
    normalized_pages = tuple(pages)
    for page_number in normalized_pages:
        if isinstance(page_number, bool) or not isinstance(page_number, int):
            raise ValueError(f"{field_name} must contain integers")
        if not 1 <= page_number <= page_count:
            raise ValueError(f"{field_name} page is outside 1..page_count")
    return normalized_pages


def _validateCandidateFragments(
    candidate_fragments: Mapping[str, str], plans: Sequence[VisualChunkPlan]
) -> dict[str, str]:
    if not isinstance(candidate_fragments, Mapping):
        raise TypeError("candidate_fragments must be a mapping")
    expected_ids = {plan.chunk_id for plan in plans}
    if set(candidate_fragments) != expected_ids:
        raise ValueError("candidate_fragments must match chunk_plans exactly")
    fragments: dict[str, str] = {}
    for chunk_id in expected_ids:
        fragment = candidate_fragments[chunk_id]
        if not isinstance(fragment, str):
            raise ValueError(f"candidate fragment must be text: {chunk_id}")
        try:
            fragment.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError(f"candidate fragment is not UTF-8 encodable: {chunk_id}") from exc
        fragments[chunk_id] = fragment
    return fragments


def _validateCandidateFragmentScope(candidate_fragment_scope: str) -> str:  # noqa: N802
    if not isinstance(candidate_fragment_scope, str):
        raise ValueError("candidate_fragment_scope must be a string")
    if candidate_fragment_scope not in CANDIDATE_FRAGMENT_SCOPES:
        raise ValueError("candidate_fragment_scope is not supported")
    return candidate_fragment_scope


def _validateRenderedPages(
    run_dir: Path, page_count: int, rendered_pages: Mapping[int, Path]
) -> dict[int, Path]:
    if not isinstance(rendered_pages, Mapping):
        raise TypeError("rendered_pages must be a mapping")
    expected_pages = set(range(1, page_count + 1))
    if set(rendered_pages) != expected_pages:
        raise ValueError("rendered_pages must map every page exactly once")
    rendered_root = run_dir / "rendered"
    if isPathReparsePoint(rendered_root) or not rendered_root.is_dir():
        raise FileNotFoundError(f"rendered 页目录不存在: {rendered_root}")
    resolved_rendered_root = rendered_root.resolve()
    normalized: dict[int, Path] = {}
    for page_number in sorted(expected_pages):
        source_path = Path(rendered_pages[page_number])
        _requireRegularFile(source_path, f"rendered page {page_number}")
        try:
            source_path.resolve().relative_to(resolved_rendered_root)
        except ValueError as exc:
            raise ValueError("rendered page must stay under run_dir/rendered") from exc
        normalized[page_number] = source_path
    return normalized


def _prepareTasksRoot(tasks_root: Path, expected_chunk_ids: set[str]) -> None:
    if isPathReparsePoint(tasks_root):
        raise TaskPackageConflictError(f"tasks 目录不能是 reparse point: {tasks_root}")
    if not tasks_root.exists():
        tasks_root.mkdir()
        if isPathReparsePoint(tasks_root) or not tasks_root.is_dir():
            raise TaskPackageConflictError(f"tasks 目录不能是 reparse point: {tasks_root}")
        return
    if not tasks_root.is_dir():
        raise TaskPackageConflictError(f"tasks 路径不是目录: {tasks_root}")
    actual_names: set[str] = set()
    for entry in os.scandir(tasks_root):
        if isPathReparsePoint(Path(entry.path)) or not entry.is_dir(follow_symlinks=False):
            raise TaskPackageConflictError(f"tasks 目录包含冲突条目: {entry.name}")
        actual_names.add(entry.name)
    unexpected_names = actual_names - expected_chunk_ids
    if unexpected_names:
        raise TaskPackageConflictError(
            f"tasks 目录包含不属于当前计划的块: {sorted(unexpected_names)}"
        )


def _makeTaskDescription(
    run_metadata: _RunMetadata,
    plan: VisualChunkPlan,
    template_version: str,
    requested_model: str | None,
    candidate_fragment_scope: str,
) -> dict[str, Any]:
    core_inputs = [_pageInputPath("core", page_number) for page_number in plan.core_pages]
    context_inputs = [_pageInputPath("context", page_number) for page_number in plan.context_pages]
    read_only_paths = ["candidate-fragment.md", *core_inputs, *context_inputs]
    return {
        "run": {
            "run_id": run_metadata.run_id,
            "candidate_sha256": run_metadata.candidate_sha256,
        },
        "chunk": {
            "chunk_id": plan.chunk_id,
            "core_pages": list(plan.core_pages),
            "context_pages": list(plan.context_pages),
        },
        "template_version": template_version,
        "requested_model": requested_model,
        "candidate_fragment": "candidate-fragment.md",
        "candidate_fragment_scope": candidate_fragment_scope,
        "inputs": {"core": core_inputs, "context": context_inputs},
        "allowed_outputs": list(ALLOWED_OUTPUTS),
        "output_contract": _makeOutputContract(),
        "write_boundary": {
            "only_paths": list(ALLOWED_OUTPUTS),
            "scope": "Write only these paths in this chunk; all other run and task files are read-only.",
        },
        "read_only_boundary": {"paths": read_only_paths},
    }


def _makeOutputContract() -> dict[str, Any]:
    """写入不依赖任一 Agent Host 的 worker 输出协议。"""
    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "result_json": {
            "required_fields": sorted(RESULT_JSON_FIELDS),
            "field_types": {
                "schema_version": "string",
                "run_id": "string matching task.run.run_id",
                "candidate_sha256": "64-character SHA-256 string matching task.run.candidate_sha256",
                "chunk_id": "string matching task.chunk.chunk_id",
                "core_pages": "array of positive integers exactly matching task.chunk.core_pages",
                "status": "one listed status string",
                "covered_pages": "array of core page integers in core_pages order",
                "warnings": "array of non-empty strings",
                "unresolved_issues": "array of non-empty strings",
                "failure_code": "string or null",
                "crop_requests": "array of crop_request objects",
            },
            "status_values": sorted(RESULT_STATUSES),
            "retryable_failure_codes": sorted(RETRYABLE_FAILURE_CODES),
            "crop_request": {
                "required_fields": ["page", "bbox", "kind"],
                "bbox": "normalized [left, top, right, bottom] within 0..1",
                "kind_values": ["formula", "table", "image"],
            },
            "rules": [
                "completed covers every core page and has no unresolved_issues or failure_code",
                "retryable_failure uses one listed retryable_failure_code",
                "blocked has at least one unresolved_issue",
                "every crop_request requires at least one warning",
            ],
        },
        "result_markdown": {
            "encoding": "utf-8",
            "page_start_marker": PAGE_START_MARKER,
            "page_end_marker": PAGE_END_MARKER,
            "rules": [
                "write page markers on lines by themselves",
                "write only core pages in core_pages order; context pages are read-only",
                "covered_pages must exactly match the pages enclosed by markers",
                "completed encloses every core page exactly once",
                "do not write content outside page markers",
            ],
        },
    }


def _createTaskPackage(
    tasks_root: Path,
    task_dir: Path,
    expected_task: dict[str, Any],
    fragment: str,
    rendered_pages: Mapping[int, Path],
    plan: VisualChunkPlan,
) -> None:
    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{plan.chunk_id}.", dir=tasks_root))
    try:
        (temporary_dir / "inputs" / "core").mkdir(parents=True)
        (temporary_dir / "inputs" / "context").mkdir(parents=True)
        _writeBytes(temporary_dir / "candidate-fragment.md", fragment.encode("utf-8"))
        for section, page_numbers in (("core", plan.core_pages), ("context", plan.context_pages)):
            for page_number in page_numbers:
                destination = temporary_dir / _pageInputPath(section, page_number)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(rendered_pages[page_number], destination)
        _writeJsonAtomically(temporary_dir / "task.json", expected_task)
        os.replace(temporary_dir, task_dir)
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise


def _reuseExistingTaskPackage(
    task_dir: Path,
    expected_task: dict[str, Any],
    fragment: str,
    rendered_pages: Mapping[int, Path],
    plan: VisualChunkPlan,
) -> None:
    if isPathReparsePoint(task_dir) or not task_dir.is_dir():
        raise TaskPackageConflictError(f"任务包目录冲突: {task_dir}")
    _validateExistingTaskTree(task_dir, expected_task)
    task_path = task_dir / "task.json"
    existing_task = _readJsonObject(task_path, "task.json")
    if _withoutRequestedModel(existing_task) != _withoutRequestedModel(expected_task):
        raise TaskPackageConflictError(f"任务包不可变输入冲突: {task_dir}")

    fragment_path = task_dir / "candidate-fragment.md"
    if fragment_path.read_bytes() != fragment.encode("utf-8"):
        raise TaskPackageConflictError(f"candidate fragment 冲突: {task_dir}")
    for section, page_numbers in (("core", plan.core_pages), ("context", plan.context_pages)):
        for page_number in page_numbers:
            packaged_page = task_dir / _pageInputPath(section, page_number)
            if not _filesEqual(packaged_page, rendered_pages[page_number]):
                raise TaskPackageConflictError(f"渲染页输入冲突: {packaged_page}")

    has_worker_result = any((task_dir / output_name).exists() for output_name in ALLOWED_OUTPUTS)
    if (
        not has_worker_result
        and existing_task.get("requested_model") != expected_task["requested_model"]
    ):
        _writeJsonAtomically(task_path, expected_task)


def _validateExistingTaskTree(task_dir: Path, expected_task: Mapping[str, Any]) -> None:
    try:
        files, directories = _collectRelativeTree(task_dir)
    except ValueError as exc:
        raise TaskPackageConflictError(str(exc)) from exc
    expected_files = {
        "task.json",
        "candidate-fragment.md",
        *expected_task["inputs"]["core"],
        *expected_task["inputs"]["context"],
    }
    allowed_files = expected_files | set(ALLOWED_OUTPUTS)
    if set(files) - allowed_files:
        raise TaskPackageConflictError(
            f"任务包包含未声明文件: {sorted(set(files) - allowed_files)}"
        )
    if not expected_files.issubset(files):
        raise TaskPackageConflictError("任务包缺少既有输入文件")
    expected_directories = {"inputs", "inputs/core", "inputs/context"}
    if directories != expected_directories:
        raise TaskPackageConflictError("任务包目录结构冲突")
    for relative_path in expected_files:
        if not _isRegularFile(task_dir / relative_path):
            raise TaskPackageConflictError(f"任务包输入不是普通文件: {relative_path}")
    for relative_path in set(ALLOWED_OUTPUTS) & set(files):
        if not _isRegularFile(task_dir / relative_path):
            raise TaskPackageConflictError(f"任务包输出不是普通文件: {relative_path}")


def _withoutRequestedModel(task: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in task.items() if key != "requested_model"}


def _allowedOutputPaths(chunk_ids: Sequence[str]) -> frozenset[str]:
    return frozenset(
        f"tasks/{chunk_id}/{output_name}"
        for chunk_id in chunk_ids
        for output_name in ALLOWED_OUTPUTS
    )


def _validateActiveChunkIds(run_dir: Path, active_chunk_ids: Sequence[str]) -> tuple[str, ...]:
    if isinstance(active_chunk_ids, str):
        raise TypeError("active_chunk_ids must be a non-empty sequence of chunk ids")
    chunk_ids = tuple(_validatePathComponent(chunk_id, "chunk_id") for chunk_id in active_chunk_ids)
    if not chunk_ids:
        raise ValueError("active_chunk_ids must not be empty")
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("active_chunk_ids must be unique")
    for chunk_id in chunk_ids:
        task_dir = run_dir / "tasks" / chunk_id
        if (
            isPathReparsePoint(task_dir)
            or not task_dir.is_dir()
            or not _isRegularFile(task_dir / "task.json")
        ):
            raise FileNotFoundError(f"任务包不存在: {task_dir}")
    return chunk_ids


def _pageInputPath(section: str, page_number: int) -> str:
    return f"inputs/{section}/page-{page_number:04d}.png"


def _validateRunDir(run_dir: Path) -> Path:
    path = Path(run_dir)
    if path.parent.name != ".visual-runs":
        raise FileNotFoundError(f"Visual Repair Run 必须直接位于 .visual-runs: {path}")
    paper_dir = path.parent.parent
    if (
        isPathReparsePoint(paper_dir)
        or isPathReparsePoint(path.parent)
        or isPathReparsePoint(path)
        or not path.is_dir()
    ):
        raise FileNotFoundError(f"Visual Repair Run 目录不存在或不安全: {path}")
    _requireRegularFile(path / "run.json", "run.json")
    resolved_root = path.parent.resolve()
    resolved_path = path.resolve()
    if resolved_path.parent != resolved_root:
        raise FileNotFoundError(f"Visual Repair Run 越出 .visual-runs: {path}")
    return resolved_path


def _loadRunMetadata(run_dir: Path) -> _RunMetadata:
    data = _readJsonObject(run_dir / "run.json", "run.json")
    compatibility = data.get("compatibility")
    if not isinstance(compatibility, dict):
        raise ValueError("run.json compatibility must be an object")
    run_id = data.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run.json run_id must be a non-empty string")
    candidate_sha256 = compatibility.get("candidate_sha256")
    if not _isSha256(candidate_sha256):
        raise ValueError("run.json compatibility.candidate_sha256 must be a SHA256 digest")
    template_version = compatibility.get("template_version")
    if not isinstance(template_version, str) or not template_version:
        raise ValueError("run.json compatibility.template_version must be a non-empty string")
    return _RunMetadata(run_id, candidate_sha256.lower(), template_version)


def _readJsonObject(path: Path, label: str) -> dict[str, Any]:
    _requireRegularFile(path, label)
    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be an object")
    return data


def _writeJsonAtomically(path: Path, data: Mapping[str, Any]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _writeBytes(path: Path, data: bytes) -> None:
    with path.open("xb") as file:
        file.write(data)


def _collectRelativeTree(root: Path) -> tuple[dict[str, _FileFingerprint], frozenset[str]]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"目录不是普通目录: {root}")
    files: dict[str, _FileFingerprint] = {}
    directories: set[str] = set()
    pending_directories = [root]
    while pending_directories:
        directory = pending_directories.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                entry_path = Path(entry.path)
                relative_path = entry_path.relative_to(root).as_posix()
                if isPathReparsePoint(entry_path):
                    raise ValueError(f"目录树包含 reparse point: {relative_path}")
                entry_stat = entry.stat(follow_symlinks=False)
                if stat.S_ISREG(entry_stat.st_mode):
                    files[relative_path] = _FileFingerprint(
                        entry_stat.st_size, entry_stat.st_mtime_ns
                    )
                elif stat.S_ISDIR(entry_stat.st_mode):
                    directories.add(relative_path)
                    pending_directories.append(entry_path)
                else:
                    raise ValueError(f"目录树包含非普通文件: {relative_path}")
    return files, frozenset(directories)


def _isRegularFile(path: Path) -> bool:
    if isPathReparsePoint(path):
        return False
    try:
        return stat.S_ISREG(os.stat(path, follow_symlinks=False).st_mode)
    except FileNotFoundError:
        return False


def _requireRegularFile(path: Path, label: str) -> None:
    if not _isRegularFile(path):
        raise FileNotFoundError(f"{label} 必须是存在的普通文件: {path}")


def _calculateFileSha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _filesEqual(first_path: Path, second_path: Path) -> bool:
    if not _isRegularFile(first_path) or not _isRegularFile(second_path):
        return False
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


def _validatePathComponent(value: str, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or ".." in value
        or any(character not in PATH_COMPONENT_CHARS for character in value)
    ):
        raise ValueError(f"{field_name} must be a safe path component")
    return value


def _isSha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )
