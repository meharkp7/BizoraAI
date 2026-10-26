"""Supervised local execution of claimed experiment runs."""

import functools
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import ModuleType

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

import bizora
from bizora.adapters.registry import AdapterRegistry, create_default_registry
from bizora.contracts.execution import (
    AdapterExecutionRequest,
    ExecutionErrorCode,
    ExecutionLimits,
    ExecutionResult,
    ExecutionStatus,
    StructuredError,
)
from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.run import (
    ArtifactRecord,
    ExperimentRun,
    MetricRecord,
    RunState,
)
from bizora.core.errors import BizoraError, ErrorCode, ExperimentStateError
from bizora.db.models import ExperimentRunRecord
from bizora.db.repository import (
    claim_experiment_run,
    compare_and_set_run_state,
    experiment_run_from_record,
    get_experiment_run,
    get_graph_revision,
    heartbeat_experiment_run,
    list_claimable_runs,
    save_artifact_record,
    save_metric_record,
)

_resource: ModuleType | None
try:
    import resource as _resource
except ImportError:  # pragma: no cover - platforms without rlimits.
    _resource = None


@dataclass(frozen=True)
class WorkerConfig:
    """Tuning knobs for one local execution worker."""

    worker_id: str
    lease_ttl_seconds: int = 300
    heartbeat_seconds: float = 60.0
    poll_seconds: float = 0.5
    max_runtime_seconds: int | None = None
    soft_rss_mb: int = 4096
    max_output_bytes: int = 1_000_000
    kill_grace_seconds: int = 10

    def __post_init__(self) -> None:
        """Reject unusable worker tuning values."""
        if not self.worker_id:
            raise ValueError("worker_id must be non-empty.")
        if self.lease_ttl_seconds < 1:
            raise ValueError("lease_ttl_seconds must be positive.")
        if self.heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive.")
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive.")
        if self.max_runtime_seconds is not None and not (
            1 <= self.max_runtime_seconds <= 86_400
        ):
            raise ValueError("max_runtime_seconds must be within 1 and 86400.")
        if self.soft_rss_mb < 1:
            raise ValueError("soft_rss_mb must be positive.")
        if self.max_output_bytes < 1024:
            raise ValueError("max_output_bytes must be at least 1024.")
        if self.kill_grace_seconds < 0:
            raise ValueError("kill_grace_seconds must be non-negative.")


class _Outcome(StrEnum):
    COMPLETED = "completed"
    EXITED_BADLY = "exited_badly"
    TIMEOUT = "timeout"
    OUTPUT_OVERFLOW = "output_overflow"
    MEMORY_SOFT_LIMIT = "memory_soft_limit"
    CANCELLED = "cancelled"
    LEASE_LOST = "lease_lost"


@dataclass(frozen=True)
class _SupervisedResult:
    outcome: _Outcome
    exit_code: int | None = None
    signal_number: int | None = None
    observed_rss_mb: int | None = None


