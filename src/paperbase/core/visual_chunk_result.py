"""Strict, host-neutral validation and merging for visual worker results.

This module only reads worker-owned ``result.md`` and ``result.json`` files.
It deliberately does not advance run state, create fallback assets, or write
Canonical Markdown.
"""

from __future__ import annotations

# ruff: noqa: N802
import json
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from paperbase.core.visual_repair_run import isPathReparsePoint

RESULT_SCHEMA_VERSION = "visual-chunk-result-v1"
RESULT_STATUSES = frozenset({"completed", "retryable_failure", "blocked"})
RETRYABLE_FAILURE_CODES = frozenset({"http_429", "http_503", "timeout", "channel_error"})
CROP_KINDS = frozenset({"formula", "table", "image"})
RESULT_JSON_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "candidate_sha256",
        "chunk_id",
        "core_pages",
        "status",
        "covered_pages",
        "warnings",
        "unresolved_issues",
        "failure_code",
        "crop_requests",
    }
)
PAGE_START_MARKER = "<!-- paperbase:visual-page-start page={page} -->"
PAGE_END_MARKER = "<!-- paperbase:visual-page-end page={page} -->"
_PAGE_START_PATTERN = re.compile(r"^<!-- paperbase:visual-page-start page=([1-9][0-9]*) -->\r?\n?$")
_PAGE_END_PATTERN = re.compile(r"^<!-- paperbase:visual-page-end page=([1-9][0-9]*) -->\r?\n?$")
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_PATH_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class VisualChunkResultError(ValueError):
    """Worker 结果不符合任务包或结果契约。"""


@dataclass(frozen=True)
class CropRequest:
    """供后续本地保真裁剪使用的归一化页面区域请求。"""

    page: int
    bbox: tuple[float, float, float, float]
    kind: str


@dataclass(frozen=True)
class VisualChunkResult:
    """已验证的单个 worker 结果，页 Markdown 不含临时标记。"""

    schema_version: str
    run_id: str
    candidate_sha256: str
    chunk_id: str
    core_pages: tuple[int, ...]
    status: str
    covered_pages: tuple[int, ...]
    warnings: tuple[str, ...]
    unresolved_issues: tuple[str, ...]
    failure_code: str | None
    crop_requests: tuple[CropRequest, ...]
    page_markdown: dict[int, str]


def validateVisualChunkResult(task_dir: Path) -> VisualChunkResult:
    """读取并严格验证一个任务包中唯一允许的 worker 输出。

    任务包与 ``run.json`` 是身份和页归属的真值；worker 提交的身份字段
    必须逐项匹配。此函数只读取文件，不改变运行状态或文件内容。
    """
    normalized_task_dir = _validateTaskDir(task_dir)
    run_dir = normalized_task_dir.parent.parent
    run_metadata = _loadRunMetadata(run_dir)
    task = _loadTaskDescription(normalized_task_dir / "task.json")
    task_metadata = _validateTaskMetadata(task, run_metadata, normalized_task_dir.name)
    _validateTaskTree(normalized_task_dir, task)

    result_json = _loadJsonObject(normalized_task_dir / "result.json", "result.json")
    result = _validateResultJson(result_json, task_metadata)
    result_markdown = _readUtf8(normalized_task_dir / "result.md", "result.md")
    page_markdown = _extractPageMarkdown(result_markdown, task_metadata.core_pages)
    marked_pages = tuple(page_markdown)
    if result.covered_pages != marked_pages:
        raise VisualChunkResultError("covered_pages must exactly match result.md page markers")
    _validateStatusRules(result, task_metadata.core_pages)
    return VisualChunkResult(
        schema_version=result.schema_version,
        run_id=result.run_id,
        candidate_sha256=result.candidate_sha256,
        chunk_id=result.chunk_id,
        core_pages=result.core_pages,
        status=result.status,
        covered_pages=result.covered_pages,
        warnings=result.warnings,
        unresolved_issues=result.unresolved_issues,
        failure_code=result.failure_code,
        crop_requests=result.crop_requests,
        page_markdown=page_markdown,
    )


