
"""Repository operations for persistent methodology graph revisions."""

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bizora.contracts.graph import MethodologyGraph
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db.models import GraphRevisionRecord


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
