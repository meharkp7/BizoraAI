"""Application service for visual-only graph layouts."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.layout import GraphLayout
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db.repository import (
    get_graph_layout,
    get_graph_revision,
    layout_from_record,
    save_graph_layout,
)


class LayoutService:
    """Save and retrieve visual-only layouts without touching graph revisions."""

    @staticmethod
    def _current_time(now: datetime | None) -> datetime:
        """Return the supplied clock value or the current UTC time."""
        timestamp = now if now is not None else datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise BizoraError(
                ErrorCode.INVALID_REQUEST,
                "Layout timestamps must be timezone-aware.",
            )
        return timestamp

    @staticmethod
    def _revision_node_ids(
        session: Session,
        layout: GraphLayout,
    ) -> set[str]:
        """Return the referenced revision's node IDs or raise not-found."""
        revision = get_graph_revision(
            session,
            project_id=layout.project_id,
            graph_id=layout.graph_id,
            version=layout.version,
        )
        if revision is None:
            raise BizoraError(
                ErrorCode.RESOURCE_NOT_FOUND,
                "The referenced graph revision does not exist.",
                details={
                    "project_id": layout.project_id,
                    "graph_id": layout.graph_id,
                    "version": layout.version,
                },
            )
        graph = MethodologyGraph.model_validate(revision.graph_payload)
        return {node.id for node in graph.nodes}

    @classmethod
    def save_layout(
        cls,
        session: Session,
        layout: GraphLayout,
        *,
        now: datetime | None = None,
    ) -> GraphLayout:
        """Validate and persist one revision's layout.

        Positions may omit nodes, but must never reference unknown node IDs.
        Saving a layout never creates or alters a graph revision.
        """
        timestamp = cls._current_time(now)

        try:
            known_nodes = cls._revision_node_ids(session, layout)
            unknown = sorted(
                position.node_id
                for position in layout.positions
                if position.node_id not in known_nodes
            )
            if unknown:
                raise BizoraError(
                    ErrorCode.INVALID_REQUEST,
                    "The layout references unknown graph nodes.",
                    details={
                        "unknown_node_ids": unknown,
                        "project_id": layout.project_id,
                        "graph_id": layout.graph_id,
                        "version": layout.version,
                    },
                )

            record = save_graph_layout(session, layout, now=timestamp)
            session.commit()
            return layout_from_record(record)
        except Exception:
            session.rollback()
            raise

    @staticmethod
    def get_layout(
        session: Session,
        *,
        project_id: str,
        graph_id: str,
        version: int,
    ) -> GraphLayout:
        """Return one revision's saved layout."""
        record = get_graph_layout(
            session,
            project_id=project_id,
            graph_id=graph_id,
            version=version,
        )
        if record is None:
            raise BizoraError(
                ErrorCode.RESOURCE_NOT_FOUND,
                "No layout was saved for this graph revision.",
                details={
                    "project_id": project_id,
                    "graph_id": graph_id,
                    "version": version,
                },
            )
        return layout_from_record(record)