def mergeVisualChunkResults(run_dir: Path) -> str:
    """确定性合并一个运行的全部 completed worker 结果并去除页标记。"""
    normalized_run_dir = _validateRunDir(run_dir)
    merge_plan = _loadMergePlan(normalized_run_dir)
    task_dirs = _collectTaskDirs(normalized_run_dir)
    actual_chunk_ids = {task_dir.name for task_dir in task_dirs}
    if actual_chunk_ids != set(merge_plan):
        raise VisualChunkResultError("task packages must exactly match run.json chunks")
    results = [validateVisualChunkResult(task_dir) for task_dir in task_dirs]
    if not results:
        raise VisualChunkResultError("visual run has no task packages to merge")
    if any(result.status != "completed" for result in results):
        raise VisualChunkResultError("only completed chunk results can be merged")

    page_markdown: dict[int, str] = {}
    for task_dir, result in zip(task_dirs, results, strict=True):
        expected_plan = merge_plan[result.chunk_id]
        task_metadata = _validateTaskMetadata(
            _loadTaskDescription(task_dir / "task.json"),
            _loadRunMetadata(normalized_run_dir),
            task_dir.name,
        )
        if (
            result.core_pages != expected_plan.core_pages
            or task_metadata.context_pages != expected_plan.context_pages
        ):
            raise VisualChunkResultError("task pages do not match run.json chunking_scheme")
        for page_number, markdown in result.page_markdown.items():
            if page_number in page_markdown:
                raise VisualChunkResultError(
                    f"page is covered by more than one chunk: {page_number}"
                )
            page_markdown[page_number] = markdown

    ordered_pages = tuple(sorted(page_markdown))
    expected_pages = tuple(
        page_number
        for chunk_plan in sorted(merge_plan.values(), key=lambda plan: plan.core_pages[0])
        for page_number in chunk_plan.core_pages
    )
    if ordered_pages != expected_pages:
        raise VisualChunkResultError("merged results do not cover the run chunking_scheme exactly")
    return _joinPageMarkdown(page_markdown[page_number] for page_number in ordered_pages)


@dataclass(frozen=True)
class _RunMetadata:
    run_id: str
    candidate_sha256: str


@dataclass(frozen=True)
class _TaskMetadata:
    run_id: str
    candidate_sha256: str
    chunk_id: str
    core_pages: tuple[int, ...]
    context_pages: tuple[int, ...]


@dataclass(frozen=True)
class _ChunkPlan:
    core_pages: tuple[int, ...]
    context_pages: tuple[int, ...]


def _validateRunDir(run_dir: Path) -> Path:
    path = Path(run_dir)
    if isPathReparsePoint(path) or not path.is_dir():
        raise VisualChunkResultError(f"visual run directory is not a regular directory: {path}")
    if path.name == ".visual-runs":
        raise VisualChunkResultError("visual run directory must name one run")
    _requireRegularFile(path / "run.json", "run.json")
    return path.resolve()


def _validateTaskDir(task_dir: Path) -> Path:
    path = Path(task_dir)
    tasks_root = path.parent
    if (
        isPathReparsePoint(path)
        or isPathReparsePoint(tasks_root)
        or not path.is_dir()
        or tasks_root.name != "tasks"
    ):
        raise VisualChunkResultError(
            "task directory must be directly under a regular tasks directory"
        )
    run_dir = path.parent.parent
    _validateRunDir(run_dir)
    _validatePathComponent(path.name, "chunk_id")
    _requireRegularFile(path / "task.json", "task.json")
    return path.resolve()


def _loadRunMetadata(run_dir: Path) -> _RunMetadata:
    data = _loadJsonObject(run_dir / "run.json", "run.json")
    run_id = _validatePathComponent(data.get("run_id"), "run.json run_id")
    if run_id != run_dir.name:
        raise VisualChunkResultError("run.json run_id does not match its directory")
    compatibility = data.get("compatibility")
    if not isinstance(compatibility, dict):
        raise VisualChunkResultError("run.json compatibility must be an object")
    candidate_sha256 = _validateSha256(
        compatibility.get("candidate_sha256"), "run.json compatibility.candidate_sha256"
    )
    return _RunMetadata(run_id=run_id, candidate_sha256=candidate_sha256)


