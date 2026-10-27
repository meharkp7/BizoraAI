
"""Repository operations for persistent methodology graph revisions."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bizora.contracts.experiment import ExperimentConfig, ResultKind
from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.run import (
    TERMINAL_STATES,
    ArtifactRecord,
    ExperimentRun,
    MetricRecord,
    RunState,
)
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db.models import (
    ArtifactRecordRow,
    ExperimentRunRecord,
    GraphRevisionRecord,
    MetricRecordRow,
)


def _serialize_graph(graph: MethodologyGraph) -> dict[str, Any]:
    """Return a JSON-compatible snapshot of a validated graph."""
    return graph.model_dump(mode="json")


def _calculate_snapshot_hash(payload: dict[str, Any]) -> str:
    """Calculate a deterministic SHA-256 hash of the serialized snapshot."""
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def save_graph_revision(
    session: Session,
    graph: MethodologyGraph,
) -> GraphRevisionRecord:
    """Stage a graph revision and flush it without committing the transaction."""
    payload = _serialize_graph(graph)

    record = GraphRevisionRecord(
        project_id=graph.project_id,
        graph_id=graph.graph_id,
        version=graph.version,
        parent_version=graph.parent_version,
        title=graph.title,
        schema_version=graph.schema_version,
        created_by=graph.created_by,
        graph_payload=payload,
        snapshot_sha256=_calculate_snapshot_hash(payload),
    )

    session.add(record)

    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise BizoraError(
            ErrorCode.RESOURCE_CONFLICT,
            "The graph revision conflicts with an existing database record.",
            details={
                "project_id": graph.project_id,
                "graph_id": graph.graph_id,
                "version": graph.version,
            },
        ) from exc

    return record


def get_graph_revision(
    session: Session,
    *,
    project_id: str,
    graph_id: str,
    version: int,
) -> GraphRevisionRecord | None:
    """Retrieve one exact graph revision."""
    statement = select(GraphRevisionRecord).where(
        GraphRevisionRecord.project_id == project_id,
        GraphRevisionRecord.graph_id == graph_id,
        GraphRevisionRecord.version == version,
    )
    return session.scalar(statement)


def get_latest_graph_revision(
    session: Session,
    *,
    project_id: str,
    graph_id: str,
) -> GraphRevisionRecord | None:
    """Retrieve the highest persisted version of a graph."""
    statement = (
        select(GraphRevisionRecord)
        .where(
            GraphRevisionRecord.project_id == project_id,
            GraphRevisionRecord.graph_id == graph_id,
        )
        .order_by(GraphRevisionRecord.version.desc())
        .limit(1)
    )
    return session.scalar(statement)


def _ensure_aware(value: datetime) -> datetime:
    """Return a timezone-aware timestamp, assuming UTC when naive."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def experiment_run_from_record(record: ExperimentRunRecord) -> ExperimentRun:
    """Convert a persisted run record into its lifecycle contract."""
    started_at = record.started_at
    finished_at = record.finished_at
    return ExperimentRun(
        run_id=record.run_id,
        config=ExperimentConfig.model_validate(record.config_snapshot),
        state=RunState(record.state),
        created_at=_ensure_aware(record.created_at),
        started_at=_ensure_aware(started_at) if started_at is not None else None,
        finished_at=_ensure_aware(finished_at) if finished_at is not None else None,
        error=record.error,
    )


def save_experiment_run(
    session: Session,
    run: ExperimentRun,
) -> ExperimentRunRecord:
    """Stage an experiment run and flush it without committing the transaction."""
    record = ExperimentRunRecord(
        run_id=run.run_id,
        experiment_id=run.config.experiment_id,
        project_id=run.config.project_id,
        graph_id=run.config.graph_id,
        graph_version=run.config.graph_version,
        state=run.state.value,
        error=run.error,
        config_snapshot=run.config.model_dump(mode="json"),
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )

    session.add(record)

    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise BizoraError(
            ErrorCode.RESOURCE_CONFLICT,
            "The experiment run conflicts with an existing database record.",
            details={"run_id": run.run_id},
        ) from exc

    return record


def get_experiment_run(
    session: Session,
    run_id: str,
) -> ExperimentRunRecord | None:
    """Retrieve one experiment run by its identifier."""
    statement = select(ExperimentRunRecord).where(
        ExperimentRunRecord.run_id == run_id,
    )
    return session.scalar(statement)


