"""Host-neutral Boundary Review task packages and result validation.

The module operates only on one completed visual-repair run.  It prepares
run-local review inputs, validates the worker's sole result file, and never
changes run state, Canonical Markdown, or fallback assets.
"""

from __future__ import annotations

# ruff: noqa: N802
import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from paperbase.core.visual_chunk_result import (
    VisualChunkResult,
    VisualChunkResultError,
    mergeVisualChunkResults,
    validateVisualChunkResult,
)
from paperbase.core.visual_repair_run import isPathReparsePoint

BOUNDARY_REVIEW_TASK_SCHEMA_VERSION = "visual-boundary-review-task-v1"
BOUNDARY_REVIEW_RESULT_SCHEMA_VERSION = "visual-boundary-review-result-v1"
BOUNDARY_REVIEW_DIRECTORY = "boundary-review"
BOUNDARY_REVIEW_RESULT_FILE = "result.json"
BOUNDARY_REVIEW_DECISIONS = frozenset({"pass", "rework_required", "blocked"})
BOUNDARY_REVIEW_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "candidate_sha256",
        "decision",
        "checked_item_ids",
        "affected_chunk_ids",
        "unresolved_issues",
        "warnings",
    }
)
_SHA256_HEX = frozenset("0123456789abcdefABCDEF")


class BoundaryReviewError(ValueError):
    """Boundary Review 包或 worker 结果未满足严格契约。"""


@dataclass(frozen=True)
class BoundaryReviewActionRequired:
    """任务包已就绪，等待 Agent Host 把 ``result.json`` 写回。"""

    task_package: Path


@dataclass(frozen=True)
class BoundaryReviewResult:
    """已通过任务包身份、检查项和决策规则验证的 worker 结果。"""

    decision: str
    checked_item_ids: tuple[str, ...]
    affected_chunk_ids: tuple[str, ...]
    unresolved_issues: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ValidatedBoundaryReview:
    """已存在且已校验的 Boundary Review 结果。"""

    task_package: Path
    result: BoundaryReviewResult


@dataclass(frozen=True)
class _RunIdentity:
    run_id: str
    candidate_sha256: str


@dataclass(frozen=True)
class _ChunkPlan:
    chunk_id: str
    core_pages: tuple[int, ...]


@dataclass(frozen=True)
class _BoundaryItem:
    item_id: str
    kind: str
    pages: tuple[int, ...]
    chunk_ids: tuple[str, ...]


def prepareOrValidateBoundaryReview(
    run_dir: Path,
) -> BoundaryReviewActionRequired | ValidatedBoundaryReview:
    """创建或复用一个完成分块结果的 run-local Boundary Review 包。

    没有 ``result.json`` 时返回交接对象；已存在时仅在它匹配当前运行输入和
    严格结果契约后返回已验证对象。所有输入都由 PaperBase 生成并保持只读。
    """
    normalized_run_dir = _validateRunDir(run_dir)
    identity = _loadRunIdentity(normalized_run_dir)
    merged_markdown = _mergeCompletedChunks(normalized_run_dir)
    chunk_results = _loadCompletedChunkResults(normalized_run_dir)
    chunk_plans = tuple(
        _ChunkPlan(result.chunk_id, result.core_pages)
        for result in sorted(chunk_results, key=lambda result: result.core_pages[0])
    )
    attempted_chunk_ids = _loadAttemptedChunkIds(normalized_run_dir, chunk_plans)
    items = _makeBoundaryItems(chunk_plans, attempted_chunk_ids)
    page_markdown = {
        page_number: markdown
        for result in chunk_results
        for page_number, markdown in result.page_markdown.items()
    }
    input_pages = tuple(sorted({page_number for item in items for page_number in item.pages}))
    expected_task = _makeTaskDescription(identity, items, input_pages)
    expected_inputs = _makeExpectedInputs(
        normalized_run_dir, merged_markdown, page_markdown, input_pages
    )
    review_dir = normalized_run_dir / BOUNDARY_REVIEW_DIRECTORY
    _createOrValidateReviewPackage(review_dir, expected_task, expected_inputs)

    result_path = review_dir / BOUNDARY_REVIEW_RESULT_FILE
    if not result_path.exists():
        return BoundaryReviewActionRequired(review_dir)
    result = _validateBoundaryReviewResult(review_dir, identity, items, chunk_plans)
    return ValidatedBoundaryReview(review_dir, result)


