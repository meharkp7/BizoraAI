
"""Application service for transactional graph revision persistence."""

from pydantic import ValidationError
from sqlalchemy.orm import Session

from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
)
from bizora.core.errors import BizoraError, ErrorCode, GraphValidationError
from bizora.core.graph_service import GraphService
from bizora.db.models import GraphRevisionRecord
from bizora.db.repository import (
    get_latest_graph_revision,
    save_graph_revision,
)


class GraphPersistenceService:
    """Validate, version, and persist methodology graph snapshots."""

    @staticmethod
    def _conflict(message: str, graph: MethodologyGraph) -> BizoraError:
        """Build a consistent conflict error for graph persistence."""
        return BizoraError(
            ErrorCode.RESOURCE_CONFLICT,
            message,
            details={
                "project_id": graph.project_id,
                "graph_id": graph.graph_id,
                "version": graph.version,
            },
        )

    @classmethod
    def create_initial_revision(
        cls,
        session: Session,
        graph: MethodologyGraph,
    ) -> GraphRevisionRecord:
        """Persist the first revision of a graph and commit the transaction."""
        GraphService.validate(graph)

        if graph.version != 1 or graph.parent_version is not None:
            raise GraphValidationError(
                "An initial graph revision must have version 1 "
                "and no parent version."
            )

        try:
            latest = get_latest_graph_revision(
                session,
                project_id=graph.project_id,
                graph_id=graph.graph_id,
            )

            if latest is not None:
                raise cls._conflict(
                    "An initial revision already exists for this graph.",
                    graph,
                )

            record = save_graph_revision(session, graph)
            session.commit()
            return record
        except Exception:
            session.rollback()
            raise

    @classmethod
    def create_revision(
        cls,
        session: Session,
        graph: MethodologyGraph,
        *,
        created_by: str,
        nodes: tuple[GraphNode, ...] | None = None,
        edges: tuple[GraphEdge, ...] | None = None,
        source_ids: tuple[str, ...] | None = None,
        title: str | None = None,
    ) -> GraphRevisionRecord:
        """Create and persist a revision only when the supplied graph is current."""
        GraphService.validate(graph)

        try:
            latest = get_latest_graph_revision(
                session,
                project_id=graph.project_id,
                graph_id=graph.graph_id,
            )

            if latest is None:
                raise cls._conflict(
                    "Cannot revise a graph that has not been persisted.",
                    graph,
                )

            supplied_snapshot = graph.model_dump(mode="json")

            try:
                canonical_latest = MethodologyGraph.model_validate(
                    latest.graph_payload
                ).model_dump(mode="json")
            except ValidationError:
                # Rows that predate the current contract keep the legacy
                # raw comparison instead of failing closed here.
                canonical_latest = latest.graph_payload

            if (
                latest.version != graph.version
                or canonical_latest != supplied_snapshot
            ):
                raise cls._conflict(
                    "The supplied graph is stale; load the latest revision "
                    "before editing.",
                    graph,
                )

            revision = GraphService.create_revision(
                graph,
                created_by=created_by,
                nodes=nodes,
                edges=edges,
                source_ids=source_ids,
                title=title,
            )

            record = save_graph_revision(session, revision)
            session.commit()
            return record
        except Exception:
            session.rollback()
            raise