def _loadMergePlan(run_dir: Path) -> dict[str, _ChunkPlan]:
    data = _loadJsonObject(run_dir / "run.json", "run.json")
    chunks = data.get("chunks")
    compatibility = data.get("compatibility")
    if not isinstance(chunks, dict) or not isinstance(compatibility, dict):
        raise VisualChunkResultError("run.json must contain chunks and compatibility objects")
    chunking_scheme = compatibility.get("chunking_scheme")
    if not isinstance(chunking_scheme, dict):
        raise VisualChunkResultError("run.json compatibility.chunking_scheme must be an object")
    page_count = chunking_scheme.get("page_count")
    if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count <= 0:
        raise VisualChunkResultError(
            "run.json chunking_scheme.page_count must be a positive integer"
        )
    scheme_chunks = chunking_scheme.get("chunks")
    if not isinstance(scheme_chunks, list) or not scheme_chunks:
        raise VisualChunkResultError("run.json chunking_scheme.chunks must be a non-empty list")

    plans: dict[str, _ChunkPlan] = {}
    all_core_pages: list[int] = []
    for scheme_chunk in scheme_chunks:
        if not isinstance(scheme_chunk, dict) or set(scheme_chunk) != {
            "chunk_id",
            "core_pages",
            "context_pages",
        }:
            raise VisualChunkResultError("run.json chunking_scheme chunk is invalid")
        chunk_id = _validatePathComponent(scheme_chunk["chunk_id"], "chunking_scheme chunk_id")
        if chunk_id in plans:
            raise VisualChunkResultError("run.json chunking_scheme repeats a chunk_id")
        core_pages = _validatePageSequence(scheme_chunk["core_pages"], "chunking_scheme core_pages")
        context_pages = _validatePageSequence(
            scheme_chunk["context_pages"], "chunking_scheme context_pages", allow_empty=True
        )
        if core_pages != tuple(range(core_pages[0], core_pages[-1] + 1)):
            raise VisualChunkResultError("run.json chunking_scheme core_pages must be continuous")
        if context_pages != tuple(sorted(context_pages)) or set(core_pages) & set(context_pages):
            raise VisualChunkResultError("run.json chunking_scheme context_pages are invalid")
        plans[chunk_id] = _ChunkPlan(core_pages, context_pages)
        all_core_pages.extend(core_pages)

    declared_chunk_ids = {
        _validatePathComponent(chunk_id, "run.json chunk_id") for chunk_id in chunks
    }
    if declared_chunk_ids != set(plans):
        raise VisualChunkResultError(
            "run.json chunks and chunking_scheme must name the same chunks"
        )
    if sorted(all_core_pages) != list(range(1, page_count + 1)):
        raise VisualChunkResultError("run.json chunking_scheme must cover every page exactly once")
    return plans


def _loadTaskDescription(path: Path) -> dict[str, Any]:
    task = _loadJsonObject(path, "task.json")
    output_contract = task.get("output_contract")
    if not isinstance(output_contract, dict):
        raise VisualChunkResultError("task.json output_contract must be an object")
    if output_contract.get("result_schema_version") != RESULT_SCHEMA_VERSION:
        raise VisualChunkResultError("task.json result schema version is unsupported")
    if task.get("allowed_outputs") != ["result.md", "result.json"]:
        raise VisualChunkResultError("task.json allowed_outputs must be result.md and result.json")
    return task


def _validateTaskMetadata(
    task: Mapping[str, Any], run_metadata: _RunMetadata, directory_chunk_id: str
) -> _TaskMetadata:
    run = task.get("run")
    chunk = task.get("chunk")
    if not isinstance(run, dict) or not isinstance(chunk, dict):
        raise VisualChunkResultError("task.json run and chunk must be objects")
    run_id = _validatePathComponent(run.get("run_id"), "task.json run.run_id")
    candidate_sha256 = _validateSha256(
        run.get("candidate_sha256"), "task.json run.candidate_sha256"
    )
    chunk_id = _validatePathComponent(chunk.get("chunk_id"), "task.json chunk.chunk_id")
    core_pages = _validatePageSequence(chunk.get("core_pages"), "task.json chunk.core_pages")
    context_pages = _validatePageSequence(
        chunk.get("context_pages"), "task.json chunk.context_pages", allow_empty=True
    )
    if run_id != run_metadata.run_id or candidate_sha256 != run_metadata.candidate_sha256:
        raise VisualChunkResultError("task.json identity does not match run.json")
    if chunk_id != directory_chunk_id:
        raise VisualChunkResultError("task.json chunk_id does not match its directory")
    if core_pages != tuple(range(core_pages[0], core_pages[-1] + 1)):
        raise VisualChunkResultError("task.json core_pages must be continuous and ascending")
    if context_pages != tuple(sorted(context_pages)):
        raise VisualChunkResultError("task.json context_pages must be ascending")
    if set(core_pages) & set(context_pages):
        raise VisualChunkResultError("task.json context_pages must not overlap core_pages")
    return _TaskMetadata(run_id, candidate_sha256, chunk_id, core_pages, context_pages)


