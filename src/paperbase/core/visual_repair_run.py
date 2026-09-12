"""可恢复 Visual Repair Run 的本地文件协议。"""

# ruff: noqa: N802

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

RUN_STATES = frozenset({"prepared", "running", "failed", "ready_to_adopt"})
CHUNK_STATES = frozenset({"pending", "running", "completed", "failed"})
INCOMPLETE_RUN_STATES = frozenset({"prepared", "running", "failed"})
REUSABLE_RUN_STATES = INCOMPLETE_RUN_STATES | frozenset({"ready_to_adopt"})
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
PATH_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class LeaseConflictError(RuntimeError):
    """运行已由其他 Host 占用，或另一个 Host 正在完成原子操作。"""


class InvalidStateTransitionError(ValueError):
    """运行或分块状态迁移不符合状态机。"""


class WorkerPathViolationError(ValueError):
    """worker 声明了不属于自身结果文件的写入路径。"""


Clock = Callable[[], datetime]
TokenFactory = Callable[[], str]
RunIdFactory = Callable[[], str]


@dataclass(frozen=True)
class RunCompatibility:
    """决定一次运行能否续接的唯一兼容键。"""

    source_pdf_sha256: str
    candidate_sha256: str
    template_version: str
    chunking_scheme: Any

    def toDict(self) -> dict[str, Any]:  # noqa: N802
        return {
            "source_pdf_sha256": self.source_pdf_sha256,
            "candidate_sha256": self.candidate_sha256,
            "template_version": self.template_version,
            "chunking_scheme": self.chunking_scheme,
        }

    @classmethod
    def fromDict(cls, data: dict[str, Any]) -> RunCompatibility:  # noqa: N802
        return cls(
            source_pdf_sha256=_validateSha256(data["source_pdf_sha256"], "source_pdf_sha256"),
            candidate_sha256=_validateSha256(data["candidate_sha256"], "candidate_sha256"),
            template_version=_validateNonemptyText(data["template_version"], "template_version"),
            chunking_scheme=_normalizeJsonValue(data["chunking_scheme"], "chunking_scheme"),
        )


@dataclass
class VisualChunk:
    """运行内一个核心页块的最小状态。"""

    state: str = "pending"
    lease_token: str | None = None
    retry_count: int = 0

    def toDict(self) -> dict[str, Any]:  # noqa: N802
        return {
            "state": self.state,
            "lease_token": self.lease_token,
            "retry_count": self.retry_count,
        }

    @classmethod
    def fromDict(cls, data: dict[str, Any]) -> VisualChunk:  # noqa: N802
        state = data["state"]
        if state not in CHUNK_STATES:
            raise ValueError(f"unknown chunk state: {state}")
        lease_token = data.get("lease_token")
        if lease_token is not None and not isinstance(lease_token, str):
            raise ValueError("chunk lease_token must be a string or null")
        retry_count = data.get("retry_count", 0)
        if isinstance(retry_count, bool) or not isinstance(retry_count, int) or retry_count < 0:
            raise ValueError("chunk retry_count must be a non-negative integer")
        return cls(state=state, lease_token=lease_token, retry_count=retry_count)


