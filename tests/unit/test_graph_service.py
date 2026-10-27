
"""Tests for methodology graph validation and revision creation."""

import pytest

from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.core.errors import GraphValidationError
from bizora.core.graph_service import GraphService


def make_graph() -> MethodologyGraph:
    """Build a minimal valid feed-forward methodology graph."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Vision Transformer",
        source_ids=("paper-1",),
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, label="Image"),
            GraphNode(id="encoder", kind=NodeKind.MODEL, label="Transformer encoder"),
            GraphNode(id="output", kind=NodeKind.OUTPUT, label="Predictions"),
        ),
        edges=(
            GraphEdge(id="edge-1", source="input", target="encoder"),
            GraphEdge(id="edge-2", source="encoder", target="output"),
        ),
        created_by="researcher-1",
    )


def test_validate_accepts_a_valid_graph() -> None:
    graph = make_graph()

    GraphService.validate(graph)


def test_revision_increments_version_and_sets_parent() -> None:
    original = make_graph()

    revision = GraphService.create_revision(
        original,
        created_by="researcher-2",
    )

    assert revision.version == 2
    assert revision.parent_version == 1
    assert revision.created_by == "researcher-2"


def test_revision_preserves_research_brief() -> None:
    original = make_graph().model_copy(
        update={
            "brief": {
                "problem": "Low yield.",
                "objectives": ["Raise yield"],
                "findings": [],
                "limitations": [],
            }
        }
    )

    revision = GraphService.create_revision(
        original,
        created_by="researcher-2",
    )

    assert revision.brief is not None
    assert revision.brief.problem == "Low yield."


def test_revision_preserves_original_graph() -> None:
    original = make_graph()
    original_nodes = original.nodes
    original_edges = original.edges

    revision = GraphService.create_revision(
        original,
        created_by="researcher-2",
        title="Revised Vision Transformer",
    )

    assert original.version == 1
    assert original.parent_version is None
    assert original.title == "Vision Transformer"
    assert original.nodes == original_nodes
    assert original.edges == original_edges
    assert revision.title == "Revised Vision Transformer"


def test_revision_can_replace_graph_nodes() -> None:
    original = make_graph()
    revised_nodes = (
        GraphNode(id="input", kind=NodeKind.INPUT, label="Image"),
        GraphNode(id="encoder", kind=NodeKind.MODEL, label="Modified encoder"),
        GraphNode(id="output", kind=NodeKind.OUTPUT, label="Predictions"),
    )

    revision = GraphService.create_revision(
        original,
        created_by="researcher-2",
        nodes=revised_nodes,
    )

    assert revision.nodes == revised_nodes
    assert original.nodes[1].label == "Transformer encoder"
    assert revision.nodes[1].label == "Modified encoder"


def test_revision_rejects_edges_with_missing_nodes() -> None:
    original = make_graph()
    invalid_edges = (
        GraphEdge(id="edge-1", source="missing-node", target="output"),
    )

    with pytest.raises(GraphValidationError) as exc_info:
        GraphService.create_revision(
            original,
            created_by="researcher-2",
            edges=invalid_edges,
        )

    assert any(
        "missing source node" in error
        for error in exc_info.value.details["errors"]
    )


def test_revision_rejects_cycles_in_feed_forward_graphs() -> None:
    original = make_graph()
    cyclic_edges = (
        GraphEdge(id="edge-1", source="input", target="encoder"),
        GraphEdge(id="edge-2", source="encoder", target="input"),
    )

    with pytest.raises(GraphValidationError) as exc_info:
        GraphService.create_revision(
            original,
            created_by="researcher-2",
            edges=cyclic_edges,
            require_dag=True,
        )

    assert any(
        "contains a cycle" in error
        for error in exc_info.value.details["errors"]
    )


def test_invalid_revision_does_not_change_original_version() -> None:
    original = make_graph()
    invalid_edges = (
        GraphEdge(id="edge-1", source="missing-node", target="output"),
    )

    with pytest.raises(GraphValidationError):
        GraphService.create_revision(
            original,
            created_by="researcher-2",
            edges=invalid_edges,
        )

    assert original.version == 1
    assert original.edges[0].source == "input"


def test_revision_nested_config_is_isolated_from_original() -> None:
    original = make_graph()
    configured_nodes = tuple(
        node.model_copy(update={"config": {"layers": [{"width": 128}]}})
        if node.id == "encoder"
        else node
        for node in original.nodes
    )
    original = original.model_copy(update={"nodes": configured_nodes})

    revision = GraphService.create_revision(
        original,
        created_by="researcher-2",
    )

    revision.nodes[1].config["layers"][0]["width"] = 256

    assert original.nodes[1].config["layers"][0]["width"] == 128
    assert revision.nodes[1].config["layers"][0]["width"] == 256


def test_original_nested_config_changes_do_not_affect_revision() -> None:
    original = make_graph()
    configured_nodes = tuple(
        node.model_copy(update={"config": {"layers": [{"width": 128}]}})
        if node.id == "encoder"
        else node
        for node in original.nodes
    )
    original = original.model_copy(update={"nodes": configured_nodes})

    revision = GraphService.create_revision(
        original,
        created_by="researcher-2",
    )

    original.nodes[1].config["layers"][0]["width"] = 512

    assert revision.nodes[1].config["layers"][0]["width"] == 128
    assert original.nodes[1].config["layers"][0]["width"] == 512