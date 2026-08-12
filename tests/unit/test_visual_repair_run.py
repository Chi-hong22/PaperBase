import multiprocessing
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from paperbase.core.visual_repair_run import (
    InvalidStateTransitionError,
    LeaseConflictError,
    WorkerPathViolationError,
    acquireRunLease,
    cleanupVisualRun,
    loadVisualRun,
    prepareVisualRun,
    saveVisualRun,
    transitionChunkState,
    transitionRunState,
    validateWorkerOutputPaths,
)


def _hold_operations_lock_in_child(run_dir_text, locked_event, release_event, result_queue):
    from paperbase.core.visual_repair_run import _exclusiveFileLock

    run_dir = Path(run_dir_text)
    try:
        with _exclusiveFileLock(run_dir.parent / ".operations.lock"):
            locked_event.set()
            result_queue.put("locked")
            release_event.wait(5)
    except Exception as exc:
        result_queue.put(("error", repr(exc)))


def _attempt_lease_in_child(run_dir_text, owner, result_queue):
    run_dir = Path(run_dir_text)
    try:
        lease = acquireRunLease(run_dir, owner, 30)
    except LeaseConflictError:
        result_queue.put("conflict")
    except Exception as exc:
        result_queue.put(("error", repr(exc)))
    else:
        result_queue.put("acquired")
        from paperbase.core.visual_repair_run import releaseRunLease

        releaseRunLease(run_dir, lease)


class FakeClock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


SOURCE_SHA = "a" * 64
CANDIDATE_SHA = "b" * 64
CHUNKING_SCHEME = {"chunk_pages": 5, "core_pages": [[1, 5]]}


def _prepare(tmp_path, clock, **overrides):
    return prepareVisualRun(
        tmp_path / "paper",
        overrides.get("source_pdf_sha256", SOURCE_SHA),
        overrides.get("candidate_sha256", CANDIDATE_SHA),
        overrides.get("template_version", "visual-v1"),
        overrides.get("chunking_scheme", CHUNKING_SCHEME),
        overrides.get("chunk_ids", ["chunk-001"]),
        model_name=overrides.get("model_name"),
        clock=clock,
        run_id_factory=overrides.get("run_id_factory"),
    )


def _run_dir(tmp_path, run):
    return tmp_path / "paper" / ".visual-runs" / run.run_id


