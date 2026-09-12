"""Advance a prepared visual-repair run without binding an Agent Host."""

from __future__ import annotations

# ruff: noqa: N802
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from paperbase.core.canonical_adoption_gate import (
    CanonicalAdoptionGateError,
    validateFinalMarkdownHealth,
)
from paperbase.core.visual_adoption import (
    VisualAdoptionError,
    adoptConfirmedVisualWarnings,
)
from paperbase.core.visual_boundary_review import (
    BoundaryReviewActionRequired,
    BoundaryReviewError,
    ValidatedBoundaryReview,
    prepareOrValidateBoundaryReview,
)
from paperbase.core.visual_chunk_result import (
    VisualChunkResultError,
    validateVisualChunkResult,
)
from paperbase.core.visual_conversion import prepareVisualConversion
from paperbase.core.visual_fallback_assets import (
    VisualFallbackAssetsError,
    prepareVisualFallbackAssets,
)
from paperbase.core.visual_repair_run import (
    LeaseConflictError,
    RunLease,
    VisualRepairRun,
    acquireRunLease,
    isPathReparsePoint,
    loadVisualRun,
    releaseRunLease,
    reworkReadyRunForReReview,
    saveVisualRun,
    transitionChunkState,
    transitionRunState,
)

if TYPE_CHECKING:
    from paperbase.config.models import VisualPdfConfig
    from paperbase.core.pdf_conversion import PdfConversionOutcome


ORCHESTRATOR_OWNER = "paperbase-visual-progress"
ORCHESTRATOR_LEASE_SECONDS = 30
ATTEMPTS_DIRECTORY = "attempts"
BOUNDARY_DIRECTORY = "boundary-review"


class _VisualProgressFailure(RuntimeError):  # noqa: N818
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def prepareOrProgressVisualConversion(  # noqa: N802
    source_pdf: Path,
    candidate_markdown: str,
    visual_config: VisualPdfConfig,
    *,
    accept_visual_warnings: bool = False,
    re_review: bool = False,
) -> PdfConversionOutcome:
    """Prepare a compatible run, then advance only validated local state.

    Agent Hosts remain responsible for writing worker results.  This function
    only consumes those files under a short lease and returns the next unified
    conversion outcome.  With ``re_review`` a ``ready_to_adopt`` run drops its
    stale Boundary Review package and re-enters the normal progression without
    resetting its completed chunk results.
    """
    from paperbase.core.pdf_conversion import (
        AgentActionRequiredOutcome,
        NeedsConfirmationOutcome,
    )

    try:
        run_dir = prepareVisualConversion(source_pdf, candidate_markdown, visual_config)
        run = loadVisualRun(run_dir)
    except Exception:
        return _failedOutcome(
            "visual_preparation_failed",
            "could not prepare visual conversion task package",
        )

    if run.state == "ready_to_adopt":
        if not re_review:
            return _confirmWarningsIfRequested(
                run_dir,
                _readyRunOutcome(run_dir),
                accept_visual_warnings,
            )
        reset_outcome = _resetReadyRunForReReview(run, run_dir)
        if reset_outcome is not None:
            return reset_outcome
    elif re_review:
        return _failedOutcome(
            "visual_re_review_invalid",
            "visual re-review requires a ready_to_adopt run; "
            "remove --re-review and re-run ingest to progress the run normally",
        )

    try:
        lease = acquireRunLease(
            run_dir,
            ORCHESTRATOR_OWNER,
            ORCHESTRATOR_LEASE_SECONDS,
        )
    except LeaseConflictError:
        return AgentActionRequiredOutcome(task_package=run_dir)
    except Exception:
        return _failedOutcome(
            "visual_progress_failed",
            "could not acquire visual conversion progress lease",
        )

    lease_released = False
    try:
        run = loadVisualRun(run_dir)
        outcome = _advanceRun(run, run_dir, lease, visual_config)
    except _VisualProgressFailure as exc:
        outcome = _failRun(run, run_dir, lease, exc.code, exc.message)
    except Exception:
        outcome = _failRun(
            run,
            run_dir,
            lease,
            "visual_progress_failed",
            "could not progress visual conversion task package",
        )
    finally:
        try:
            releaseRunLease(run_dir, lease)
        except Exception:
            pass
        else:
            lease_released = True
    if (
        accept_visual_warnings
        and isinstance(outcome, NeedsConfirmationOutcome)
        and not lease_released
    ):
        return _failedOutcome(
            "visual_warning_adoption_failed",
            "could not release visual conversion progress lease before warning adoption",
        )
    return _confirmWarningsIfRequested(run_dir, outcome, accept_visual_warnings)