def _apply_child_limits(cpu_seconds: int, max_output_bytes: int) -> None:
    """Apply kernel resource limits inside the forked child process."""
    if _resource is None:
        return
    _resource.setrlimit(_resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    _resource.setrlimit(
        _resource.RLIMIT_FSIZE, (max_output_bytes, max_output_bytes)
    )
    _resource.setrlimit(_resource.RLIMIT_CORE, (0, 0))
    _resource.setrlimit(_resource.RLIMIT_NOFILE, (256, 256))


def _read_rss_mb(pid: int) -> int | None:
    """Return a process's resident megabytes, or None when unreadable."""
    try:
        completed = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        return int(completed.stdout.strip()) // 1024
    except ValueError:
        return None


class ExecutionService:
    """Claim runs atomically and supervise allowlisted adapters."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        config: WorkerConfig,
        *,
        registry: AdapterRegistry | None = None,
        argv_factory: Callable[[str, str], list[str]] | None = None,
        rss_reader: Callable[[int], int | None] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._config = config
        self._registry = registry if registry is not None else create_default_registry()
        self._argv_factory = argv_factory
        self._rss_reader = rss_reader if rss_reader is not None else _read_rss_mb

    @contextmanager
    def _session(self) -> Iterator[Session]:
        """Yield a session that always closes after use."""
        session = self._session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _utcnow() -> datetime:
        """Return the current timezone-aware UTC time."""
        return datetime.now(UTC)

    def _limits_for(self, max_runtime_seconds: int) -> ExecutionLimits:
        """Derive execution limits from config and worker caps."""
        timeout = max_runtime_seconds
        if self._config.max_runtime_seconds is not None:
            timeout = min(timeout, self._config.max_runtime_seconds)
        return ExecutionLimits(
            timeout_seconds=timeout,
            cpu_seconds=timeout,
            soft_rss_mb=self._config.soft_rss_mb,
            max_output_bytes=self._config.max_output_bytes,
            kill_grace_seconds=self._config.kill_grace_seconds,
        )

    @staticmethod
    def _child_env() -> dict[str, str]:
        """Build a minimal child environment without secrets."""
        src_dir = str(Path(bizora.__file__).resolve().parent.parent)
        return {
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": src_dir,
            "PYTHONIOENCODING": "utf-8",
        }

    def _child_argv(self, request_path: str, result_path: str) -> list[str]:
        """Return the child command for one execution."""
        if self._argv_factory is not None:
            return self._argv_factory(request_path, result_path)
        return [
            sys.executable,
            "-m",
            "bizora.adapters.runner",
            request_path,
            result_path,
        ]

    def claim_next_available(self) -> str | None:
        """Claim the oldest pending run; return its id or None."""
        with self._session() as session:
            candidates = [
                record.run_id for record in list_claimable_runs(session, limit=10)
            ]
        for run_id in candidates:
            with self._session() as session:
                claimed = claim_experiment_run(
                    session,
                    run_id=run_id,
                    worker_id=self._config.worker_id,
                    now=self._utcnow(),
                    lease_ttl_seconds=self._config.lease_ttl_seconds,
                )
                if claimed is None:
                    continue
                session.commit()
                return run_id
        return None

    def _claim_or_adopt(self, run_id: str) -> ExperimentConfig:
        """Claim a pending run or adopt this worker's own claim."""
        with self._session() as session:
            record = get_experiment_run(session, run_id)
            if record is None:
                raise BizoraError(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    "The experiment run does not exist.",
                    details={"run_id": run_id},
                )
            config = ExperimentConfig.model_validate(record.config_snapshot)
            if record.state == RunState.PENDING.value:
                claimed = claim_experiment_run(
                    session,
                    run_id=run_id,
                    worker_id=self._config.worker_id,
                    now=self._utcnow(),
                    lease_ttl_seconds=self._config.lease_ttl_seconds,
                )
                if claimed is None:
                    raise BizoraError(
                        ErrorCode.RESOURCE_CONFLICT,
                        f"Run '{run_id}' was claimed concurrently.",
                        details={"run_id": run_id},
                    )
                session.commit()
                return config
            if (
                record.state == RunState.RUNNING.value
                and record.worker_id == self._config.worker_id
            ):
                return config
            raise ExperimentStateError(
                f"Run '{run_id}' is '{record.state}' and cannot be executed.",
                details={"run_id": run_id, "state": record.state},
            )

    def _cas_terminal(
        self,
        session: Session,
        run_id: str,
        *,
        to_state: RunState,
        error: str | None,
    ) -> ExperimentRunRecord | None:
        """Attempt the terminal compare-and-set in an open session."""
        return compare_and_set_run_state(
            session,
            run_id=run_id,
            expected_state=RunState.RUNNING,
            new_state=to_state,
            now=self._utcnow(),
            error=error,
        )

    def _resolve_finalize_race(
        self, session: Session, run_id: str
    ) -> ExperimentRun:
        """Return the cancelled run or report a conflicting finalize race."""
        current = get_experiment_run(session, run_id)
        if current is not None and current.state == RunState.CANCELLED.value:
            return experiment_run_from_record(current)
        raise BizoraError(
            ErrorCode.RESOURCE_CONFLICT,
            f"Run '{run_id}' changed while finalizing.",
            details={"run_id": run_id},
        )

    def _finalize(
        self,
        run_id: str,
        *,
        to_state: RunState,
        error: str | None,
    ) -> ExperimentRun:
        """Move a running run to a terminal state without overwriting cancel."""
        with self._session() as session:
            record = self._cas_terminal(
                session, run_id, to_state=to_state, error=error
            )
            if record is None:
                return self._resolve_finalize_race(session, run_id)
            session.commit()
            return experiment_run_from_record(record)

    def _succeed_with_results(
        self, run_id: str, result: ExecutionResult
    ) -> ExperimentRun:
        """Persist adapter-reported results and finalize as succeeded."""
        with self._session() as session:
            record = self._cas_terminal(
                session, run_id, to_state=RunState.SUCCEEDED, error=None
            )
            if record is None:
                return self._resolve_finalize_race(session, run_id)
            for metric in result.metrics:
                save_metric_record(
                    session,
                    MetricRecord(
                        metric_id=metric.metric_id,
                        run_id=run_id,
                        name=metric.name,
                        value=metric.value,
                        result_kind=metric.result_kind,
                    ),
                )
            for artifact in result.artifacts:
                save_artifact_record(
                    session,
                    ArtifactRecord(
                        artifact_id=artifact.artifact_id,
                        run_id=run_id,
                        kind=artifact.kind,
                        uri=artifact.uri,
                        sha256=artifact.sha256,
                        result_kind=artifact.result_kind,
                    ),
                )
            session.commit()
            return experiment_run_from_record(record)

    def _fail(
        self,
        run_id: str,
        code: ExecutionErrorCode,
        message: str,
    ) -> ExperimentRun:
        """Finalize a claimed run as failed with a structured error."""
        error = StructuredError(code=code, message=message[:2000])
        return self._finalize(
            run_id, to_state=RunState.FAILED, error=error.to_record_value()
        )

    def execute_run(self, run_id: str) -> ExperimentRun:
        """Claim, validate, supervise, and finalize one run."""
        config = self._claim_or_adopt(run_id)
        with self._session() as session:
            graph_record = get_graph_revision(
                session,
                project_id=config.project_id,
                graph_id=config.graph_id,
                version=config.graph_version,
            )
            graph_payload = (
                dict(graph_record.graph_payload) if graph_record is not None else None
            )
        if graph_payload is None:
            return self._fail(
                run_id,
                ExecutionErrorCode.GRAPH_MISMATCH,
                f"Graph revision '{config.graph_id}' version "
                f"{config.graph_version} no longer exists.",
            )
        graph = MethodologyGraph.model_validate(graph_payload)
        limits = self._limits_for(config.max_runtime_seconds)
        try:
            request = AdapterExecutionRequest(
                run_id=run_id,
                config=config,
                graph=graph,
                limits=limits,
            )
        except ValidationError as exc:
            return self._fail(
                run_id, ExecutionErrorCode.GRAPH_MISMATCH, str(exc)[:2000]
            )
        try:
            adapter = self._registry.resolve(
                config.adapter_id, config.adapter_version
            )
        except BizoraError as exc:
            return self._fail(
                run_id, ExecutionErrorCode.ADAPTER_UNKNOWN, str(exc)[:2000]
            )
        reasons = adapter.check_compatibility(config, graph)
        if reasons:
            return self._fail(
                run_id,
                ExecutionErrorCode.ADAPTER_INCOMPATIBLE,
                "; ".join(reasons)[:2000],
            )
        return self._spawn_and_supervise(run_id, request)

    def _spawn_and_supervise(
        self, run_id: str, request: AdapterExecutionRequest
    ) -> ExperimentRun:
        """Run the adapter child and record its supervised outcome."""
        with tempfile.TemporaryDirectory(prefix=f"bizora-{run_id}-") as workspace:
            request_path = str(Path(workspace) / "request.json")
            result_path = str(Path(workspace) / "result.json")
            stdout_path = str(Path(workspace) / "stdout.log")
            stderr_path = str(Path(workspace) / "stderr.log")
            Path(request_path).write_text(
                request.model_dump_json(), encoding="utf-8"
            )
            with (
                open(stdout_path, "wb") as stdout_handle,
                open(stderr_path, "wb") as stderr_handle,
            ):
                try:
                    process = subprocess.Popen(
                        self._child_argv(request_path, result_path),
                        stdin=subprocess.DEVNULL,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                        env=self._child_env(),
                        cwd=workspace,
                        start_new_session=True,
                        preexec_fn=functools.partial(
                            _apply_child_limits,
                            request.limits.cpu_seconds,
                            request.limits.max_output_bytes,
                        ),
                    )
                except OSError as exc:
                    return self._fail(
                        run_id,
                        ExecutionErrorCode.ADAPTER_FAILED,
                        f"Failed to spawn adapter process: {exc}",
                    )
                try:
                    supervised = self._supervise(
                        process,
                        run_id=run_id,
                        workspace=workspace,
                        limits=request.limits,
                    )
                finally:
                    self._terminate(process)
            return self._record_outcome(
                run_id, request, supervised, result_path, stderr_path
            )

    def _terminate(self, process: "subprocess.Popen[bytes]") -> int | None:
        """Ensure a child process and its group are dead; return its code."""
        if process.poll() is not None:
            return process.returncode
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                return process.poll()
            try:
                return process.wait(timeout=self._config.kill_grace_seconds)
            except subprocess.TimeoutExpired:
                pass
            with suppress(ProcessLookupError, PermissionError):
                os.killpg(process.pid, signal.SIGKILL)
            return process.wait()
        process.terminate()
        try:
            return process.wait(timeout=self._config.kill_grace_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait()

    def _read_state(self, run_id: str) -> RunState | None:
        """Read one run's state without ORM identity-map caching."""
        with self._session() as session:
            value = session.connection().execute(
                select(ExperimentRunRecord.state).where(
                    ExperimentRunRecord.run_id == run_id
                )
            ).scalar()
        return RunState(value) if value is not None else None

    def _heartbeat(self, run_id: str) -> bool:
        """Extend this worker's lease; report whether ownership held."""
        with self._session() as session:
            record = heartbeat_experiment_run(
                session,
                run_id=run_id,
                worker_id=self._config.worker_id,
                now=self._utcnow(),
                lease_ttl_seconds=self._config.lease_ttl_seconds,
            )
            session.commit()
            return record is not None

    @staticmethod
    def _output_size(workspace: str) -> int:
        """Return the combined captured-output size in bytes."""
        total = 0
        for name in ("stdout.log", "stderr.log"):
            try:
                total += Path(workspace, name).stat().st_size
            except OSError:
                continue
        return total

    def _supervise(
        self,
        process: "subprocess.Popen[bytes]",
        *,
        run_id: str,
        workspace: str,
        limits: ExecutionLimits,
    ) -> _SupervisedResult:
        """Watch a child until it exits, overruns, or loses its mandate."""
        deadline = time.monotonic() + limits.timeout_seconds
        last_heartbeat = time.monotonic()
        while True:
            try:
                returncode = process.wait(timeout=self._config.poll_seconds)
            except subprocess.TimeoutExpired:
                pass
            else:
                if returncode == 0:
                    return _SupervisedResult(outcome=_Outcome.COMPLETED)
                if returncode < 0:
                    return _SupervisedResult(
                        outcome=_Outcome.EXITED_BADLY,
                        signal_number=-returncode,
                    )
                return _SupervisedResult(
                    outcome=_Outcome.EXITED_BADLY, exit_code=returncode
                )
            if time.monotonic() >= deadline:
                self._terminate(process)
                return _SupervisedResult(outcome=_Outcome.TIMEOUT)
            if self._output_size(workspace) > limits.max_output_bytes:
                self._terminate(process)
                return _SupervisedResult(outcome=_Outcome.OUTPUT_OVERFLOW)
            rss_mb = self._rss_reader(process.pid)
            if rss_mb is not None and rss_mb > limits.soft_rss_mb:
                self._terminate(process)
                return _SupervisedResult(
                    outcome=_Outcome.MEMORY_SOFT_LIMIT, observed_rss_mb=rss_mb
                )
            state = self._read_state(run_id)
            if state is None:
                self._terminate(process)
                raise BizoraError(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    "The experiment run does not exist.",
                    details={"run_id": run_id},
                )
            if state == RunState.CANCELLED:
                self._terminate(process)
                return _SupervisedResult(outcome=_Outcome.CANCELLED)
            if state != RunState.RUNNING:
                self._terminate(process)
                return _SupervisedResult(outcome=_Outcome.LEASE_LOST)
            if time.monotonic() - last_heartbeat >= self._config.heartbeat_seconds:
                if not self._heartbeat(run_id):
                    self._terminate(process)
                    return _SupervisedResult(outcome=_Outcome.LEASE_LOST)
                last_heartbeat = time.monotonic()

    def _read_result(self, result_path: str, max_bytes: int) -> ExecutionResult:
        """Load and validate an adapter result file."""
        try:
            size = Path(result_path).stat().st_size
        except OSError as exc:
            raise ValueError(f"Result file is missing: {exc}") from exc
        if size > max_bytes:
            raise ValueError("Result file exceeds the output limit.")
        payload = json.loads(Path(result_path).read_text(encoding="utf-8"))
        return ExecutionResult.model_validate(payload)

    @staticmethod
    def _stderr_tail(stderr_path: str, *, limit: int = 500) -> str:
        """Return the bounded tail of captured stderr."""
        try:
            content = Path(stderr_path).read_bytes()
        except OSError:
            return ""
        return content[-limit:].decode("utf-8", errors="replace")

    def _current_run(self, run_id: str) -> ExperimentRun:
        """Return the current persisted view of a run."""
        with self._session() as session:
            record = get_experiment_run(session, run_id)
            if record is None:
                raise BizoraError(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    "The experiment run does not exist.",
                    details={"run_id": run_id},
                )
            return experiment_run_from_record(record)

    def _record_outcome(
        self,
        run_id: str,
        request: AdapterExecutionRequest,
        supervised: _SupervisedResult,
        result_path: str,
        stderr_path: str,
    ) -> ExperimentRun:
        """Map a supervised outcome onto the run lifecycle."""
        if supervised.outcome in (_Outcome.CANCELLED, _Outcome.LEASE_LOST):
            return self._current_run(run_id)
        if supervised.outcome == _Outcome.TIMEOUT:
            return self._fail(
                run_id,
                ExecutionErrorCode.TIMEOUT,
                f"Run exceeded the {request.limits.timeout_seconds}s limit.",
            )
        if supervised.outcome == _Outcome.OUTPUT_OVERFLOW:
            return self._fail(
                run_id,
                ExecutionErrorCode.ADAPTER_FAILED,
                "Adapter exceeded the captured-output limit.",
            )
        if supervised.outcome == _Outcome.MEMORY_SOFT_LIMIT:
            return self._fail(
                run_id,
                ExecutionErrorCode.MEMORY_SOFT_LIMIT,
                f"Adapter exceeded {request.limits.soft_rss_mb}MB "
                f"(observed {supervised.observed_rss_mb}MB).",
            )
        if supervised.outcome == _Outcome.EXITED_BADLY:
            detail = (
                f"signal {supervised.signal_number}"
                if supervised.signal_number is not None
                else f"status {supervised.exit_code}"
            )
            tail = self._stderr_tail(stderr_path)
            message = f"Adapter exited with {detail}."
            if tail.strip():
                message = f"{message} stderr: {tail.strip()}"
            return self._fail(
                run_id, ExecutionErrorCode.ADAPTER_FAILED, message[:2000]
            )
        try:
            result = self._read_result(
                result_path, request.limits.max_output_bytes
            )
        except (OSError, ValueError, ValidationError) as exc:
            return self._fail(
                run_id,
                ExecutionErrorCode.RESULT_INVALID,
                f"Adapter result is unusable: {exc}",
            )
        if result.run_id != run_id:
            return self._fail(
                run_id,
                ExecutionErrorCode.RESULT_INVALID,
                "Adapter returned a result for a different run.",
            )
        if result.status == ExecutionStatus.FAILED:
            # Failed runs record errors, never partial measurements.
            assert result.error is not None  # Guaranteed by the contract.
            return self._finalize(
                run_id,
                to_state=RunState.FAILED,
                error=result.error.to_record_value(),
            )
        return self._succeed_with_results(run_id, result)