def _make_junction_or_skip(link_path: Path, target_path: Path) -> None:
    target_path.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link_path), str(target_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("Windows junction creation is unavailable in this environment")


def _remove_junction(link_path: Path) -> None:
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "rmdir", str(link_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_compatible_incomplete_run_is_reused_and_incompatible_key_creates_new(tmp_path):
    clock = FakeClock(datetime(2026, 8, 11, tzinfo=UTC))
    first = _prepare(tmp_path, clock, run_id_factory=lambda: "run-one")
    reused = _prepare(tmp_path, clock, run_id_factory=lambda: "run-two")
    different_candidate = _prepare(
        tmp_path,
        clock,
        candidate_sha256="c" * 64,
        run_id_factory=lambda: "run-three",
    )
    different_scheme = _prepare(
        tmp_path,
        clock,
        chunking_scheme={"chunk_pages": 6, "core_pages": [[1, 6]]},
        run_id_factory=lambda: "run-four",
    )

    assert reused.run_id == first.run_id
    assert different_candidate.run_id != first.run_id
    assert different_scheme.run_id != first.run_id
    assert set(first.chunks) == {"chunk-001"}
    assert not (_run_dir(tmp_path, first) / "chunks").exists()


def test_model_change_does_not_change_compatibility_or_persist_model_name(tmp_path):
    clock = FakeClock(datetime(2026, 8, 11, tzinfo=UTC))
    first = _prepare(tmp_path, clock, model_name="model-a", run_id_factory=lambda: "run-one")
    reused = _prepare(tmp_path, clock, model_name="model-b", run_id_factory=lambda: "run-two")

    assert reused.run_id == first.run_id
    assert "model" not in (_run_dir(tmp_path, first) / "run.json").read_text(encoding="utf-8")


def test_prepare_rejects_junctioned_visual_runs_root_without_writing_target(tmp_path):
    """A reparse-point .visual-runs root must not redirect preparation writes."""
    clock = FakeClock(datetime(2026, 8, 11, tzinfo=UTC))
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    junction_path = paper_dir / ".visual-runs"
    external_target = tmp_path / "external-runs"
    _make_junction_or_skip(junction_path, external_target)

    try:
        with pytest.raises(ValueError, match="symbolic link or reparse point"):
            _prepare(tmp_path, clock)
        assert list(external_target.iterdir()) == []
    finally:
        _remove_junction(junction_path)


def test_load_rejects_run_resolved_through_junctioned_visual_runs_root(tmp_path):
    """Existing runs cannot be reached through a substituted .visual-runs root."""
    clock = FakeClock(datetime(2026, 8, 11, tzinfo=UTC))
    external_paper = tmp_path / "external-paper"
    run = prepareVisualRun(
        external_paper,
        SOURCE_SHA,
        CANDIDATE_SHA,
        "visual-v1",
        CHUNKING_SCHEME,
        ["chunk-001"],
        clock=clock,
        run_id_factory=lambda: "run-one",
    )
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    junction_path = paper_dir / ".visual-runs"
    _make_junction_or_skip(junction_path, external_paper / ".visual-runs")

    try:
        with pytest.raises(ValueError, match="symbolic link or reparse point"):
            loadVisualRun(junction_path / run.run_id)
    finally:
        _remove_junction(junction_path)


def test_cleanup_rejects_junctioned_run_without_removing_external_target(tmp_path):
    """Cleanup must not follow a reparse-point run directory into another tree."""
    clock = FakeClock(datetime(2026, 8, 11, tzinfo=UTC))
    external_paper = tmp_path / "external-paper"
    run = prepareVisualRun(
        external_paper,
        SOURCE_SHA,
        CANDIDATE_SHA,
        "visual-v1",
        CHUNKING_SCHEME,
        ["chunk-001"],
        clock=clock,
        run_id_factory=lambda: "run-one",
    )
    paper_dir = tmp_path / "paper"
    runs_root = paper_dir / ".visual-runs"
    runs_root.mkdir(parents=True)
    junction_path = runs_root / run.run_id
    external_run_dir = external_paper / ".visual-runs" / run.run_id
    _make_junction_or_skip(junction_path, external_run_dir)

    try:
        with pytest.raises(ValueError, match="symbolic link or reparse point"):
            cleanupVisualRun(paper_dir, run.run_id, clock=clock)
        assert external_run_dir.is_dir()
    finally:
        _remove_junction(junction_path)


def test_valid_lease_rejects_second_host(tmp_path):
    clock = FakeClock(datetime(2026, 8, 11, tzinfo=UTC))
    run = _prepare(tmp_path, clock)
    acquireRunLease(_run_dir(tmp_path, run), "host-a", 30, clock=clock)

    with pytest.raises(LeaseConflictError):
        acquireRunLease(_run_dir(tmp_path, run), "host-b", 30, clock=clock)


def test_expired_lease_can_be_taken_over_once(tmp_path):
    clock = FakeClock(datetime(2026, 8, 11, tzinfo=UTC))
    run = _prepare(tmp_path, clock)
    first_lease = acquireRunLease(_run_dir(tmp_path, run), "host-a", 10, clock=clock)
    clock.advance(10)

    second_lease = acquireRunLease(_run_dir(tmp_path, run), "host-b", 10, clock=clock)

    assert second_lease.owner == "host-b"
    assert second_lease.token != first_lease.token
    with pytest.raises(LeaseConflictError):
        acquireRunLease(_run_dir(tmp_path, run), "host-c", 10, clock=clock)


@pytest.mark.skipif(os.name != "nt", reason="exercises the Windows msvcrt lock branch")
def test_windows_process_lock_blocks_concurrent_lease_acquisition(tmp_path):
    clock = FakeClock(datetime(2026, 8, 11, tzinfo=UTC))
    run = _prepare(tmp_path, clock)
    run_dir = _run_dir(tmp_path, run)
    context = multiprocessing.get_context("spawn")
    locked_event = context.Event()
    release_event = context.Event()
    holder_results = context.Queue()
    blocked_results = context.Queue()
    resumed_results = context.Queue()
    holder = context.Process(
        target=_hold_operations_lock_in_child,
        args=(str(run_dir), locked_event, release_event, holder_results),
    )
    blocked_host = context.Process(
        target=_attempt_lease_in_child,
        args=(str(run_dir), "host-b", blocked_results),
    )
    resumed_host = context.Process(
        target=_attempt_lease_in_child,
        args=(str(run_dir), "host-c", resumed_results),
    )
    try:
        holder.start()
        assert locked_event.wait(5)
        assert holder_results.get(timeout=5) == "locked"

        blocked_host.start()
        blocked_host.join(5)
        assert blocked_host.exitcode == 0
        assert blocked_results.get(timeout=5) == "conflict"

        release_event.set()
        holder.join(5)
        assert holder.exitcode == 0

        resumed_host.start()
        resumed_host.join(5)
        assert resumed_host.exitcode == 0
        assert resumed_results.get(timeout=5) == "acquired"
    finally:
        release_event.set()
        for process in (holder, blocked_host, resumed_host):
            if process.is_alive():
                process.terminate()
            process.join(5)


def test_takeover_recovers_expired_running_chunks_but_not_completed_chunks(tmp_path):
    clock = FakeClock(datetime(2026, 8, 11, tzinfo=UTC))
    run = _prepare(tmp_path, clock, chunk_ids=["chunk-001", "chunk-002"])
    run_dir = _run_dir(tmp_path, run)
    lease = acquireRunLease(run_dir, "host-a", 10, clock=clock)
    transitionChunkState(run, "chunk-001", "running", lease=lease, clock=clock)
    transitionChunkState(run, "chunk-002", "running", lease=lease, clock=clock)
    transitionChunkState(run, "chunk-002", "completed", clock=clock)
    saveVisualRun(run, run_dir, lease, clock=clock)
    clock.advance(10)

    acquireRunLease(run_dir, "host-b", 10, clock=clock)
    resumed = loadVisualRun(run_dir)

    assert resumed.chunks["chunk-001"].state == "pending"
    assert resumed.chunks["chunk-002"].state == "completed"
    with pytest.raises(InvalidStateTransitionError):
        transitionChunkState(resumed, "chunk-002", "pending", clock=clock)


def test_illegal_run_and_chunk_transitions_are_rejected(tmp_path):
    clock = FakeClock(datetime(2026, 8, 11, tzinfo=UTC))
    run = _prepare(tmp_path, clock)

    with pytest.raises(InvalidStateTransitionError):
        transitionRunState(run, "ready_to_adopt", clock=clock)
    with pytest.raises(InvalidStateTransitionError):
        transitionChunkState(run, "chunk-001", "completed", clock=clock)


@pytest.mark.parametrize(
    "declared_path",
    [
        "candidate.md",
        "run.json",
        "../chunk-002/result.md",
        "../shared/assets.json",
        "chunks/chunk-002/result.md",
    ],
)
def test_worker_output_path_must_stay_within_its_two_result_files(tmp_path, declared_path):
    clock = FakeClock(datetime(2026, 8, 11, tzinfo=UTC))
    run = _prepare(tmp_path, clock, chunk_ids=["chunk-001", "chunk-002"])
    run_dir = _run_dir(tmp_path, run)

    allowed = validateWorkerOutputPaths(run_dir, "chunk-001", ["result.md", "result.json"])
    assert allowed == [
        run_dir / "tasks" / "chunk-001" / "result.md",
        run_dir / "tasks" / "chunk-001" / "result.json",
    ]
    with pytest.raises(WorkerPathViolationError):
        validateWorkerOutputPaths(run_dir, "chunk-001", [declared_path])