def list_experiment_runs(
    session: Session,
    *,
    project_id: str | None = None,
    graph_id: str | None = None,
    limit: int = 50,
) -> list[ExperimentRunRecord]:
    """List runs newest-first, optionally filtered by project and graph."""
    if limit < 1 or limit > 200:
        raise ValueError("limit must be within 1 and 200.")
    statement = select(ExperimentRunRecord).order_by(
        ExperimentRunRecord.created_at.desc()
    )
    if project_id is not None:
        statement = statement.where(
            ExperimentRunRecord.project_id == project_id
        )
    if graph_id is not None:
        statement = statement.where(ExperimentRunRecord.graph_id == graph_id)
    return list(session.scalars(statement.limit(limit)))


def compare_and_set_run_state(
    session: Session,
    *,
    run_id: str,
    expected_state: RunState,
    new_state: RunState,
    now: datetime,
    error: str | None,
) -> ExperimentRunRecord | None:
    """Atomically transition a run only when it is in the expected state.

    Returns the refreshed record on success, or None when no row matched
    because the run is missing or its state changed concurrently.
    """
    values: dict[str, Any] = {"state": new_state.value, "error": error}
    if new_state == RunState.RUNNING:
        values["started_at"] = now
    if new_state in TERMINAL_STATES:
        values["finished_at"] = now

    result = session.connection().execute(
        update(ExperimentRunRecord)
        .where(
            ExperimentRunRecord.run_id == run_id,
            ExperimentRunRecord.state == expected_state.value,
        )
        .values(**values)
    )

    if result.rowcount != 1:
        return None

    session.flush()
    record = get_experiment_run(session, run_id)
    if record is not None:
        # The bulk UPDATE bypasses the identity map, so refresh the
        # instance to avoid returning stale state to the caller.
        session.refresh(record)
    return record


def list_claimable_runs(
    session: Session,
    *,
    limit: int = 10,
) -> list[ExperimentRunRecord]:
    """List pending runs oldest-first for worker polling."""
    if limit < 1:
        raise ValueError("limit must be a positive integer.")
    statement = (
        select(ExperimentRunRecord)
        .where(ExperimentRunRecord.state == RunState.PENDING.value)
        .order_by(ExperimentRunRecord.created_at.asc())
        .limit(limit)
    )
    return list(session.scalars(statement))


def claim_experiment_run(
    session: Session,
    *,
    run_id: str,
    worker_id: str,
    now: datetime,
    lease_ttl_seconds: int,
) -> ExperimentRunRecord | None:
    """Atomically claim a pending run for one worker.

    Returns the refreshed record on success, or None when the run is
    missing or no longer pending. Callers must pass timezone-aware UTC
    timestamps so lease comparisons stay consistent across databases.
    """
    if lease_ttl_seconds < 1:
        raise ValueError("lease_ttl_seconds must be a positive integer.")
    result = session.connection().execute(
        update(ExperimentRunRecord)
        .where(
            ExperimentRunRecord.run_id == run_id,
            ExperimentRunRecord.state == RunState.PENDING.value,
        )
        .values(
            state=RunState.RUNNING.value,
            started_at=now,
            worker_id=worker_id,
            lease_expires_at=now + timedelta(seconds=lease_ttl_seconds),
        )
    )

    if result.rowcount != 1:
        return None

    session.flush()
    record = get_experiment_run(session, run_id)
    if record is not None:
        session.refresh(record)
    return record


def heartbeat_experiment_run(
    session: Session,
    *,
    run_id: str,
    worker_id: str,
    now: datetime,
    lease_ttl_seconds: int,
) -> ExperimentRunRecord | None:
    """Extend the lease only when the worker still owns a running run.

    Returns the refreshed record, or None when the run is missing,
    finished, expired-and-reaped, or owned by another worker.
    """
    if lease_ttl_seconds < 1:
        raise ValueError("lease_ttl_seconds must be a positive integer.")
    result = session.connection().execute(
        update(ExperimentRunRecord)
        .where(
            ExperimentRunRecord.run_id == run_id,
            ExperimentRunRecord.state == RunState.RUNNING.value,
            ExperimentRunRecord.worker_id == worker_id,
        )
        .values(lease_expires_at=now + timedelta(seconds=lease_ttl_seconds))
    )

    if result.rowcount != 1:
        return None

    session.flush()
    record = get_experiment_run(session, run_id)
    if record is not None:
        session.refresh(record)
    return record