def _validateTaskTree(task_dir: Path, task: Mapping[str, Any]) -> None:
    files, directories = _collectRelativeTree(task_dir)
    inputs = task.get("inputs")
    if not isinstance(inputs, dict):
        raise VisualChunkResultError("task.json inputs must be an object")
    core_inputs = _validateInputPaths(inputs.get("core"), "core")
    context_inputs = _validateInputPaths(inputs.get("context"), "context")
    expected_files = {
        "task.json",
        "candidate-fragment.md",
        "result.md",
        "result.json",
        *core_inputs,
        *context_inputs,
    }
    expected_directories = {"inputs", "inputs/core", "inputs/context"}
    if set(files) != expected_files or directories != expected_directories:
        raise VisualChunkResultError("task package contains an undeclared or missing output path")


def _validateInputPaths(value: Any, section: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise VisualChunkResultError(f"task.json inputs.{section} must be a list")
    expected_prefix = f"inputs/{section}/"
    paths: list[str] = []
    for path in value:
        if not isinstance(path, str) or not path.startswith(expected_prefix):
            raise VisualChunkResultError(f"task.json inputs.{section} contains an invalid path")
        pure_path = Path(path)
        if pure_path.is_absolute() or any(part in {"", ".", ".."} for part in pure_path.parts):
            raise VisualChunkResultError(f"task.json inputs.{section} contains an unsafe path")
        paths.append(path)
    if len(paths) != len(set(paths)):
        raise VisualChunkResultError(f"task.json inputs.{section} contains duplicate paths")
    return tuple(paths)


def _validateResultJson(data: Mapping[str, Any], task: _TaskMetadata) -> VisualChunkResult:
    if set(data) != RESULT_JSON_FIELDS:
        unexpected = sorted(set(data) - RESULT_JSON_FIELDS)
        missing = sorted(RESULT_JSON_FIELDS - set(data))
        raise VisualChunkResultError(
            f"result.json fields must match the contract (missing={missing}, unknown={unexpected})"
        )
    schema_version = data["schema_version"]
    if schema_version != RESULT_SCHEMA_VERSION:
        raise VisualChunkResultError("result.json schema_version is unsupported")
    run_id = _validatePathComponent(data["run_id"], "result.json run_id")
    candidate_sha256 = _validateSha256(data["candidate_sha256"], "result.json candidate_sha256")
    chunk_id = _validatePathComponent(data["chunk_id"], "result.json chunk_id")
    core_pages = _validatePageSequence(data["core_pages"], "result.json core_pages")
    covered_pages = _validatePageSequence(
        data["covered_pages"], "result.json covered_pages", allow_empty=True
    )
    status = data["status"]
    if not isinstance(status, str) or status not in RESULT_STATUSES:
        raise VisualChunkResultError("result.json status is unsupported")
    warnings = _validateTextList(data["warnings"], "result.json warnings")
    unresolved_issues = _validateTextList(
        data["unresolved_issues"], "result.json unresolved_issues"
    )
    failure_code = _validateFailureCode(data["failure_code"])
    crop_requests = _validateCropRequests(data["crop_requests"], task.core_pages)

    if (
        run_id != task.run_id
        or candidate_sha256 != task.candidate_sha256
        or chunk_id != task.chunk_id
        or core_pages != task.core_pages
    ):
        raise VisualChunkResultError("result.json identity does not match task.json")
    if any(page_number not in task.core_pages for page_number in covered_pages):
        raise VisualChunkResultError("result.json covered_pages must stay within core_pages")
    if tuple(sorted(covered_pages, key=task.core_pages.index)) != covered_pages:
        raise VisualChunkResultError("result.json covered_pages must follow core_pages order")
    return VisualChunkResult(
        schema_version=schema_version,
        run_id=run_id,
        candidate_sha256=candidate_sha256,
        chunk_id=chunk_id,
        core_pages=core_pages,
        status=status,
        covered_pages=covered_pages,
        warnings=warnings,
        unresolved_issues=unresolved_issues,
        failure_code=failure_code,
        crop_requests=crop_requests,
        page_markdown={},
    )


def _validateStatusRules(result: VisualChunkResult, core_pages: tuple[int, ...]) -> None:
    if result.crop_requests and not result.warnings:
        raise VisualChunkResultError("crop_requests require at least one warning")
    if result.status == "completed":
        if result.covered_pages != core_pages:
            raise VisualChunkResultError("completed result must cover every core page exactly once")
        if result.unresolved_issues or result.failure_code is not None:
            raise VisualChunkResultError(
                "completed result cannot contain unresolved issues or failure_code"
            )
    elif result.status == "retryable_failure":
        if result.failure_code not in RETRYABLE_FAILURE_CODES:
            raise VisualChunkResultError(
                "retryable_failure must use a stable retryable failure_code"
            )
    elif not result.unresolved_issues:
        raise VisualChunkResultError("blocked result must contain unresolved_issues")


def _validatePageSequence(
    value: Any, field_name: str, *, allow_empty: bool = False
) -> tuple[int, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise VisualChunkResultError(f"{field_name} must be a non-empty list of page numbers")
    pages: list[int] = []
    for page_number in value:
        if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number <= 0:
            raise VisualChunkResultError(f"{field_name} must contain positive integers")
        pages.append(page_number)
    if len(pages) != len(set(pages)):
        raise VisualChunkResultError(f"{field_name} must not repeat pages")
    return tuple(pages)


def _validateTextList(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise VisualChunkResultError(f"{field_name} must be a list of non-empty strings")
    texts: list[str] = []
    for text in value:
        if not isinstance(text, str) or not text.strip():
            raise VisualChunkResultError(f"{field_name} must contain non-empty strings")
        texts.append(text)
    return tuple(texts)


def _validateFailureCode(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 128:
        raise VisualChunkResultError("result.json failure_code must be a string or null")
    return value


def _validateCropRequests(value: Any, core_pages: Sequence[int]) -> tuple[CropRequest, ...]:
    if not isinstance(value, list):
        raise VisualChunkResultError("result.json crop_requests must be a list")
    requests: list[CropRequest] = []
    for request in value:
        if not isinstance(request, dict) or set(request) != {"page", "bbox", "kind"}:
            raise VisualChunkResultError("each crop_request must contain only page, bbox, and kind")
        page = request["page"]
        if isinstance(page, bool) or not isinstance(page, int) or page not in core_pages:
            raise VisualChunkResultError("crop_request page must be one of the core pages")
        kind = request["kind"]
        if not isinstance(kind, str) or kind not in CROP_KINDS:
            raise VisualChunkResultError("crop_request kind is unsupported")
        bbox = request["bbox"]
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise VisualChunkResultError("crop_request bbox must be four normalized coordinates")
        coordinates: list[float] = []
        for coordinate in bbox:
            if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
                raise VisualChunkResultError("crop_request bbox coordinates must be numbers")
            normalized_coordinate = float(coordinate)
            if not math.isfinite(normalized_coordinate) or not 0.0 <= normalized_coordinate <= 1.0:
                raise VisualChunkResultError(
                    "crop_request bbox must stay within normalized page bounds"
                )
            coordinates.append(normalized_coordinate)
        left, top, right, bottom = coordinates
        if left >= right or top >= bottom:
            raise VisualChunkResultError("crop_request bbox must have positive area")
        requests.append(CropRequest(page, (left, top, right, bottom), kind))
    return tuple(requests)


def _extractPageMarkdown(markdown: str, core_pages: Sequence[int]) -> dict[int, str]:
    page_markdown: dict[int, str] = {}
    active_page: int | None = None
    active_lines: list[str] = []
    outside_lines: list[str] = []
    for line in markdown.splitlines(keepends=True):
        start_match = _PAGE_START_PATTERN.fullmatch(line)
        end_match = _PAGE_END_PATTERN.fullmatch(line)
        if start_match:
            if active_page is not None:
                raise VisualChunkResultError("result.md contains a nested page start marker")
            active_page = int(start_match.group(1))
            if active_page in page_markdown:
                raise VisualChunkResultError("result.md repeats a page marker")
            active_lines = []
        elif end_match:
            page_number = int(end_match.group(1))
            if active_page != page_number:
                raise VisualChunkResultError(
                    "result.md page end marker does not match its start marker"
                )
            page_markdown[page_number] = "".join(active_lines)
            active_page = None
            active_lines = []
        elif active_page is None:
            outside_lines.append(line)
        else:
            active_lines.append(line)
    if active_page is not None:
        raise VisualChunkResultError("result.md has an unclosed page marker")
    if any(line.strip() for line in outside_lines):
        raise VisualChunkResultError("result.md contains content outside temporary page markers")

    marked_pages = tuple(page_markdown)
    if any(page_number not in core_pages for page_number in marked_pages):
        raise VisualChunkResultError("result.md contains a context or out-of-range page")
    expected_order = tuple(
        page_number for page_number in core_pages if page_number in page_markdown
    )
    if marked_pages != expected_order:
        raise VisualChunkResultError("result.md page markers must follow core_pages order")
    return page_markdown


def _collectTaskDirs(run_dir: Path) -> list[Path]:
    tasks_root = run_dir / "tasks"
    if isPathReparsePoint(tasks_root) or not tasks_root.is_dir():
        raise VisualChunkResultError("visual run tasks directory is missing or unsafe")
    task_dirs: list[Path] = []
    for entry in sorted(os.scandir(tasks_root), key=lambda item: item.name):
        if isPathReparsePoint(Path(entry.path)) or not entry.is_dir(follow_symlinks=False):
            raise VisualChunkResultError("visual run tasks directory contains an unsafe entry")
        task_dirs.append(Path(entry.path))
    return task_dirs


def _collectRelativeTree(root: Path) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    directories: set[str] = set()
    pending_directories = [root]
    while pending_directories:
        directory = pending_directories.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                entry_path = Path(entry.path)
                relative_path = entry_path.relative_to(root).as_posix()
                if isPathReparsePoint(entry_path):
                    raise VisualChunkResultError(
                        f"task package contains a symbolic link or reparse point: {relative_path}"
                    )
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISREG(mode):
                    files.add(relative_path)
                elif stat.S_ISDIR(mode):
                    directories.add(relative_path)
                    pending_directories.append(entry_path)
                else:
                    raise VisualChunkResultError(
                        f"task package contains a non-regular path: {relative_path}"
                    )
    return files, directories


def _loadJsonObject(path: Path, label: str) -> dict[str, Any]:
    text = _readUtf8(path, label)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VisualChunkResultError(f"{label} is not valid JSON") from exc
    if not isinstance(data, dict):
        raise VisualChunkResultError(f"{label} must be an object")
    return data


def _readUtf8(path: Path, label: str) -> str:
    _requireRegularFile(path, label)
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise VisualChunkResultError(f"{label} must be UTF-8") from exc
    except OSError as exc:
        raise VisualChunkResultError(f"cannot read {label}") from exc


def _requireRegularFile(path: Path, label: str) -> None:
    if isPathReparsePoint(path):
        raise VisualChunkResultError(f"{label} must not be a symbolic link or reparse point")
    try:
        mode = os.stat(path, follow_symlinks=False).st_mode
    except FileNotFoundError as exc:
        raise VisualChunkResultError(f"{label} must be an existing regular file") from exc
    if not stat.S_ISREG(mode):
        raise VisualChunkResultError(f"{label} must be an existing regular file")


def _validatePathComponent(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _PATH_COMPONENT_PATTERN.fullmatch(value) or ".." in value:
        raise VisualChunkResultError(f"{field_name} must be a safe path component")
    return value


def _validateSha256(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise VisualChunkResultError(f"{field_name} must be a SHA256 digest")
    return value.lower()


def _joinPageMarkdown(page_markdown: Sequence[str]) -> str:
    merged = ""
    for markdown in page_markdown:
        if not merged:
            merged = markdown
        elif merged.endswith("\n") or markdown.startswith("\n"):
            merged += markdown
        else:
            merged += "\n" + markdown
    return merged
