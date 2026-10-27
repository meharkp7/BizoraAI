"""Tests for deterministic revision-diff computation."""

import pytest

from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.core.diff_service import RevisionDiffService
from bizora.core.errors import BizoraError, ErrorCode


def make_graph(
    *,
    version: int = 1,
    graph_id: str = "graph-1",
    nodes: tuple[GraphNode, ...] | None = None,
    edges: tuple[GraphEdge, ...] | None = None,
) -> MethodologyGraph:
    """Build a graph revision for diff comparisons."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id=graph_id,
        version=version,
        title="Vision transformer",
        source_ids=("paper-1",),
        nodes=nodes
        if nodes is not None
        else (
            GraphNode(id="input", kind=NodeKind.INPUT, label="Image"),
            GraphNode(id="encoder", kind=NodeKind.MODEL, label="Encoder"),
        ),
        edges=edges
        if edges is not None
        else (GraphEdge(id="e1", source="input", target="encoder"),),
        created_by="test",
    )


def test_identical_revisions_produce_empty_diff() -> None:
    diff = RevisionDiffService.diff(make_graph(), make_graph(version=1))

    assert diff.base_version == 1
    assert diff.target_version == 1
    assert diff.is_empty()


def test_added_and_removed_nodes_detected() -> None:
    base = make_graph()
    target = make_graph(
        version=2,
        nodes=(
            GraphNode(id="encoder", kind=NodeKind.MODEL, label="Encoder"),
            GraphNode(id="head", kind=NodeKind.OUTPUT, label="Head"),
        ),
        edges=(GraphEdge(id="e2", source="encoder", target="head"),),
    )

    diff = RevisionDiffService.diff(base, target)

    assert [node.id for node in diff.added_nodes] == ["head"]
    assert [node.id for node in diff.removed_nodes] == ["input"]
    assert [edge.id for edge in diff.added_edges] == ["e2"]
    assert [edge.id for edge in diff.removed_edges] == ["e1"]
    assert diff.changed_nodes == ()
    assert diff.changed_edges == ()


def test_changed_node_reports_before_and_after() -> None:
    base = make_graph()
    target = make_graph(
        version=2,
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, label="Image"),
            GraphNode(
                id="encoder",
                kind=NodeKind.MODEL,
                label="Encoder",
                config={"layers": 12},
            ),
        ),
    )

    diff = RevisionDiffService.diff(base, target)

    assert len(diff.changed_nodes) == 1
    changed = diff.changed_nodes[0]
    assert changed.node_id == "encoder"
    assert changed.before.config == {}
    assert changed.after.config == {"layers": 12}
    assert diff.added_nodes == ()
    assert diff.removed_nodes == ()


def test_changed_edge_reports_before_and_after() -> None:
    base = make_graph()
    target = make_graph(
        version=2,
        edges=(
            GraphEdge(id="e1", source="input", target="encoder", label="tokens"),
        ),
    )

    diff = RevisionDiffService.diff(base, target)

    assert len(diff.changed_edges) == 1
    changed = diff.changed_edges[0]
    assert changed.edge_id == "e1"
    assert changed.before.label is None
    assert changed.after.label == "tokens"


def test_diff_entries_ordered_by_id() -> None:
    base = make_graph(nodes=(), edges=())
    target = make_graph(
        version=2,
        nodes=(
            GraphNode(id="zebra", kind=NodeKind.INPUT, label="Z"),
            GraphNode(id="apple", kind=NodeKind.INPUT, label="A"),
            GraphNode(id="mango", kind=NodeKind.INPUT, label="M"),
        ),
        edges=(),
    )

    diff = RevisionDiffService.diff(base, target)

    assert [node.id for node in diff.added_nodes] == [
        "apple",
        "mango",
        "zebra",
    ]


def test_cross_graph_diff_rejected() -> None:
    with pytest.raises(BizoraError) as exc_info:
        RevisionDiffService.diff(make_graph(), make_graph(graph_id="other"))

    assert exc_info.value.code == ErrorCode.INVALID_REQUEST