def _mergeCompletedChunks(run_dir: Path) -> str:
    try:
        return mergeVisualChunkResults(run_dir)
    except VisualChunkResultError as exc:
        raise BoundaryReviewError("Boundary Review requires a mergeable completed run") from exc


def _loadCompletedChunkResults(run_dir: Path) -> tuple[VisualChunkResult, ...]:
    tasks_root = run_dir / "tasks"
    if isPathReparsePoint(tasks_root) or not tasks_root.is_dir():
        raise BoundaryReviewError("visual run tasks directory is missing or unsafe")
    results: list[VisualChunkResult] = []
    for entry in sorted(os.scandir(tasks_root), key=lambda item: item.name):
        if isPathReparsePoint(Path(entry.path)) or not entry.is_dir(follow_symlinks=False):
            raise BoundaryReviewError("visual run tasks directory contains an unsafe entry")
        try:
            result = validateVisualChunkResult(Path(entry.path))
        except VisualChunkResultError as exc:
            raise BoundaryReviewError(
                "visual worker result cannot prepare Boundary Review"
            ) from exc
        if result.status != "completed":
            raise BoundaryReviewError("Boundary Review requires every chunk to be completed")
        results.append(result)
    if not results:
        raise BoundaryReviewError("visual run has no chunk results")
    return tuple(results)


def _makeBoundaryItems(
    chunk_plans: Sequence[_ChunkPlan], attempted_chunk_ids: frozenset[str]
) -> tuple[_BoundaryItem, ...]:
    if not chunk_plans:
        raise BoundaryReviewError("Boundary Review needs at least one chunk plan")
    first_plan = chunk_plans[0]
    last_plan = chunk_plans[-1]
    items = [
        _BoundaryItem(
            "document-start",
            "document_start",
            (first_plan.core_pages[0],),
            (first_plan.chunk_id,),
        ),
        _BoundaryItem(
            "document-end",
            "document_end",
            (last_plan.core_pages[-1],),
            (last_plan.chunk_id,),
        ),
    ]
    for previous_plan, next_plan in zip(chunk_plans, chunk_plans[1:]):
        items.append(
            _BoundaryItem(
                f"chunk-seam-{previous_plan.chunk_id}-{next_plan.chunk_id}",
                "chunk_seam",
                (previous_plan.core_pages[-1], next_plan.core_pages[0]),
                (previous_plan.chunk_id, next_plan.chunk_id),
            )
        )
    items.extend(
        _BoundaryItem(
            f"chunk-attempt-{plan.chunk_id}",
            "retry_or_rework_chunk",
            plan.core_pages,
            (plan.chunk_id,),
        )
        for plan in chunk_plans
        if plan.chunk_id in attempted_chunk_ids
    )
    items.append(
        _BoundaryItem(
            "reference-tail",
            "reference_tail",
            last_plan.core_pages,
            (last_plan.chunk_id,),
        )
    )
    return tuple(items)


def _loadAttemptedChunkIds(run_dir: Path, chunk_plans: Sequence[_ChunkPlan]) -> frozenset[str]:
    """Return chunks with persisted retry counters or archived rework attempts."""
    data = _loadJsonObject(run_dir / "run.json", "run.json")
    chunks = data.get("chunks")
    if not isinstance(chunks, dict):
        raise BoundaryReviewError("run.json chunks must be an object")
    valid_chunk_ids = {plan.chunk_id for plan in chunk_plans}
    attempted_chunk_ids: set[str] = set()
    for chunk_id in valid_chunk_ids:
        chunk = chunks.get(chunk_id)
        if not isinstance(chunk, dict):
            raise BoundaryReviewError("run.json chunks do not match the completed run")
        retry_count = chunk.get("retry_count", 0)
        if isinstance(retry_count, bool) or not isinstance(retry_count, int) or retry_count < 0:
            raise BoundaryReviewError("run.json chunk retry_count is invalid")
        if retry_count:
            attempted_chunk_ids.add(chunk_id)

    attempts_root = run_dir / "attempts"
    if not attempts_root.exists() and not isPathReparsePoint(attempts_root):
        return frozenset(attempted_chunk_ids)
    if isPathReparsePoint(attempts_root) or not attempts_root.is_dir():
        raise BoundaryReviewError("visual run attempts directory is unsafe")
    for entry in os.scandir(attempts_root):
        chunk_path = Path(entry.path)
        if isPathReparsePoint(chunk_path) or not entry.is_dir(follow_symlinks=False):
            raise BoundaryReviewError("visual run attempts directory contains an unsafe entry")
        if entry.name not in valid_chunk_ids:
            raise BoundaryReviewError("visual run attempts contain an unknown chunk")
        if any(path.name.startswith(("retry-", "rework-")) for path in chunk_path.iterdir()):
            attempted_chunk_ids.add(entry.name)
    return frozenset(attempted_chunk_ids)