def _resetReadyRunForReReview(
    run: VisualRepairRun,
    run_dir: Path,
) -> PdfConversionOutcome | None:
    """Roll a ready_to_adopt run back to running for a fresh Boundary Review.

    Completed chunk results are intentionally kept untouched.  The rollback
    goes through the single legal ``ready_to_adopt -> running`` transition in
    the run state machine, under the orchestrator lease.
    """
    from paperbase.core.pdf_conversion import AgentActionRequiredOutcome

    try:
        lease = acquireRunLease(run_dir, ORCHESTRATOR_OWNER, ORCHESTRATOR_LEASE_SECONDS)
    except LeaseConflictError:
        return AgentActionRequiredOutcome(task_package=run_dir)
    except Exception:
        return _failedOutcome(
            "visual_progress_failed",
            "could not acquire visual conversion progress lease",
        )
    try:
        reworkReadyRunForReReview(run)
        _removeRunLocalDirectory(run_dir / BOUNDARY_DIRECTORY, "Boundary Review package")
        _removeRunLocalDirectory(run_dir / "fallback-assets", "fallback assets")
        saveVisualRun(run, run_dir, lease)
    except _VisualProgressFailure as exc:
        return _failedOutcome(exc.code, exc.message)
    except Exception:
        return _failedOutcome(
            "visual_progress_failed",
            "could not reset the ready_to_adopt visual run for re-review",
        )
    finally:
        try:
            releaseRunLease(run_dir, lease)
        except Exception:
            pass
    return None


def _advanceRun(
    run: VisualRepairRun,
    run_dir: Path,
    lease: RunLease,
    visual_config: VisualPdfConfig,
) -> PdfConversionOutcome:
    from paperbase.core.pdf_conversion import AgentActionRequiredOutcome

    if run.state in {"prepared", "failed"}:
        transitionRunState(run, "running")

    chunk_outcome = _advanceChunks(run, run_dir, lease, visual_config.retry)
    if chunk_outcome is not None:
        saveVisualRun(run, run_dir, lease)
        return chunk_outcome

    try:
        boundary = prepareOrValidateBoundaryReview(run_dir)
    except BoundaryReviewError as exc:
        raise _VisualProgressFailure(
            "visual_boundary_review_invalid",
            "visual Boundary Review result is invalid",
        ) from exc
    if isinstance(boundary, BoundaryReviewActionRequired):
        saveVisualRun(run, run_dir, lease)
        return AgentActionRequiredOutcome(task_package=boundary.task_package)

    if boundary.result.decision == "blocked":
        raise _VisualProgressFailure(
            "visual_quality_blocked",
            "visual quality review blocked automatic adoption",
        )
    if boundary.result.decision == "rework_required":
        _reworkAffectedChunks(run, run_dir, lease, boundary)
        saveVisualRun(run, run_dir, lease)
        return AgentActionRequiredOutcome(task_package=run_dir)
    if boundary.result.decision != "pass":
        raise _VisualProgressFailure(
            "visual_boundary_review_invalid",
            "visual Boundary Review result is invalid",
        )

    try:
        outcome = _passOutcome(run_dir, boundary)
    except (BoundaryReviewError, VisualChunkResultError) as exc:
        raise _VisualProgressFailure(
            "visual_boundary_review_invalid",
            "visual Boundary Review result is invalid",
        ) from exc
    except VisualFallbackAssetsError as exc:
        raise _VisualProgressFailure(
            "visual_quality_blocked",
            f"visual fallback assets cannot satisfy the quality gate: {exc}",
        ) from exc
    transitionRunState(run, "ready_to_adopt")
    saveVisualRun(run, run_dir, lease)
    return outcome


