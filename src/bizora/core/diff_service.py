"""Deterministic revision-diff computation for methodology graphs."""

from bizora.contracts.diff import (
    ChangedEdge,
    ChangedNode,
    GraphRevisionDiff,
)
from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
)
from bizora.core.errors import BizoraError, ErrorCode


class RevisionDiffService:
    """Compute ordered differences between two graph revisions."""

    @staticmethod
    def diff(
        base: MethodologyGraph,
        target: MethodologyGraph,
    ) -> GraphRevisionDiff:
        """Return the deterministic diff from base to target revision."""
        if (
            base.project_id != target.project_id
            or base.graph_id != target.graph_id
        ):
            raise BizoraError(
                ErrorCode.INVALID_REQUEST,
                "Diffs require two revisions of the same graph.",
                details={
                    "base_graph": f"{base.project_id}/{base.graph_id}",
                    "target_graph": f"{target.project_id}/{target.graph_id}",
                },
            )

        base_nodes = {node.id: node for node in base.nodes}
        target_nodes = {node.id: node for node in target.nodes}
        added_nodes = RevisionDiffService._sorted_nodes(
            target_nodes, base_nodes
        )
        removed_nodes = RevisionDiffService._sorted_nodes(
            base_nodes, target_nodes
        )
        changed_nodes = tuple(
            ChangedNode(
                node_id=node_id,
                before=base_nodes[node_id],
                after=target_nodes[node_id],
            )
            for node_id in sorted(set(base_nodes) & set(target_nodes))
            if target_nodes[node_id] != base_nodes[node_id]
        )

        base_edges = {edge.id: edge for edge in base.edges}
        target_edges = {edge.id: edge for edge in target.edges}
        added_edges = RevisionDiffService._sorted_edges(
            target_edges, base_edges
        )
        removed_edges = RevisionDiffService._sorted_edges(
            base_edges, target_edges
        )
        changed_edges = tuple(
            ChangedEdge(
                edge_id=edge_id,
                before=base_edges[edge_id],
                after=target_edges[edge_id],
            )
            for edge_id in sorted(set(base_edges) & set(target_edges))
            if target_edges[edge_id] != base_edges[edge_id]
        )

        return GraphRevisionDiff(
            project_id=base.project_id,
            graph_id=base.graph_id,
            base_version=base.version,
            target_version=target.version,
            added_nodes=added_nodes,
            removed_nodes=removed_nodes,
            changed_nodes=changed_nodes,
            added_edges=added_edges,
            removed_edges=removed_edges,
            changed_edges=changed_edges,
        )

    @staticmethod
    def _sorted_nodes(
        source: dict[str, GraphNode],
        other: dict[str, GraphNode],
    ) -> tuple[GraphNode, ...]:
        """Return source-only nodes ordered by ID."""
        return tuple(
            source[node_id] for node_id in sorted(set(source) - set(other))
        )

    @staticmethod
    def _sorted_edges(
        source: dict[str, GraphEdge],
        other: dict[str, GraphEdge],
    ) -> tuple[GraphEdge, ...]:
        """Return source-only edges ordered by ID."""
        return tuple(
            source[edge_id] for edge_id in sorted(set(source) - set(other))
        )