def _makeTaskDescription(
    identity: _RunIdentity, items: Sequence[_BoundaryItem], input_pages: Sequence[int]
) -> dict[str, Any]:
    return {
        "schema_version": BOUNDARY_REVIEW_TASK_SCHEMA_VERSION,
        "run": {
            "run_id": identity.run_id,
            "candidate_sha256": identity.candidate_sha256,
        },
        "inputs": {
            "merged_markdown": "merged.md",
            "pages": [
                {
                    "page": page_number,
                    "markdown": _pageMarkdownPath(page_number),
                    "image": _pageImagePath(page_number),
                }
                for page_number in input_pages
            ],
        },
        "items": [
            {
                "item_id": item.item_id,
                "kind": item.kind,
                "pages": list(item.pages),
                "chunk_ids": list(item.chunk_ids),
            }
            for item in items
        ],
        "allowed_outputs": [BOUNDARY_REVIEW_RESULT_FILE],
        "write_boundary": {
            "only_paths": [BOUNDARY_REVIEW_RESULT_FILE],
            "scope": "Write only result.json; all task and input files are read-only.",
        },
        "result_contract": {
            "schema_version": BOUNDARY_REVIEW_RESULT_SCHEMA_VERSION,
            "required_fields": sorted(BOUNDARY_REVIEW_RESULT_FIELDS),
            "decision_values": sorted(BOUNDARY_REVIEW_DECISIONS),
            "field_types": {
                "run_id": "string matching task.run.run_id",
                "candidate_sha256": "64-character SHA-256 string matching task.run.candidate_sha256",
                "checked_item_ids": "array exactly matching task item ids in task order",
                "affected_chunk_ids": "array of task chunk ids",
                "unresolved_issues": "array of non-empty strings",
                "warnings": "array of non-empty strings",
            },
            "rules": [
                "pass has no affected_chunk_ids and no unresolved_issues",
                "rework_required has affected_chunk_ids and unresolved_issues",
                "blocked has unresolved_issues",
            ],
        },
    }


def _makeExpectedInputs(
    run_dir: Path,
    merged_markdown: str,
    page_markdown: Mapping[int, str],
    input_pages: Sequence[int],
) -> dict[str, bytes]:
    inputs = {"merged.md": _encodeUtf8(merged_markdown, "merged Markdown")}
    rendered_root = run_dir / "rendered"
    if isPathReparsePoint(rendered_root) or not rendered_root.is_dir():
        raise BoundaryReviewError("rendered page directory is missing or unsafe")
    for page_number in input_pages:
        if page_number not in page_markdown:
            raise BoundaryReviewError("Boundary Review item lacks page Markdown")
        inputs[_pageMarkdownPath(page_number)] = _encodeUtf8(
            page_markdown[page_number], f"page {page_number} Markdown"
        )
        rendered_path = rendered_root / f"page-{page_number:04d}.png"
        inputs[_pageImagePath(page_number)] = _readRegularBytes(
            rendered_path, f"rendered page {page_number}"
        )
    return inputs


def _createOrValidateReviewPackage(
    review_dir: Path, expected_task: Mapping[str, Any], expected_inputs: Mapping[str, bytes]
) -> None:
    task_bytes = _jsonBytes(expected_task)
    if review_dir.exists() or isPathReparsePoint(review_dir):
        _validateExistingReviewPackage(review_dir, task_bytes, expected_inputs)
        return

    temporary_dir = Path(tempfile.mkdtemp(prefix=".boundary-review.", dir=review_dir.parent))
    try:
        _writeNewBytes(temporary_dir / "task.json", task_bytes)
        for relative_path, content in expected_inputs.items():
            destination = temporary_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            _writeNewBytes(destination, content)
        os.replace(temporary_dir, review_dir)
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise


