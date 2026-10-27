
"""Tests for atomic multi-patch batch application."""

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


def make_graph() -> MethodologyGraph:
    """Create a valid graph for patch-batch tests."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        parent_version=None,
        title="Vision model",
        source_ids=("paper-1",),
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, label="Image"),
            GraphNode(
                id="encoder",
                kind=NodeKind.MODEL,
                label="Encoder",
                config={"layers": 6},
            ),
            GraphNode(id="output", kind=NodeKind.OUTPUT, label="Predictions"),
        ),
        edges=(
            GraphEdge(id="e1", source="input", target="encoder"),
            GraphEdge(id="e2", source="encoder", target="output"),
        ),
        created_by="test",
    )


def make_patch(
    operation: PatchOperation,
    *,
    patch_id: str = "patch-1",
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
    base_graph_id: str = "graph-1",
    base_version: int = 1,
) -> GraphPatch:
    """Create a patch against the default graph revision."""
    return GraphPatch(
        patch_id=patch_id,
        base_graph_id=base_graph_id,
        base_version=base_version,
        operation=operation,
        target_id=target_id,
        payload=payload or {},
        rationale="Test batch edit",
        requested_by="test-user",
    )


def test_remove_edge_then_node_lands_as_one_revision() -> None:
    graph = make_graph()
    batch = [
        make_patch(PatchOperation.REMOVE_EDGE, patch_id="p1", target_id="e2"),
        make_patch(
            PatchOperation.REMOVE_EDGE, patch_id="p2", target_id="e1"
        ),
        make_patch(
            PatchOperation.REMOVE_NODE, patch_id="p3", target_id="encoder"
        ),
    ]

    revision = GraphPatchService.apply_patches(graph, batch)

    assert revision.version == 2
    assert revision.parent_version == 1
    assert revision.created_by == "test-user"
    assert {node.id for node in revision.nodes} == {"input", "output"}
    assert revision.edges == ()
    # The supplied base snapshot is never mutated.
    assert len(graph.nodes) == 3
    assert len(graph.edges) == 2


def test_sequential_config_updates_merge() -> None:
    graph = make_graph()
    batch = [
        make_patch(
            PatchOperation.UPDATE_NODE_CONFIG,
            patch_id="p1",
            target_id="encoder",
            payload={"config": {"layers": 12}},
        ),
        make_patch(
            PatchOperation.UPDATE_NODE_CONFIG,
            patch_id="p2",
            target_id="encoder",
            payload={"config": {"dropout": 0.1}},
        ),
    ]

    revision = GraphPatchService.apply_patches(graph, batch)

    assert revision.version == 2
    encoder = next(node for node in revision.nodes if node.id == "encoder")
    assert encoder.config == {"layers": 12, "dropout": 0.1}


def test_empty_batch_rejected() -> None:
    with pytest.raises(BizoraError) as exc_info:
        GraphPatchService.apply_patches(make_graph(), [])

    assert exc_info.value.code == ErrorCode.INVALID_GRAPH_PATCH


def test_stale_patch_in_batch_rejected_with_conflict() -> None:
    batch = [
        make_patch(
            PatchOperation.UPDATE_NODE_CONFIG,
            patch_id="p1",
            target_id="encoder",
            payload={"config": {"layers": 12}},
        ),
        make_patch(
            PatchOperation.UPDATE_NODE_CONFIG,
            patch_id="p2",
            target_id="encoder",
            payload={"config": {"layers": 24}},
            base_version=2,
        ),
    ]

    with pytest.raises(BizoraError) as exc_info:
        GraphPatchService.apply_patches(make_graph(), batch)

    assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT


def test_invalid_later_patch_fails_whole_batch() -> None:
    batch = [
        make_patch(
            PatchOperation.UPDATE_NODE_CONFIG,
            patch_id="p1",
            target_id="encoder",
            payload={"config": {"layers": 12}},
        ),
        make_patch(
            PatchOperation.REMOVE_NODE, patch_id="p2", target_id="encoder"
        ),
    ]

    with pytest.raises(BizoraError) as exc_info:
        GraphPatchService.apply_patches(make_graph(), batch)

    assert exc_info.value.code == ErrorCode.INVALID_GRAPH_PATCH
    assert "connected edges" in str(exc_info.value)


def test_batch_result_must_stay_valid() -> None:
    batch = [
        make_patch(
            PatchOperation.ADD_EDGE,
            patch_id="p1",
            payload={
                "edge": {
                    "id": "e3",
                    "source": "output",
                    "target": "input",
                }
            },
        ),
    ]

    with pytest.raises(BizoraError) as exc_info:
        GraphPatchService.apply_patches(make_graph(), batch)

    assert exc_info.value.code == ErrorCode.INVALID_GRAPH_PATCH
