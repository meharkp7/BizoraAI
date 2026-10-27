
"""Application services for validating and versioning methodology graphs."""

from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    validate_graph,
)
from bizora.core.errors import GraphValidationError


class GraphService:
    """Coordinate graph validation and immutable revision creation."""

    @staticmethod
    def validate(
        graph: MethodologyGraph,
        *,
        require_dag: bool = False,
    ) -> None:
        """Raise a domain error when the graph violates structural invariants."""
        errors = validate_graph(graph, require_dag=require_dag)

        if errors:
            raise GraphValidationError(
                "The methodology graph is invalid.",
                details={"errors": errors},
            )

    @classmethod
    def create_revision(
        cls,
        graph: MethodologyGraph,
        *,
        created_by: str,
        nodes: tuple[GraphNode, ...] | None = None,
        edges: tuple[GraphEdge, ...] | None = None,
        source_ids: tuple[str, ...] | None = None,
        title: str | None = None,
        require_dag: bool = False,
    ) -> MethodologyGraph:
        """Create a validated revision with isolated nested node configuration."""
        selected_nodes = nodes if nodes is not None else graph.nodes
        isolated_nodes = tuple(
            node.model_copy(deep=True) for node in selected_nodes
        )

        revision = MethodologyGraph(
            schema_version=graph.schema_version,
            project_id=graph.project_id,
            graph_id=graph.graph_id,
            version=graph.version + 1,
            title=title if title is not None else graph.title,
            source_ids=source_ids if source_ids is not None else graph.source_ids,
            nodes=isolated_nodes,
            edges=tuple(edges) if edges is not None else graph.edges,
            created_by=created_by,
            parent_version=graph.version,
            brief=graph.brief,
        )

        cls.validate(revision, require_dag=require_dag)
        return revision