def _validateExistingReviewPackage(
    review_dir: Path, expected_task: bytes, expected_inputs: Mapping[str, bytes]
) -> None:
    if isPathReparsePoint(review_dir) or not review_dir.is_dir():
        raise BoundaryReviewError("boundary-review path is not a regular directory")
    files, directories = _collectRelativeTree(review_dir)
    expected_files = {"task.json", *expected_inputs}
    allowed_files = expected_files | {BOUNDARY_REVIEW_RESULT_FILE}
    expected_directories = _expectedDirectories(expected_inputs)
    if (
        files - allowed_files
        or not expected_files.issubset(files)
        or directories != expected_directories
    ):
        raise BoundaryReviewError("boundary-review package has an extra, missing, or unsafe path")
    if _readRegularBytes(review_dir / "task.json", "boundary review task") != expected_task:
        raise BoundaryReviewError("boundary-review task does not match current run inputs")
    for relative_path, expected_bytes in expected_inputs.items():
        if _readRegularBytes(review_dir / relative_path, relative_path) != expected_bytes:
            raise BoundaryReviewError(
                "boundary-review input bytes do not match current merged output"
            )
    result_path = review_dir / BOUNDARY_REVIEW_RESULT_FILE
    if result_path.exists():
        _requireRegularFile(result_path, BOUNDARY_REVIEW_RESULT_FILE)


def _validateBoundaryReviewResult(
    review_dir: Path,
    identity: _RunIdentity,
    items: Sequence[_BoundaryItem],
    chunk_plans: Sequence[_ChunkPlan],
) -> BoundaryReviewResult:
    data = _loadJsonObject(review_dir / BOUNDARY_REVIEW_RESULT_FILE, BOUNDARY_REVIEW_RESULT_FILE)
    if set(data) != BOUNDARY_REVIEW_RESULT_FIELDS:
        missing = sorted(BOUNDARY_REVIEW_RESULT_FIELDS - set(data))
        unknown = sorted(set(data) - BOUNDARY_REVIEW_RESULT_FIELDS)
        raise BoundaryReviewError(
            f"Boundary Review result fields must match the contract (missing={missing}, unknown={unknown})"
        )
    if data["schema_version"] != BOUNDARY_REVIEW_RESULT_SCHEMA_VERSION:
        raise BoundaryReviewError("Boundary Review result schema is unsupported")
    if (
        _validatePathComponent(data["run_id"], "result run_id") != identity.run_id
        or _validateSha256(data["candidate_sha256"], "result candidate_sha256")
        != identity.candidate_sha256
    ):
        raise BoundaryReviewError("Boundary Review result identity does not match task")
    decision = data["decision"]
    if not isinstance(decision, str) or decision not in BOUNDARY_REVIEW_DECISIONS:
        raise BoundaryReviewError("Boundary Review result decision is unsupported")

    expected_item_ids = tuple(item.item_id for item in items)
    checked_item_ids = _validateIdentifierList(data["checked_item_ids"], "checked_item_ids")
    if checked_item_ids != expected_item_ids:
        raise BoundaryReviewError("checked_item_ids must exactly match the required task items")
    valid_chunk_ids = {plan.chunk_id for plan in chunk_plans}
    affected_chunk_ids = _validateIdentifierList(
        data["affected_chunk_ids"], "affected_chunk_ids", allow_empty=True
    )
    if any(chunk_id not in valid_chunk_ids for chunk_id in affected_chunk_ids):
        raise BoundaryReviewError("affected_chunk_ids contains a chunk outside this run")
    unresolved_issues = _validateTextList(data["unresolved_issues"], "unresolved_issues")
    warnings = _validateTextList(data["warnings"], "warnings")

    if decision == "pass" and (affected_chunk_ids or unresolved_issues):
        raise BoundaryReviewError("pass result cannot contain affected chunks or unresolved issues")
    if decision == "rework_required" and (not affected_chunk_ids or not unresolved_issues):
        raise BoundaryReviewError("rework_required needs affected chunks and unresolved issues")
    if decision == "blocked" and not unresolved_issues:
        raise BoundaryReviewError("blocked result needs unresolved issues")
    return BoundaryReviewResult(
        decision=decision,
        checked_item_ids=checked_item_ids,
        affected_chunk_ids=affected_chunk_ids,
        unresolved_issues=unresolved_issues,
        warnings=warnings,
    )