def reap_expired_leases(
    session: Session,
    *,
    now: datetime,
    error: str,
) -> int:
    """Fail running runs whose worker lease expired; return the count.

    Runs without a lease are operator-managed and never reaped.
    """
    result = session.connection().execute(
        update(ExperimentRunRecord)
        .where(
            ExperimentRunRecord.state == RunState.RUNNING.value,
            ExperimentRunRecord.lease_expires_at.is_not(None),
            ExperimentRunRecord.lease_expires_at <= now,
        )
        .values(
            state=RunState.FAILED.value,
            finished_at=now,
            error=error,
        )
    )
    session.flush()
    # The bulk UPDATE may touch rows already present in this session.
    session.expire_all()
    return int(result.rowcount or 0)


def metric_record_from_row(row: MetricRecordRow) -> MetricRecord:
    """Convert a persisted metric row into its contract."""
    return MetricRecord(
        metric_id=row.metric_id,
        run_id=row.run_id,
        name=row.name,
        value=row.value,
        result_kind=ResultKind(row.result_kind),
    )


def artifact_record_from_row(row: ArtifactRecordRow) -> ArtifactRecord:
    """Convert a persisted artifact row into its contract."""
    return ArtifactRecord(
        artifact_id=row.artifact_id,
        run_id=row.run_id,
        kind=row.kind,
        uri=row.uri,
        sha256=row.sha256,
        result_kind=ResultKind(row.result_kind),
    )


def save_metric_record(
    session: Session,
    record: MetricRecord,
) -> MetricRecordRow:
    """Stage a metric record and flush it without committing the transaction."""
    row = MetricRecordRow(
        metric_id=record.metric_id,
        run_id=record.run_id,
        name=record.name,
        value=record.value,
        result_kind=record.result_kind.value,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise BizoraError(
            ErrorCode.RESOURCE_CONFLICT,
            "The metric record conflicts with an existing database record.",
            details={"run_id": record.run_id, "metric_id": record.metric_id},
        ) from exc
    return row


def get_metric_record(
    session: Session,
    *,
    run_id: str,
    metric_id: str,
) -> MetricRecordRow | None:
    """Retrieve one metric record by run and metric id."""
    statement = select(MetricRecordRow).where(
        MetricRecordRow.run_id == run_id,
        MetricRecordRow.metric_id == metric_id,
    )
    return session.scalar(statement)


def list_metrics_for_run(
    session: Session,
    run_id: str,
) -> list[MetricRecordRow]:
    """List one run's metric records ordered by name."""
    statement = (
        select(MetricRecordRow)
        .where(MetricRecordRow.run_id == run_id)
        .order_by(MetricRecordRow.name.asc())
    )
    return list(session.scalars(statement))


def save_artifact_record(
    session: Session,
    record: ArtifactRecord,
) -> ArtifactRecordRow:
    """Stage an artifact record and flush it without committing the transaction."""
    row = ArtifactRecordRow(
        artifact_id=record.artifact_id,
        run_id=record.run_id,
        kind=record.kind,
        uri=record.uri,
        sha256=record.sha256,
        result_kind=record.result_kind.value,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise BizoraError(
            ErrorCode.RESOURCE_CONFLICT,
            "The artifact record conflicts with an existing database record.",
            details={"run_id": record.run_id, "artifact_id": record.artifact_id},
        ) from exc
    return row


def get_artifact_record(
    session: Session,
    *,
    run_id: str,
    artifact_id: str,
) -> ArtifactRecordRow | None:
    """Retrieve one artifact record by run and artifact id."""
    statement = select(ArtifactRecordRow).where(
        ArtifactRecordRow.run_id == run_id,
        ArtifactRecordRow.artifact_id == artifact_id,
    )
    return session.scalar(statement)


def list_artifacts_for_run(
    session: Session,
    run_id: str,
) -> list[ArtifactRecordRow]:
    """List one run's artifact records ordered by artifact id."""
    statement = (
        select(ArtifactRecordRow)
        .where(ArtifactRecordRow.run_id == run_id)
        .order_by(ArtifactRecordRow.artifact_id.asc())
    )
    return list(session.scalars(statement))