def _advanceChunks(
    run: VisualRepairRun,
    run_dir: Path,
    lease: RunLease,
    retry_limit: int,
) -> PdfConversionOutcome | None:
    from paperbase.core.pdf_conversion import AgentActionRequiredOutcome

    missing_result = False
    for chunk_id in sorted(run.chunks):
        task_dir = run_dir / "tasks" / chunk_id
        result_state = _workerResultState(task_dir)
        chunk = run.chunks[chunk_id]
        if result_state == "missing":
            if chunk.state == "completed":
                raise _VisualProgressFailure(
                    "visual_worker_result_invalid",
                    "visual worker result files do not match the run state",
                )
            missing_result = True
            continue
        if result_state == "partial":
            raise _VisualProgressFailure(
                "visual_worker_result_invalid",
                "visual worker result files must be both present or both absent",
            )

        try:
            result = validateVisualChunkResult(task_dir)
        except (VisualChunkResultError, OSError) as exc:
            raise _VisualProgressFailure(
                "visual_worker_result_invalid",
                "visual worker result is invalid",
            ) from exc

        if result.status == "blocked":
            raise _VisualProgressFailure(
                "visual_quality_blocked",
                "visual worker reported unresolved quality issues",
            )
        if result.status == "retryable_failure":
            if chunk.state == "completed" or chunk.retry_count >= retry_limit:
                raise _VisualProgressFailure(
                    "visual_transient_failure_exhausted",
                    "visual worker transient failure retry limit is exhausted",
                )
            _archiveWorkerOutputs(run_dir, chunk_id, "retry")
            _markChunkFailed(run, chunk_id, lease)
            chunk.retry_count += 1
            transitionChunkState(run, chunk_id, "pending", lease=lease)
            return AgentActionRequiredOutcome(task_package=run_dir)

        if result.status != "completed":
            raise _VisualProgressFailure(
                "visual_worker_result_invalid",
                "visual worker result status is invalid",
            )
        _markChunkCompleted(run, chunk_id, lease)

    if missing_result:
        return AgentActionRequiredOutcome(task_package=run_dir)
    return None


def _markChunkCompleted(run: VisualRepairRun, chunk_id: str, lease: RunLease) -> None:
    chunk = run.chunks[chunk_id]
    if chunk.state == "completed":
        return
    if chunk.state == "failed":
        transitionChunkState(run, chunk_id, "pending", lease=lease)
    if chunk.state == "pending":
        transitionChunkState(run, chunk_id, "running", lease=lease)
    if run.chunks[chunk_id].state != "running":
        raise _VisualProgressFailure(
            "visual_worker_result_invalid",
            "visual worker result cannot complete the current chunk state",
        )
    transitionChunkState(run, chunk_id, "completed", lease=lease)


def _markChunkFailed(run: VisualRepairRun, chunk_id: str, lease: RunLease) -> None:
    chunk = run.chunks[chunk_id]
    if chunk.state == "pending":
        transitionChunkState(run, chunk_id, "running", lease=lease)
    if run.chunks[chunk_id].state != "running":
        raise _VisualProgressFailure(
            "visual_worker_result_invalid",
            "visual worker result cannot fail the current chunk state",
        )
    transitionChunkState(run, chunk_id, "failed", lease=lease)


def _workerResultState(task_dir: Path) -> str:
    if isPathReparsePoint(task_dir) or not task_dir.is_dir():
        raise _VisualProgressFailure(
            "visual_worker_result_invalid",
            "visual worker task package is invalid",
        )
    result_paths = (task_dir / "result.md", task_dir / "result.json")
    presence = tuple(path.exists() or isPathReparsePoint(path) for path in result_paths)
    if not any(presence):
        return "missing"
    if not all(presence) or any(not _isRegularFile(path) for path in result_paths):
        return "partial"
    return "complete"


