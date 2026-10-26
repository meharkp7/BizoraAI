
"""Repository operations for persistent methodology graph revisions."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.run import TERMINAL_STATES, ExperimentRun, RunState
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db.models import ExperimentRunRecord, GraphRevisionRecord


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