def _validateRunDir(run_dir: Path) -> Path:
    path = Path(run_dir)
    if isPathReparsePoint(path) or not path.is_dir() or path.parent.name != ".visual-runs":
        raise BoundaryReviewError("run_dir must be a regular run directly under .visual-runs")
    _requireRegularFile(path / "run.json", "run.json")
    return path.resolve()


def _loadRunIdentity(run_dir: Path) -> _RunIdentity:
    data = _loadJsonObject(run_dir / "run.json", "run.json")
    run_id = _validatePathComponent(data.get("run_id"), "run.json run_id")
    if run_id != run_dir.name:
        raise BoundaryReviewError("run.json run_id does not match its directory")
    compatibility = data.get("compatibility")
    if not isinstance(compatibility, dict):
        raise BoundaryReviewError("run.json compatibility must be an object")
    candidate_sha256 = _validateSha256(
        compatibility.get("candidate_sha256"), "run.json compatibility.candidate_sha256"
    )
    return _RunIdentity(run_id, candidate_sha256)


def _collectRelativeTree(root: Path) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    directories: set[str] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative_path = path.relative_to(root).as_posix()
                if isPathReparsePoint(path):
                    raise BoundaryReviewError(
                        f"boundary-review package contains a symbolic link or reparse point: {relative_path}"
                    )
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISREG(mode):
                    files.add(relative_path)
                elif stat.S_ISDIR(mode):
                    directories.add(relative_path)
                    pending.append(path)
                else:
                    raise BoundaryReviewError(
                        f"boundary-review package contains an unsafe path: {relative_path}"
                    )
    return files, directories


def _expectedDirectories(expected_inputs: Mapping[str, bytes]) -> set[str]:
    directories: set[str] = set()
    for relative_path in expected_inputs:
        parent = Path(relative_path).parent
        while parent != Path("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _pageMarkdownPath(page_number: int) -> str:
    return f"pages/page-{page_number:04d}.md"


def _pageImagePath(page_number: int) -> str:
    return f"rendered/page-{page_number:04d}.png"


def _loadJsonObject(path: Path, label: str) -> dict[str, Any]:
    try:
        text = _readRegularBytes(path, label).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BoundaryReviewError(f"{label} must be UTF-8") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BoundaryReviewError(f"{label} is not valid JSON") from exc
    if not isinstance(data, dict):
        raise BoundaryReviewError(f"{label} must be an object")
    return data


def _readRegularBytes(path: Path, label: str) -> bytes:
    _requireRegularFile(path, label)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise BoundaryReviewError(f"cannot read {label}") from exc


def _requireRegularFile(path: Path, label: str) -> None:
    if isPathReparsePoint(path):
        raise BoundaryReviewError(f"{label} must not be a symbolic link or reparse point")
    try:
        mode = os.stat(path, follow_symlinks=False).st_mode
    except FileNotFoundError as exc:
        raise BoundaryReviewError(f"{label} must be an existing regular file") from exc
    if not stat.S_ISREG(mode):
        raise BoundaryReviewError(f"{label} must be an existing regular file")


def _writeNewBytes(path: Path, content: bytes) -> None:
    with path.open("xb") as output_file:
        output_file.write(content)


def _encodeUtf8(content: str, label: str) -> bytes:
    try:
        return content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise BoundaryReviewError(f"{label} must be UTF-8 encodable") from exc


def _jsonBytes(data: Mapping[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _validatePathComponent(value: Any, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or ".." in value
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in value
        )
    ):
        raise BoundaryReviewError(f"{field_name} must be a safe path component")
    return value


def _validateSha256(value: Any, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in _SHA256_HEX for char in value)
    ):
        raise BoundaryReviewError(f"{field_name} must be a SHA-256 digest")
    return value.lower()


def _validateIdentifierList(
    value: Any, field_name: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise BoundaryReviewError(f"{field_name} must be a list of identifiers")
    identifiers = tuple(_validatePathComponent(item, field_name) for item in value)
    if len(identifiers) != len(set(identifiers)):
        raise BoundaryReviewError(f"{field_name} must not repeat identifiers")
    return identifiers


def _validateTextList(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise BoundaryReviewError(f"{field_name} must be a list of non-empty strings")
    texts: list[str] = []
    for text in value:
        if not isinstance(text, str) or not text.strip():
            raise BoundaryReviewError(f"{field_name} must contain non-empty strings")
        texts.append(text)
    return tuple(texts)
