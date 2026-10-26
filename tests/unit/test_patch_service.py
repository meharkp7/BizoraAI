
"""Tests for safe methodology graph patch application."""

from typing import Any

import pytest

from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.contracts.patches import GraphPatch, PatchOperation
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.patch_service import GraphPatchService


def make_graph(*, include_orphan: bool = False) -> MethodologyGraph:
    """Create a valid graph for patch-service tests."""
    nodes = [
        GraphNode(id="input", kind=NodeKind.INPUT, label="Image"),
        GraphNode(
            id="encoder",
            kind=NodeKind.MODEL,
            label="Encoder",
            config={"layers": 6, "dropout": 0.0},
        ),
        GraphNode(id="output", kind=NodeKind.OUTPUT, label="Predictions"),
    ]

    edges = [
        GraphEdge(id="e1", source="input", target="encoder"),
        GraphEdge(id="e2", source="encoder", target="output"),
    ]

    if include_orphan:
        nodes.append(
            GraphNode(
                id="orphan",
                kind=NodeKind.OPERATION,
                label="Unused operation",
            )
        )

    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        parent_version=None,
        title="Vision model",
        source_ids=("paper-1",),
        nodes=tuple(nodes),
        edges=tuple(edges),
        created_by="test",
    )


def make_patch(
    operation: PatchOperation,
    *,
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
    base_graph_id: str = "graph-1",
    base_version: int = 1,
) -> GraphPatch:
    """Create a patch against the default graph revision."""
    return GraphPatch(
        patch_id="patch-1",
        base_graph_id=base_graph_id,
        base_version=base_version,
        operation=operation,
        target_id=target_id,
        payload=payload or {},
        rationale="Test graph edit",
        requested_by="test-user",
    )


def test_add_node_creates_new_revision_without_mutating_base() -> None:
    graph = make_graph()
    patch = make_patch(
        PatchOperation.ADD_NODE,
        payload={
            "node": {
                "id": "normalizer",
                "kind": "preprocessing",
                "label": "Normalize image",
            }
        },
    )

    revised = GraphPatchService.apply_patch(graph, patch)

    assert revised.version == 2
    assert revised.parent_version == 1
    assert revised.created_by == "test-user"
    assert any(node.id == "normalizer" for node in revised.nodes)
    assert all(node.id != "normalizer" for node in graph.nodes)


def test_update_node_config_merges_config_values() -> None:
    graph = make_graph()
    patch = make_patch(
        PatchOperation.UPDATE_NODE_CONFIG,
        target_id="encoder",
        payload={"config": {"dropout": 0.1, "heads": 8}},
    )

    revised = GraphPatchService.apply_patch(graph, patch)
    encoder = next(node for node in revised.nodes if node.id == "encoder")

    assert encoder.config == {"layers": 6, "dropout": 0.1, "heads": 8}
    original_encoder = next(
        node for node in graph.nodes if node.id == "encoder"
    )
    assert original_encoder.config == {"layers": 6, "dropout": 0.0}


def test_replace_node_preserves_target_id() -> None:
    graph = make_graph()
    patch = make_patch(
        PatchOperation.REPLACE_NODE,
        target_id="encoder",
        payload={
            "node": {
                "id": "encoder",
                "kind": "model",
                "label": "Updated encoder",
                "config": {"layers": 12},
            }
        },
    )

    revised = GraphPatchService.apply_patch(graph, patch)
    encoder = next(node for node in revised.nodes if node.id == "encoder")

    assert encoder.label == "Updated encoder"
    assert encoder.config == {"layers": 12}


def test_add_edge_creates_valid_connection() -> None:
    graph = make_graph()
    patch = make_patch(
        PatchOperation.ADD_EDGE,
        payload={
            "edge": {
                "id": "e3",
                "source": "input",
                "target": "output",
            }
        },
    )

    revised = GraphPatchService.apply_patch(graph, patch)

    assert {edge.id for edge in revised.edges} == {"e1", "e2", "e3"}


def test_remove_edge_removes_only_requested_edge() -> None:
    graph = make_graph()
    patch = make_patch(
        PatchOperation.REMOVE_EDGE,
        target_id="e1",
    )

    revised = GraphPatchService.apply_patch(graph, patch)

    assert {edge.id for edge in revised.edges} == {"e2"}
    assert len(graph.edges) == 2


def test_remove_unconnected_node() -> None:
    graph = make_graph(include_orphan=True)
    patch = make_patch(
        PatchOperation.REMOVE_NODE,
        target_id="orphan",
    )

    revised = GraphPatchService.apply_patch(graph, patch)

    assert all(node.id != "orphan" for node in revised.nodes)


def test_remove_connected_node_requires_edges_removed_first() -> None:
    graph = make_graph()
    patch = make_patch(
        PatchOperation.REMOVE_NODE,
        target_id="encoder",
    )

    with pytest.raises(BizoraError) as exc_info:
        GraphPatchService.apply_patch(graph, patch)

    assert exc_info.value.code == ErrorCode.INVALID_GRAPH_PATCH
    assert exc_info.value.details["connected_edge_ids"] == ["e1", "e2"]


def test_duplicate_node_id_is_rejected() -> None:
    graph = make_graph()
    patch = make_patch(
        PatchOperation.ADD_NODE,
        payload={
            "node": {
                "id": "encoder",
                "kind": "model",
                "label": "Duplicate encoder",
            }
        },
    )

    with pytest.raises(BizoraError) as exc_info:
        GraphPatchService.apply_patch(graph, patch)

    assert exc_info.value.code == ErrorCode.INVALID_GRAPH_PATCH


def test_invalid_edge_endpoint_is_rejected() -> None:
    graph = make_graph()
    patch = make_patch(
        PatchOperation.ADD_EDGE,
        payload={
            "edge": {
                "id": "e3",
                "source": "input",
                "target": "missing-node",
            }
        },
    )

    with pytest.raises(BizoraError) as exc_info:
        GraphPatchService.apply_patch(graph, patch)

    assert exc_info.value.code == ErrorCode.INVALID_GRAPH_PATCH


def test_stale_patch_returns_resource_conflict() -> None:
    graph = make_graph()
    patch = make_patch(
        PatchOperation.ADD_NODE,
        base_version=2,
        payload={
            "node": {
                "id": "normalizer",
                "kind": "preprocessing",
                "label": "Normalize image",
            }
        },
    )

    with pytest.raises(BizoraError) as exc_info:
        GraphPatchService.apply_patch(graph, patch)

    assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT


def test_patch_for_another_graph_is_rejected() -> None:
    graph = make_graph()
    patch = make_patch(
        PatchOperation.REMOVE_EDGE,
        target_id="e1",
        base_graph_id="another-graph",
    )

    with pytest.raises(BizoraError) as exc_info:
        GraphPatchService.apply_patch(graph, patch)

    assert exc_info.value.code == ErrorCode.INVALID_GRAPH_PATCH


def test_missing_edge_target_is_rejected() -> None:
    graph = make_graph()
    patch = make_patch(
        PatchOperation.REMOVE_EDGE,
        target_id="missing-edge",
    )

    with pytest.raises(BizoraError) as exc_info:
        GraphPatchService.apply_patch(graph, patch)

    assert exc_info.value.code == ErrorCode.INVALID_GRAPH_PATCH