def _archiveWorkerOutputs(run_dir: Path, chunk_id: str, reason: str) -> None:
    task_dir = run_dir / "tasks" / chunk_id
    result_paths = (task_dir / "result.md", task_dir / "result.json")
    if any(not _isRegularFile(path) for path in result_paths):
        raise _VisualProgressFailure(
            "visual_worker_result_invalid",
            "visual worker result files cannot be archived",
        )
    attempts_parent = run_dir / ATTEMPTS_DIRECTORY
    attempts_root = attempts_parent / chunk_id
    _ensureRegularDirectory(attempts_parent, "visual attempts directory")
    _ensureRegularDirectory(attempts_root, "visual chunk attempts directory")
    attempt_dir = _nextAttemptDirectory(attempts_root, reason)
    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{reason}-", dir=attempts_root))
    published = False
    try:
        for result_path in result_paths:
            copied_path = temporary_dir / result_path.name
            shutil.copyfile(result_path, copied_path)
            if copied_path.read_bytes() != result_path.read_bytes():
                raise OSError("copied visual worker result does not match its source")
        os.replace(temporary_dir, attempt_dir)
        published = True
        for result_path in result_paths:
            result_path.unlink()
    except OSError as exc:
        if published:
            _restoreMissingWorkerOutputs(result_paths, attempt_dir)
        raise _VisualProgressFailure(
            "visual_progress_failed",
            "could not archive visual worker result files",
        ) from exc
    finally:
        if not published and temporary_dir.exists():
            shutil.rmtree(temporary_dir, ignore_errors=True)


def _restoreMissingWorkerOutputs(result_paths: tuple[Path, Path], attempt_dir: Path) -> None:
    """Restore a complete task pair when deletion failed after publication."""
    try:
        for result_path in result_paths:
            if result_path.exists() or isPathReparsePoint(result_path):
                continue
            archived_path = attempt_dir / result_path.name
            if not _isRegularFile(archived_path):
                return
            shutil.copyfile(archived_path, result_path)
            if result_path.read_bytes() != archived_path.read_bytes():
                result_path.unlink(missing_ok=True)
                return
    except OSError:
        return


def _ensureRegularDirectory(path: Path, label: str) -> None:
    if isPathReparsePoint(path):
        raise _VisualProgressFailure("visual_progress_failed", f"{label} is unsafe")
    if path.exists():
        if not path.is_dir():
            raise _VisualProgressFailure("visual_progress_failed", f"{label} is unsafe")
    else:
        path.mkdir()
    if isPathReparsePoint(path) or not path.is_dir():
        raise _VisualProgressFailure("visual_progress_failed", f"{label} is unsafe")


def _nextAttemptDirectory(attempts_root: Path, reason: str) -> Path:
    for index in range(1, 1000):
        candidate = attempts_root / f"{reason}-{index:03d}"
        if not candidate.exists() and not isPathReparsePoint(candidate):
            return candidate
    raise _VisualProgressFailure("visual_progress_failed", "too many visual worker attempts")


def _reworkAffectedChunks(
    run: VisualRepairRun,
    run_dir: Path,
    lease: RunLease,
    boundary: ValidatedBoundaryReview,
) -> None:
    for chunk_id in boundary.result.affected_chunk_ids:
        if run.chunks[chunk_id].state != "completed":
            raise _VisualProgressFailure(
                "visual_boundary_review_invalid",
                "Boundary Review rework target is not completed",
            )
        _archiveWorkerOutputs(run_dir, chunk_id, "rework")
        transitionChunkState(run, chunk_id, "pending", lease=lease, rework=True)
    _removeRunLocalDirectory(run_dir / BOUNDARY_DIRECTORY, "Boundary Review package")
    _removeRunLocalDirectory(run_dir / "fallback-assets", "fallback assets")


