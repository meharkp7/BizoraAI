"""Build portable export bundles for graph revisions."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from bizora.contracts.export_bundle import ExportBundle
from bizora.contracts.graph import MethodologyGraph
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.memory import MemoryService
from bizora.db import repository


def build_export_bundle(
    session: Session,
    *,
    project_id: str,
    graph_id: str,
    now: datetime | None = None,
) -> ExportBundle:
    """Bundle the latest revision of a graph with project memory."""
    record = repository.get_latest_graph_revision(
        session, project_id=project_id, graph_id=graph_id
    )
    if record is None:
        raise BizoraError(ErrorCode.RESOURCE_NOT_FOUND, "Graph not found.")
    graph = MethodologyGraph.model_validate(record.graph_payload)
    moment = now.astimezone(UTC) if now is not None else datetime.now(UTC)
    if moment.tzinfo is None:
        raise ValueError("Export timestamps must be timezone-aware.")
    facts = MemoryService.list_facts(session, project_id=project_id)
    return ExportBundle(
        exported_at=moment,
        project_id=project_id,
        graph_id=graph_id,
        version=graph.version,
        graph=graph,
        memory=tuple(facts),
    )