@dataclass
class VisualRepairRun:
    """仅由 orchestrator 持久化到 ``run.json`` 的运行记录。"""

    run_id: str
    compatibility: RunCompatibility
    state: str
    chunks: dict[str, VisualChunk]
    created_at: str
    updated_at: str

    def toDict(self) -> dict[str, Any]:  # noqa: N802
        return {
            "run_id": self.run_id,
            "compatibility": self.compatibility.toDict(),
            "state": self.state,
            "chunks": {chunk_id: chunk.toDict() for chunk_id, chunk in self.chunks.items()},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def fromDict(cls, data: dict[str, Any]) -> VisualRepairRun:  # noqa: N802
        run_id = _validatePathComponent(data["run_id"], "run_id")
        state = data["state"]
        if state not in RUN_STATES:
            raise ValueError(f"unknown run state: {state}")
        chunks_data = data["chunks"]
        if not isinstance(chunks_data, dict):
            raise ValueError("chunks must be an object")
        chunks = {
            _validatePathComponent(chunk_id, "chunk_id"): VisualChunk.fromDict(chunk_data)
            for chunk_id, chunk_data in chunks_data.items()
            if isinstance(chunk_data, dict)
        }
        if len(chunks) != len(chunks_data):
            raise ValueError("each chunk must be an object")
        return cls(
            run_id=run_id,
            compatibility=RunCompatibility.fromDict(data["compatibility"]),
            state=state,
            chunks=chunks,
            created_at=_validateNonemptyText(data["created_at"], "created_at"),
            updated_at=_validateNonemptyText(data["updated_at"], "updated_at"),
        )


@dataclass(frozen=True)
class RunLease:
    """一个 Host 在有限时间内推进运行的排他凭据。"""

    owner: str
    token: str
    acquired_at: str
    expires_at: str

    def toDict(self) -> dict[str, str]:  # noqa: N802
        return {
            "owner": self.owner,
            "token": self.token,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def fromDict(cls, data: dict[str, Any]) -> RunLease:  # noqa: N802
        return cls(
            owner=_validateNonemptyText(data["owner"], "lease.owner"),
            token=_validateNonemptyText(data["token"], "lease.token"),
            acquired_at=_validateNonemptyText(data["acquired_at"], "lease.acquired_at"),
            expires_at=_validateNonemptyText(data["expires_at"], "lease.expires_at"),
        )

    def isExpired(self, now: datetime) -> bool:  # noqa: N802
        return _parseTimestamp(self.expires_at) <= _coerceUtc(now)


def prepareVisualRun(  # noqa: N802
    paper_dir: Path,
    source_pdf_sha256: str,
    candidate_sha256: str,
    template_version: str,
    chunking_scheme: Any,
    chunk_ids: Sequence[str] = (),
    *,
    model_name: str | None = None,
    clock: Clock | None = None,
    run_id_factory: RunIdFactory | None = None,
) -> VisualRepairRun:
    """复用兼容未完成运行；模型名刻意不参与兼容键或持久化。"""
    del model_name
    clock = clock or _utcNow
    compatibility = RunCompatibility(
        source_pdf_sha256=_validateSha256(source_pdf_sha256, "source_pdf_sha256"),
        candidate_sha256=_validateSha256(candidate_sha256, "candidate_sha256"),
        template_version=_validateNonemptyText(template_version, "template_version"),
        chunking_scheme=_normalizeJsonValue(chunking_scheme, "chunking_scheme"),
    )
    normalized_chunk_ids = _validateChunkIds(chunk_ids)
    runs_root = _ensureRunsRoot(paper_dir)

    with _exclusiveFileLock(runs_root / ".operations.lock"):
        for run_dir in sorted(runs_root.iterdir(), key=lambda path: path.name):
            if isPathReparsePoint(run_dir):
                raise ValueError("visual run directory cannot be a symbolic link or reparse point")
            if not run_dir.is_dir() or not (run_dir / "run.json").is_file():
                continue
            run = loadVisualRun(run_dir)
            if run.state in REUSABLE_RUN_STATES and run.compatibility == compatibility:
                return run

        factory = run_id_factory or (lambda: uuid.uuid4().hex)
        for _ in range(5):
            run_id = _validatePathComponent(str(factory()), "run_id")
            run_dir = runs_root / run_id
            try:
                run_dir.mkdir()
            except FileExistsError:
                continue
            break
        else:
            raise RuntimeError("could not create a unique visual repair run directory")

        created_at = _formatTimestamp(_coerceUtc(clock()))
        run = VisualRepairRun(
            run_id=run_id,
            compatibility=compatibility,
            state="prepared",
            chunks={chunk_id: VisualChunk() for chunk_id in normalized_chunk_ids},
            created_at=created_at,
            updated_at=created_at,
        )
        _writeJsonAtomically(run_dir / "run.json", run.toDict())
        return run


def loadVisualRun(run_dir: Path) -> VisualRepairRun:  # noqa: N802
    """读取并验证既有 ``run.json``。"""
    run_dir = _validateRunDirectory(run_dir)
    run_path = run_dir / "run.json"
    data = _readJson(run_path)
    if not isinstance(data, dict):
        raise ValueError("run.json must be an object")
    run = VisualRepairRun.fromDict(data)
    if run.run_id != Path(run_dir).name:
        raise ValueError("run_id does not match its directory")
    return run


def saveVisualRun(  # noqa: N802
    run: VisualRepairRun,
    run_dir: Path,
    lease: RunLease,
    *,
    clock: Clock | None = None,
) -> None:
    """由持有有效 Lease 的 orchestrator 原子保存 ``run.json``。"""
    clock = clock or _utcNow
    run_dir = _validateRunDirectory(run_dir, run.run_id)
    with _exclusiveFileLock(run_dir.parent / ".operations.lock"):
        _assertCurrentLease(run_dir, lease, _coerceUtc(clock()))
        _writeJsonAtomically(run_dir / "run.json", run.toDict())


def acquireRunLease(  # noqa: N802
    run_dir: Path,
    owner: str,
    lease_seconds: int,
    *,
    clock: Clock | None = None,
    token_factory: TokenFactory | None = None,
) -> RunLease:
    """原子取得 Lease；若旧 Lease 已过期，同时恢复其 running 分块。"""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    owner = _validateNonemptyText(owner, "owner")
    clock = clock or _utcNow
    run_dir = _validateRunDirectory(run_dir)
    now = _coerceUtc(clock())

    with _exclusiveFileLock(run_dir.parent / ".operations.lock"):
        current_lease = _loadLease(run_dir)
        if current_lease is not None:
            if not current_lease.isExpired(now):
                raise LeaseConflictError(f"run is leased by {current_lease.owner}")
            run = loadVisualRun(run_dir)
            if _recoverExpiredChunks(run, current_lease, now):
                _writeJsonAtomically(run_dir / "run.json", run.toDict())
            _leasePath(run_dir).unlink()

        token = _validateNonemptyText(
            str((token_factory or (lambda: uuid.uuid4().hex))()), "lease.token"
        )
        lease = RunLease(
            owner=owner,
            token=token,
            acquired_at=_formatTimestamp(now),
            expires_at=_formatTimestamp(now + timedelta(seconds=lease_seconds)),
        )
        _createLease(run_dir, lease)
        return lease


def renewRunLease(  # noqa: N802
    run_dir: Path,
    lease: RunLease,
    lease_seconds: int,
    *,
    clock: Clock | None = None,
) -> RunLease:
    """续期当前 Host 自己仍有效的 Lease。"""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    clock = clock or _utcNow
    run_dir = _validateRunDirectory(run_dir)
    now = _coerceUtc(clock())
    with _exclusiveFileLock(run_dir.parent / ".operations.lock"):
        _assertCurrentLease(run_dir, lease, now)
        renewed = RunLease(
            owner=lease.owner,
            token=lease.token,
            acquired_at=lease.acquired_at,
            expires_at=_formatTimestamp(now + timedelta(seconds=lease_seconds)),
        )
        _writeJsonAtomically(_leasePath(run_dir), renewed.toDict())
        return renewed


def releaseRunLease(run_dir: Path, lease: RunLease) -> None:  # noqa: N802
    """释放当前 Host 自己的 Lease，不自动清理运行目录。"""
    run_dir = _validateRunDirectory(run_dir)
    with _exclusiveFileLock(run_dir.parent / ".operations.lock"):
        current_lease = _loadLease(run_dir)
        if current_lease is None or current_lease != lease:
            raise LeaseConflictError("lease is no longer owned by this host")
        _leasePath(run_dir).unlink()


def recoverExpiredRun(  # noqa: N802
    run_dir: Path,
    *,
    clock: Clock | None = None,
) -> VisualRepairRun:
    """仅在 Lease 已过期时将其 running 分块退回 pending。"""
    clock = clock or _utcNow
    run_dir = _validateRunDirectory(run_dir)
    now = _coerceUtc(clock())
    with _exclusiveFileLock(run_dir.parent / ".operations.lock"):
        lease = _loadLease(run_dir)
        if lease is None:
            return loadVisualRun(run_dir)
        if not lease.isExpired(now):
            raise LeaseConflictError("cannot recover while the lease is still valid")
        run = loadVisualRun(run_dir)
        if _recoverExpiredChunks(run, lease, now):
            _writeJsonAtomically(run_dir / "run.json", run.toDict())
        return run


def transitionRunState(  # noqa: N802
    run: VisualRepairRun,
    target_state: str,
    *,
    clock: Clock | None = None,
) -> None:
    """验证并执行运行状态迁移。"""
    allowed = {
        "prepared": {"running", "failed"},
        "running": {"failed", "ready_to_adopt"},
        "failed": {"running"},
        "ready_to_adopt": set(),
    }
    _transitionState(run.state, target_state, allowed, "run")
    run.state = target_state
    run.updated_at = _formatTimestamp(_coerceUtc((clock or _utcNow)()))


def reworkReadyRunForReReview(  # noqa: N802
    run: VisualRepairRun,
    *,
    clock: Clock | None = None,
) -> None:
    """Re-review 入口的唯一合法出边：作废已消费的 Boundary Review，回到 running。

    仅允许 ``ready_to_adopt -> running``；completed chunk 结果由调用方保留不动，
    供 Boundary Review 对 Agent 返工后的输出重新检查。
    """
    _transitionState(
        run.state,
        "running",
        {"ready_to_adopt": {"running"}},
        "run",
    )
    run.state = "running"
    run.updated_at = _formatTimestamp(_coerceUtc((clock or _utcNow)()))


def transitionChunkState(  # noqa: N802
    run: VisualRepairRun,
    chunk_id: str,
    target_state: str,
    *,
    lease: RunLease | None = None,
    recovery: bool = False,
    rework: bool = False,
    clock: Clock | None = None,
) -> None:
    """验证分块状态迁移；只有恢复流程可将 running 退回 pending。"""
    chunk_id = _validatePathComponent(chunk_id, "chunk_id")
    if chunk_id not in run.chunks:
        raise KeyError(f"unknown chunk_id: {chunk_id}")
    chunk = run.chunks[chunk_id]
    allowed = {
        "pending": {"running"},
        "running": {"completed", "failed"},
        "failed": {"pending"},
        "completed": set(),
    }
    if recovery and rework:
        raise InvalidStateTransitionError("chunk transition cannot be both recovery and rework")
    if recovery and chunk.state == "running" and target_state == "pending":
        if not chunk.lease_token:
            raise InvalidStateTransitionError("running chunk has no lease token")
    elif rework and chunk.state == "completed" and target_state == "pending":
        now = _coerceUtc((clock or _utcNow)())
        if lease is None or lease.isExpired(now):
            raise LeaseConflictError("a valid lease is required to rework a completed chunk")
    else:
        _transitionState(chunk.state, target_state, allowed, "chunk")

    now = _coerceUtc((clock or _utcNow)())
    if target_state == "running":
        if lease is None or lease.isExpired(now):
            raise LeaseConflictError("a valid lease is required to start a chunk")
        chunk.lease_token = lease.token
    else:
        chunk.lease_token = None
    chunk.state = target_state
    run.updated_at = _formatTimestamp(now)


def validateWorkerOutputPaths(  # noqa: N802
    run_dir: Path,
    chunk_id: str,
    declared_paths: Sequence[str | Path],
) -> list[Path]:
    """采用前验证 worker 声明：仅允许其目录中的两个结果文件。"""
    run_dir = _validateRunDirectory(run_dir)
    chunk_id = _validatePathComponent(chunk_id, "chunk_id")
    if chunk_id not in loadVisualRun(run_dir).chunks:
        raise KeyError(f"unknown chunk_id: {chunk_id}")
    task_dir = (run_dir / "tasks" / chunk_id).resolve()
    allowed = {task_dir / "result.md", task_dir / "result.json"}
    validated_paths: list[Path] = []
    for declared_path in declared_paths:
        raw_path = Path(declared_path)
        if raw_path.is_absolute() or any(part == ".." for part in raw_path.parts):
            raise WorkerPathViolationError(f"worker output escapes its chunk: {declared_path}")
        resolved_path = (task_dir / raw_path).resolve()
        if resolved_path not in allowed:
            raise WorkerPathViolationError(f"worker output is not permitted: {declared_path}")
        validated_paths.append(resolved_path)
    return validated_paths


def cleanupVisualRun(  # noqa: N802
    paper_dir: Path,
    run_id: str,
    *,
    clock: Clock | None = None,
) -> None:
    """受控删除指定运行；有效 Lease 存在时拒绝删除，且绝不自动调用。"""
    clock = clock or _utcNow
    run_id = _validatePathComponent(run_id, "run_id")
    runs_root = _ensureRunsRoot(paper_dir)
    run_dir = runs_root / run_id
    with _exclusiveFileLock(runs_root / ".operations.lock"):
        run_dir = _validateRunDirectory(run_dir, run_id)
        lease = _loadLease(run_dir)
        if lease is not None and not lease.isExpired(_coerceUtc(clock())):
            raise LeaseConflictError("cannot clean up a run with an active lease")
        shutil.rmtree(run_dir)


def _runsRoot(paper_dir: Path) -> Path:
    return Path(paper_dir) / ".visual-runs"


def _ensureRunsRoot(paper_dir: Path) -> Path:
    runs_root = _runsRoot(paper_dir)
    if isPathReparsePoint(runs_root):
        raise ValueError("visual runs root cannot be a symbolic link or reparse point")
    if runs_root.exists():
        if not runs_root.is_dir():
            raise ValueError("visual runs root must be a directory")
    else:
        runs_root.mkdir(parents=True, exist_ok=True)
    if isPathReparsePoint(runs_root):
        raise ValueError("visual runs root cannot be a symbolic link or reparse point")
    return runs_root


def _validateRunDirectory(run_dir: Path, expected_run_id: str | None = None) -> Path:
    run_dir = Path(run_dir)
    if run_dir.parent.name != ".visual-runs":
        raise ValueError("run directory must be directly under .visual-runs")
    runs_root = _ensureRunsRoot(run_dir.parent.parent)
    run_id = _validatePathComponent(run_dir.name, "run_id")
    if expected_run_id is not None and run_id != expected_run_id:
        raise ValueError("run_id does not match its directory")
    if isPathReparsePoint(run_dir):
        raise ValueError("visual run directory cannot be a symbolic link or reparse point")
    if not run_dir.is_dir() or not (run_dir / "run.json").is_file():
        raise FileNotFoundError(run_dir)
    resolved_root = runs_root.resolve()
    resolved_run_dir = run_dir.resolve()
    if resolved_run_dir.parent != resolved_root:
        raise ValueError("resolved run directory escapes its visual runs root")
    return run_dir


def isPathReparsePoint(path: Path) -> bool:  # noqa: N802
    """Return whether a path is a symlink, junction, or other reparse point."""
    path = Path(path)
    try:
        path_stat = os.lstat(path)
    except FileNotFoundError:
        return False
    if path.is_symlink():
        return True
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if reparse_attribute and getattr(path_stat, "st_file_attributes", 0) & reparse_attribute:
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction and isjunction(path))


def _validatePathComponent(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not PATH_COMPONENT_PATTERN.fullmatch(value) or ".." in value:
        raise ValueError(f"{field_name} must be a safe path component")
    return value


def _validateSha256(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a SHA256 hex digest")
    return value.lower()


def _validateNonemptyText(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _validateChunkIds(chunk_ids: Sequence[str]) -> list[str]:
    normalized_chunk_ids = [_validatePathComponent(chunk_id, "chunk_id") for chunk_id in chunk_ids]
    if len(normalized_chunk_ids) != len(set(normalized_chunk_ids)):
        raise ValueError("chunk_ids must be unique")
    return normalized_chunk_ids


def _normalizeJsonValue(value: Any, field_name: str) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be JSON serializable") from exc


def _utcNow() -> datetime:
    return datetime.now(UTC)


def _coerceUtc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _formatTimestamp(value: datetime) -> str:
    return value.isoformat()


def _parseTimestamp(value: str) -> datetime:
    try:
        return _coerceUtc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 timestamp: {value}") from exc


def _readJson(path: Path) -> Any:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def _writeJsonAtomically(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temp_path = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
        raise


def _leasePath(run_dir: Path) -> Path:
    return run_dir / "lease.json"


def _loadLease(run_dir: Path) -> RunLease | None:
    path = _leasePath(run_dir)
    if not path.exists():
        return None
    data = _readJson(path)
    if not isinstance(data, dict):
        raise ValueError("lease.json must be an object")
    return RunLease.fromDict(data)


def _createLease(run_dir: Path, lease: RunLease) -> None:
    path = _leasePath(run_dir)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as exc:
        raise LeaseConflictError("lease was acquired by another host") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(lease.toDict(), file, ensure_ascii=False, indent=2, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _assertCurrentLease(run_dir: Path, lease: RunLease, now: datetime) -> None:
    current_lease = _loadLease(run_dir)
    if current_lease is None or current_lease != lease or current_lease.isExpired(now):
        raise LeaseConflictError("a matching active lease is required")


def _recoverExpiredChunks(run: VisualRepairRun, lease: RunLease, now: datetime) -> bool:
    recovered = False
    for chunk_id, chunk in run.chunks.items():
        if chunk.state == "running" and chunk.lease_token == lease.token:
            transitionChunkState(run, chunk_id, "pending", recovery=True, clock=lambda: now)
            recovered = True
    return recovered


def _transitionState(
    current_state: str,
    target_state: str,
    allowed_transitions: dict[str, set[str]],
    subject: str,
) -> None:
    if current_state not in allowed_transitions:
        raise InvalidStateTransitionError(f"unknown {subject} state: {current_state}")
    if target_state not in allowed_transitions[current_state]:
        raise InvalidStateTransitionError(
            f"illegal {subject} transition: {current_state} -> {target_state}"
        )


@contextmanager
def _exclusiveFileLock(lock_path: Path) -> Iterator[None]:
    """标准库跨进程字节锁；Windows 走 msvcrt，避免进程内锁假象。"""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\\0")
            lock_file.flush()
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise LeaseConflictError("another host is updating visual runs") from exc
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise LeaseConflictError("another host is updating visual runs") from exc
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
