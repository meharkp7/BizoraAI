"""Tests for tensor-shape patch preflight on the deep-learning pack."""

from typing import Any

from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.contracts.packs import PackPreflightSeverity
from bizora.contracts.patches import GraphPatch, PatchOperation
from bizora.packs.deep_learning import pack


def make_graph() -> MethodologyGraph:
    """Build input(2,8) -> linear 8->4 -> relu -> output."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Stack",
        nodes=(
            GraphNode(
                id="input",
                kind=NodeKind.INPUT,
                label="Input",
                output_shape=(2, 8),
            ),
            GraphNode(
                id="dense",
                kind=NodeKind.MODEL,
                label="Dense",
                config={"layer": "linear", "in_features": 8, "out_features": 4},
            ),
            GraphNode(
                id="act",
                kind=NodeKind.MODEL,
                label="Activation",
                config={"layer": "activation", "function": "relu"},
            ),
            GraphNode(id="output", kind=NodeKind.OUTPUT, label="Output"),
        ),
        edges=(
            GraphEdge(id="e1", source="input", target="dense"),
            GraphEdge(id="e2", source="dense", target="act"),
            GraphEdge(id="e3", source="act", target="output"),
        ),
        created_by="tester",
    )


def make_patch(
    operation: PatchOperation,
    *,
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
    base_version: int = 1,
) -> GraphPatch:
    """Build a patch against the shared fixture graph."""
    return GraphPatch(
        patch_id="patch-1",
        base_graph_id="graph-1",
        base_version=base_version,
        operation=operation,
        target_id=target_id,
        payload=payload or {},
        rationale="test edit",
        requested_by="tester",
    )


def test_compatible_config_update_clears() -> None:
    """A shape-preserving parameter tweak yields no findings."""
    graph = make_graph()
    patch = make_patch(
        PatchOperation.UPDATE_NODE_CONFIG,
        target_id="act",
        payload={"config": {"function": "gelu"}},
    )
    assert pack.check_patch(graph, patch) == ()


def test_width_mismatch_replacement_blocks() -> None:
    """Swapping in a layer that disagrees on width is BLOCKed."""
    graph = make_graph()
    patch = make_patch(
        PatchOperation.REPLACE_NODE,
        target_id="dense",
        payload={
            "node": {
                "id": "dense",
                "kind": "model",
                "label": "Dense",
                "config": {"layer": "linear", "in_features": 7, "out_features": 4},
            }
        },
    )
    findings = pack.check_patch(graph, patch)
    assert len(findings) == 1
    assert findings[0].rule_id == "deep_learning_shape_mismatch"
    assert findings[0].severity is PackPreflightSeverity.BLOCK
    assert "last dim 8 != 'in_features' 7" in findings[0].message


def test_unknown_layer_blocks() -> None:
    """Layers outside the allowlist are BLOCKed, not compiled."""
    graph = make_graph()
    patch = make_patch(
        PatchOperation.UPDATE_NODE_CONFIG,
        target_id="dense",
        payload={"config": {"layer": "fancy-new-op"}},
    )
    findings = pack.check_patch(graph, patch)
    assert [finding.rule_id for finding in findings] == [
        "deep_learning_unknown_layer",
    ]
    assert "fancy-new-op" in findings[0].message


def test_broken_divisibility_blocks() -> None:
    """Parameter constraints (heads dividing width) are enforced."""
    graph = make_graph()
    patch = make_patch(
        PatchOperation.REPLACE_NODE,
        target_id="dense",
        payload={
            "node": {
                "id": "dense",
                "kind": "model",
                "label": "Attention",
                "config": {"layer": "attention", "embed_dim": 8, "num_heads": 3},
                "input_shape": [2, 4, 8],
            }
        },
    )
    findings = pack.check_patch(graph, patch)
    assert any(
        finding.rule_id == "deep_learning_invalid_layer_params"
        and "must be divisible" in finding.message
        for finding in findings
    )


def test_collapsing_convolution_blocks() -> None:
    """A kernel larger than its input is BLOCKed on add."""
    graph = make_graph()
    patch = make_patch(
        PatchOperation.ADD_NODE,
        payload={
            "node": {
                "id": "conv",
                "kind": "model",
                "label": "Conv",
                "config": {
                    "layer": "convolution",
                    "in_channels": 3,
                    "out_channels": 6,
                    "spatial_dims": 2,
                    "kernel_size": 9,
                },
                "input_shape": [1, 3, 8, 8],
            }
        },
    )
    findings = pack.check_patch(graph, patch)
    assert len(findings) == 1
    assert findings[0].rule_id == "deep_learning_shape_mismatch"
    assert "collapses" in findings[0].message


def test_fan_in_conflict_blocks() -> None:
    """Wiring two disagreeing producers into one node is BLOCKed."""
    nodes = (
        GraphNode(
            id="left",
            kind=NodeKind.INPUT,
            label="Left",
            output_shape=(2, 8),
        ),
        GraphNode(
            id="right",
            kind=NodeKind.INPUT,
            label="Right",
            output_shape=(2, 4),
        ),
        GraphNode(
            id="dense",
            kind=NodeKind.MODEL,
            label="Dense",
            config={"layer": "linear", "in_features": 8, "out_features": 4},
        ),
    )
    graph = MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Fork",
        nodes=nodes,
        edges=(GraphEdge(id="e1", source="left", target="dense"),),
        created_by="tester",
    )
    patch = make_patch(
        PatchOperation.ADD_EDGE,
        payload={"edge": {"id": "e2", "source": "right", "target": "dense"}},
    )
    findings = pack.check_patch(graph, patch)
    assert len(findings) == 1
    assert findings[0].rule_id == "deep_learning_shape_mismatch"
    assert "conflicting inputs" in findings[0].message


def test_declared_output_conflict_blocks() -> None:
    """A declared sink shape that disagrees with the flow is BLOCKed."""
    graph = make_graph()
    patch = make_patch(
        PatchOperation.REPLACE_NODE,
        target_id="output",
        payload={
            "node": {
                "id": "output",
                "kind": "output",
                "label": "Output",
                "output_shape": [2, 9],
            }
        },
    )
    findings = pack.check_patch(graph, patch)
    assert len(findings) == 1
    assert findings[0].rule_id == "deep_learning_shape_mismatch"


def test_lexical_and_shape_findings_combine() -> None:
    """Interface preservation and shape checks report side by side."""
    nodes = (
        GraphNode(
            id="input",
            kind=NodeKind.INPUT,
            label="Input",
            output_shape=(2, 4, 8),
        ),
        GraphNode(
            id="block",
            kind=NodeKind.MODEL,
            label="Attention block",
            config={"layer": "attention", "embed_dim": 8, "num_heads": 2},
        ),
    )
    graph = MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Attention",
        nodes=nodes,
        edges=(GraphEdge(id="e1", source="input", target="block"),),
        created_by="tester",
    )
    patch = make_patch(
        PatchOperation.REPLACE_NODE,
        target_id="block",
        payload={
            "node": {
                "id": "block",
                "kind": "evaluation",
                "label": "Benchmark scores",
                "config": {"layer": "fancy-new-op"},
            }
        },
    )
    findings = pack.check_patch(graph, patch)
    rule_ids = {finding.rule_id for finding in findings}
    assert "deep_learning_interface_preserved" in rule_ids
    assert "deep_learning_unknown_layer" in rule_ids
    assert all(finding.severity is PackPreflightSeverity.BLOCK for finding in findings)


def test_structural_problems_abstain_to_core() -> None:
    """Unparseable payloads, stale bases, and missing targets clear here."""
    graph = make_graph()
    bad_node = make_patch(
        PatchOperation.ADD_NODE,
        payload={"node": {"id": "???"}},
    )
    assert pack.check_patch(graph, bad_node) == ()
    stale = make_patch(
        PatchOperation.UPDATE_NODE_CONFIG,
        target_id="dense",
        payload={"config": {"layer": "fancy-new-op"}},
        base_version=99,
    )
    assert pack.check_patch(graph, stale) == ()
    missing = make_patch(
        PatchOperation.REPLACE_NODE,
        target_id="ghost",
        payload={"node": {"id": "ghost", "kind": "model", "label": "Ghost"}},
    )
    assert pack.check_patch(graph, missing) == ()
    mismatched_id = make_patch(
        PatchOperation.REPLACE_NODE,
        target_id="dense",
        payload={"node": {"id": "other", "kind": "model", "label": "Other"}},
    )
    assert pack.check_patch(graph, mismatched_id) == ()


def test_removing_an_edge_clears() -> None:
    """Dropping a data-flow edge removes constraints, so it clears."""
    graph = make_graph()
    patch = make_patch(PatchOperation.REMOVE_EDGE, target_id="e3")
    assert pack.check_patch(graph, patch) == ()


def test_opaque_nodes_pass_shapes_through() -> None:
    """Unbound nodes never invent conflicts; declared shapes still check."""
    graph = make_graph()
    patch = make_patch(
        PatchOperation.REPLACE_NODE,
        target_id="act",
        payload={
            "node": {
                "id": "act",
                "kind": "model",
                "label": "Custom op",
                "output_shape": [2, 4],
            }
        },
    )
    assert pack.check_patch(graph, patch) == ()
