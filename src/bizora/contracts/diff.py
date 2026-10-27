"""Revision-diff contracts for comparing methodology graph revisions."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bizora.contracts.graph import GraphEdge, GraphNode


class ChangedNode(BaseModel):
    """One node present in both revisions with different content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=128)
    before: GraphNode
    after: GraphNode


class ChangedEdge(BaseModel):
    """One edge present in both revisions with different content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: str = Field(min_length=1, max_length=128)
    before: GraphEdge
    after: GraphEdge


class GraphRevisionDiff(BaseModel):
    """Deterministic differences between two revisions of one graph.

    Entries are ordered by ID so repeated diffs of the same revisions
    always produce identical output.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    base_version: int = Field(ge=1)
    target_version: int = Field(ge=1)
    added_nodes: tuple[GraphNode, ...] = ()
    removed_nodes: tuple[GraphNode, ...] = ()
    changed_nodes: tuple[ChangedNode, ...] = ()
    added_edges: tuple[GraphEdge, ...] = ()
    removed_edges: tuple[GraphEdge, ...] = ()
    changed_edges: tuple[ChangedEdge, ...] = ()

    def is_empty(self) -> bool:
        """Return True when both revisions are semantically identical."""
        return not (
            self.added_nodes
            or self.removed_nodes
            or self.changed_nodes
            or self.added_edges
            or self.removed_edges
            or self.changed_edges
        )

    def summary(self) -> dict[str, Any]:
        """Return stable counts of each change category."""
        return {
            "added_nodes": len(self.added_nodes),
            "removed_nodes": len(self.removed_nodes),
            "changed_nodes": len(self.changed_nodes),
            "added_edges": len(self.added_edges),
            "removed_edges": len(self.removed_edges),
            "changed_edges": len(self.changed_edges),
        }