def _passOutcome(run_dir: Path, boundary: ValidatedBoundaryReview) -> PdfConversionOutcome:
    from paperbase.core.pdf_conversion import NeedsConfirmationOutcome, ReadyConversionOutcome

    fallback = prepareVisualFallbackAssets(run_dir)
    try:
        validateFinalMarkdownHealth(fallback.markdown)
    except CanonicalAdoptionGateError as exc:
        raise _VisualProgressFailure("visual_quality_blocked", exc.message) from exc
    warnings = tuple(dict.fromkeys((*boundary.result.warnings, *fallback.warnings)))
    if warnings:
        return NeedsConfirmationOutcome(warnings)
    return ReadyConversionOutcome(
        markdown=fallback.markdown,
        assets=tuple(asset.canonical_relative_path for asset in fallback.assets),
    )


def _confirmWarningsIfRequested(
    run_dir: Path,
    outcome: PdfConversionOutcome,
    accept_visual_warnings: bool,
) -> PdfConversionOutcome:
    """Adopt warning-bearing runs only after the caller's lease is released."""
    from paperbase.core.pdf_conversion import (
        NeedsConfirmationOutcome,
        ReadyConversionOutcome,
    )

    if not accept_visual_warnings or not isinstance(outcome, NeedsConfirmationOutcome):
        return outcome
    try:
        adoption = adoptConfirmedVisualWarnings(run_dir)
    except (VisualAdoptionError, OSError) as exc:
        return _failedOutcome(
            "visual_warning_adoption_failed",
            f"could not adopt confirmed visual conversion warnings: {exc}",
        )
    except Exception as exc:
        return _failedOutcome(
            "visual_warning_adoption_failed",
            f"could not adopt confirmed visual conversion warnings: {exc}",
        )
    return ReadyConversionOutcome(markdown=adoption.markdown, assets=adoption.assets)


def _removeRunLocalDirectory(path: Path, label: str) -> None:
    if not path.exists() and not isPathReparsePoint(path):
        return
    if isPathReparsePoint(path) or not path.is_dir():
        raise _VisualProgressFailure("visual_boundary_review_invalid", f"{label} is unsafe")
    shutil.rmtree(path)


def _readyRunOutcome(run_dir: Path) -> PdfConversionOutcome:
    try:
        boundary = prepareOrValidateBoundaryReview(run_dir)
        if not isinstance(boundary, ValidatedBoundaryReview) or boundary.result.decision != "pass":
            return _failedOutcome(
                "visual_boundary_review_invalid",
                "visual Boundary Review result is invalid",
            )
        return _passOutcome(run_dir, boundary)
    except _VisualProgressFailure as exc:
        return _failedOutcome(exc.code, exc.message)
    except VisualFallbackAssetsError as exc:
        return _failedOutcome(
            "visual_quality_blocked",
            f"visual fallback assets cannot satisfy the quality gate: {exc}",
        )
    except (BoundaryReviewError, VisualChunkResultError, OSError):
        return _failedOutcome(
            "visual_boundary_review_invalid",
            "visual Boundary Review result is invalid",
        )


def _failRun(
    run: VisualRepairRun,
    run_dir: Path,
    lease: RunLease,
    code: str,
    message: str,
) -> PdfConversionOutcome:
    if run.state in {"prepared", "running"}:
        transitionRunState(run, "failed")
        try:
            saveVisualRun(run, run_dir, lease)
        except Exception:
            pass
    return _failedOutcome(code, message)


def _failedOutcome(code: str, message: str) -> PdfConversionOutcome:
    from paperbase.core.pdf_conversion import FailedConversionOutcome, PdfConversionError

    return FailedConversionOutcome(error=PdfConversionError(code=code, message=message))


def _isRegularFile(path: Path) -> bool:
    if isPathReparsePoint(path):
        return False
    try:
        return stat.S_ISREG(os.stat(path, follow_symlinks=False).st_mode)
    except FileNotFoundError:
        return False
