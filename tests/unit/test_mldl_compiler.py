"""Tests for the template-only graph-to-PyTorch compiler."""

from typing import Any

import pytest

from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
    RelationKind,
)
from bizora.packs.deep_learning import (
    GraphCompileError,
    check_first_party_source,
    compile_graph_to_torch,
)


def make_chain(
    entry_shape: tuple[int | None, ...],
    layers: list[tuple[str, dict[str, Any]]],
    *,
    exit_shape: tuple[int | None, ...] | None = None,
) -> MethodologyGraph:
    """Build input -> layer nodes -> output along data-flow edges."""
    nodes: list[GraphNode] = [
        GraphNode(
            id="input",
            kind=NodeKind.INPUT,
            label="Input",
            output_shape=entry_shape,
        ),
    ]
    edges: list[GraphEdge] = []
    previous = "input"
    for index, (layer_id, params) in enumerate(layers):
        node_id = f"layer{index}"
        nodes.append(
            GraphNode(
                id=node_id,
                kind=NodeKind.MODEL,
                label=f"Layer {index}",
                config={"layer": layer_id, **params},
            )
        )
        edges.append(
            GraphEdge(
                id=f"edge{index}",
                source=previous,
                target=node_id,
            )
        )
        previous = node_id
    nodes.append(
        GraphNode(
            id="output",
            kind=NodeKind.OUTPUT,
            label="Output",
            output_shape=exit_shape,
        )
    )
    edges.append(GraphEdge(id="edge-out", source=previous, target="output"))
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Chain",
        nodes=tuple(nodes),
        edges=tuple(edges),
        created_by="tester",
    )


CASES: list[tuple[str, tuple[int, ...], dict[str, Any], str, tuple[int, ...]]] = [
    ("linear", (2, 8), {"in_features": 8, "out_features": 4}, "nn.Linear(8, 4, bias=True)", (2, 4)),
    (
        "convolution",
        (1, 3, 8, 8),
        {"in_channels": 3, "out_channels": 6, "spatial_dims": 2, "kernel_size": 3, "padding": 1},
        "nn.Conv2d(3, 6, kernel_size=3",
        (1, 6, 8, 8),
    ),
    ("normalization", (2, 8), {"variant": "layer", "num_channels": 8}, "nn.LayerNorm(8", (2, 8)),
    ("normalization", (2, 8), {"variant": "rms", "num_channels": 8}, "_RMSNorm(8", (2, 8)),
    (
        "normalization",
        (2, 8, 4),
        {"variant": "group", "num_channels": 8, "num_groups": 2},
        "nn.GroupNorm(2, 8",
        (2, 8, 4),
    ),
    (
        "normalization",
        (2, 8, 4, 4),
        {"variant": "batch", "num_channels": 8},
        "nn.BatchNorm2d(8",
        (2, 8, 4, 4),
    ),
    ("activation", (2, 8), {"function": "gelu"}, "nn.GELU()", (2, 8)),
    ("dropout", (2, 8), {"p": 0.5}, "nn.Dropout(0.5)", (2, 8)),
    (
        "attention",
        (2, 4, 8),
        {"embed_dim": 8, "num_heads": 2},
        "nn.MultiheadAttention(8, 2",
        (2, 4, 8),
    ),
    (
        "mlp-block",
        (2, 8),
        {"in_features": 8, "out_features": 4, "hidden_features": 16},
        "nn.Sequential(nn.Linear(8, 16",
        (2, 4),
    ),
    (
        "residual",
        (2, 8),
        {"branch": {"layer": "linear", "in_features": 8, "out_features": 8}},
        "_Residual(nn.Linear(8, 8",
        (2, 8),
    ),
    (
        "embedding",
        (2, 6),
        {"num_embeddings": 100, "embedding_dim": 8},
        "nn.Embedding(100, 8)",
        (2, 6, 8),
    ),
    (
        "pooling",
        (1, 3, 8, 8),
        {"spatial_dims": 2, "kernel_size": 2},
        "nn.MaxPool2d(kernel_size=2, stride=2",
        (1, 3, 4, 4),
    ),
    (
        "positional-encoding",
        (2, 4, 8),
        {"d_model": 8, "max_len": 64},
        "_SinusoidalPositionalEncoding(8, max_len=64)",
        (2, 4, 8),
    ),
]


@pytest.mark.parametrize(
    ("layer_id", "entry", "params", "snippet", "exited"),
    CASES,
)
def test_compile_each_layer_kind(
    layer_id: str,
    entry: tuple[int, ...],
    params: dict[str, Any],
    snippet: str,
    exited: tuple[int, ...],
) -> None:
    """Every allowlisted layer compiles to clean template-only source."""
    graph = make_chain(entry, [(layer_id, params)])
    compiled = compile_graph_to_torch(graph)
    assert check_first_party_source(compiled.source) == ()
    assert snippet in compiled.source
    assert compiled.shapes["layer0"] == exited
    assert compiled.layers[0].layer_id == layer_id
    assert compiled.entry_shape == entry


def test_compiled_source_references_only_templates() -> None:
    """Template ids are recorded; node ids and labels never reach the code."""
    graph = make_chain(
        (2, 8),
        [("linear", {"in_features": 8, "out_features": 4}), ("activation", {"function": "relu"})],
    )
    compiled = compile_graph_to_torch(graph)
    assert compiled.template_ids == ("linear", "activation")
    assert "self.layer_0 = nn.Linear(8, 4, bias=True)" in compiled.source
    assert "self.layer_1 = nn.ReLU()" in compiled.source
    assert "x = self.layer_0(x)\n        x = self.layer_1(x)" in compiled.source
    assert "layer0" not in compiled.source
    assert "Layer 0" not in compiled.source


def test_hostile_labels_never_reach_generated_code() -> None:
    """Model-written text (even code-shaped) cannot smuggle into output."""
    payloads = (
        "import os; os.system('pwn')",
        "__import__('sys').exit(1)",
        "eval('1+1')",
        "nn.Bogus()",
    )
    nodes = [
        GraphNode(
            id="input",
            kind=NodeKind.INPUT,
            label=payloads[0],
            description=payloads[1],
            output_shape=(2, 8),
        ),
        GraphNode(
            id="mid",
            kind=NodeKind.MODEL,
            label=payloads[2],
            description=payloads[3],
            config={"layer": "linear", "in_features": 8, "out_features": 4},
        ),
        GraphNode(id="output", kind=NodeKind.OUTPUT, label=payloads[0]),
    ]
    edges = (
        GraphEdge(id="e1", source="input", target="mid"),
        GraphEdge(id="e2", source="mid", target="output"),
    )
    graph = MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Hostile",
        nodes=tuple(nodes),
        edges=edges,
        created_by="tester",
    )
    compiled = compile_graph_to_torch(graph)
    for payload in payloads:
        assert payload not in compiled.source
    assert "import os" not in compiled.source
    assert "__import__" not in compiled.source
    assert "eval(" not in compiled.source
    assert "Bogus" not in compiled.source
    assert check_first_party_source(compiled.source) == ()


def test_helpers_ship_only_when_needed() -> None:
    """Preamble helpers and math import appear exactly when referenced."""
    plain = compile_graph_to_torch(
        make_chain(
            (2, 8),
            [
                ("linear", {"in_features": 8, "out_features": 4}),
            ],
        )
    )
    assert "import math" not in plain.source
    assert "helper:" not in ",".join(plain.template_ids)
    rich = compile_graph_to_torch(
        make_chain(
            (2, 4, 8),
            [
                ("normalization", {"variant": "rms", "num_channels": 8}),
                ("residual", {"branch": {"layer": "activation"}}),
                ("positional-encoding", {"d_model": 8}),
            ],
        )
    )
    assert check_first_party_source(rich.source) == ()
    assert "import math" in rich.source
    assert "helper:rms_norm" in rich.template_ids
    assert "helper:residual" in rich.template_ids
    assert "helper:positional" in rich.template_ids


def test_unknown_layer_is_rejected() -> None:
    """Layers outside the allowlist never compile."""
    graph = make_chain((2, 8), [("fancy-new-op", {})])
    with pytest.raises(GraphCompileError, match="unknown layer"):
        compile_graph_to_torch(graph)


def test_invalid_params_are_rejected() -> None:
    """Bad enums, divisibility, and collapsed shapes never compile."""
    with pytest.raises(GraphCompileError, match="must be one of"):
        compile_graph_to_torch(
            make_chain(
                (2, 8),
                [("activation", {"function": "swish"})],
            )
        )
    with pytest.raises(GraphCompileError, match="must be divisible"):
        compile_graph_to_torch(
            make_chain(
                (2, 4, 8),
                [("attention", {"embed_dim": 8, "num_heads": 3})],
            )
        )
    with pytest.raises(GraphCompileError, match="collapses"):
        compile_graph_to_torch(
            make_chain(
                (1, 3, 8, 8),
                [
                    (
                        "convolution",
                        {"in_channels": 3, "out_channels": 6, "spatial_dims": 2, "kernel_size": 9},
                    )
                ],
            )
        )


def test_residual_rejects_shape_changing_branch() -> None:
    """A residual branch that resizes its input cannot compile."""
    graph = make_chain(
        (2, 8),
        [
            ("residual", {"branch": {"layer": "linear", "in_features": 8, "out_features": 4}}),
        ],
    )
    with pytest.raises(GraphCompileError, match="conflicts with the block"):
        compile_graph_to_torch(graph)


def test_residual_rejects_nested_residual() -> None:
    """Branches stay flat: residual-in-residual is refused at validation."""
    graph = make_chain(
        (2, 8),
        [
            ("residual", {"branch": {"layer": "residual", "branch": {"layer": "activation"}}}),
        ],
    )
    with pytest.raises(GraphCompileError, match="may not itself be residual"):
        compile_graph_to_torch(graph)


def test_residual_rejects_unknown_branch_layer() -> None:
    """Branches outside the allowlist are refused with one clean message."""
    graph = make_chain((2, 8), [("residual", {"branch": {"layer": "fancy-new-op"}})])
    with pytest.raises(GraphCompileError) as excinfo:
        compile_graph_to_torch(graph)
    assert len(excinfo.value.errors) == 1
    assert "unknown branch layer 'fancy-new-op'" in excinfo.value.errors[0]


def test_batch_norm_selects_class_by_rank() -> None:
    """Batch norm renders the rank-correct class; unknown rank refuses."""
    rank3 = compile_graph_to_torch(
        make_chain(
            (2, 8, 4),
            [
                ("normalization", {"variant": "batch", "num_channels": 8}),
            ],
        )
    )
    assert "nn.BatchNorm1d(8" in rank3.source
    unknown = MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Unknown",
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, label="Input"),
            GraphNode(
                id="norm",
                kind=NodeKind.MODEL,
                label="Norm",
                config={"layer": "normalization", "variant": "batch", "num_channels": 8},
            ),
            GraphNode(id="output", kind=NodeKind.OUTPUT, label="Output"),
        ),
        edges=(
            GraphEdge(id="e1", source="input", target="norm"),
            GraphEdge(id="e2", source="norm", target="output"),
        ),
        created_by="tester",
    )
    with pytest.raises(GraphCompileError, match="known input rank"):
        compile_graph_to_torch(unknown)


def test_module_name_injection_is_rejected() -> None:
    """The one caller-supplied string in codegen must be a plain identifier."""
    graph = make_chain((2, 8), [("linear", {"in_features": 8, "out_features": 4})])
    for bad in ("Bad Name", "class", "x;y", "9lives", "a-b", ""):
        with pytest.raises(GraphCompileError, match="invalid module name"):
            compile_graph_to_torch(graph, module_name=bad)


def test_cycles_and_layerless_graphs_are_rejected() -> None:
    """Codegen needs a DAG with at least one bound layer."""
    cyclic = MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Cyclic",
        nodes=(
            GraphNode(
                id="a",
                kind=NodeKind.MODEL,
                label="A",
                config={"layer": "linear", "in_features": 4, "out_features": 4},
                input_shape=(2, 4),
            ),
            GraphNode(
                id="b",
                kind=NodeKind.MODEL,
                label="B",
                config={"layer": "linear", "in_features": 4, "out_features": 4},
            ),
        ),
        edges=(
            GraphEdge(id="e1", source="a", target="b"),
            GraphEdge(id="e2", source="b", target="a"),
        ),
        created_by="tester",
    )
    with pytest.raises(GraphCompileError, match="cycle"):
        compile_graph_to_torch(cyclic)
    bare = make_chain((2, 8), [])
    with pytest.raises(GraphCompileError, match="no nodes bound"):
        compile_graph_to_torch(bare)


def test_non_data_flow_edges_do_not_carry_shapes() -> None:
    """Control/depends edges are ignored by shape flow and compilation."""
    graph = make_chain((2, 8), [("linear", {"in_features": 8, "out_features": 4})])
    extra = GraphEdge(
        id="control",
        source="output",
        target="layer0",
        relation=RelationKind.CONTROL_FLOW,
    )
    graph = graph.model_copy(update={"edges": (*graph.edges, extra)})
    compiled = compile_graph_to_torch(graph)
    assert compiled.shapes["layer0"] == (2, 4)


def test_compile_is_deterministic() -> None:
    """Two compiles of one graph produce identical source."""
    graph = make_chain(
        (2, 4, 8),
        [
            ("attention", {"embed_dim": 8, "num_heads": 2}),
            ("mlp-block", {"in_features": 8, "out_features": 8, "hidden_features": 16}),
        ],
    )
    first = compile_graph_to_torch(graph)
    second = compile_graph_to_torch(graph)
    assert first.source == second.source
    assert first.template_ids == second.template_ids


TAMPERINGS = [
    "\nimport os\n",
    "\nimport torch as t\n",
    "\nfrom os import system\n",
    "\nx = eval('1 + 1')\n",
    "\nx = __import__('os')\n",
    "\nx = getattr(nn, 'Linear')\n",
    "\nwhile True:\n    pass\n",
    "\ndef sneaky():\n    return 1\n",
    "\nclass Sneaky(nn.Module):\n    pass\n",
    "\nGLOBAL = 1\n",
    "\nlambda: 1\n",
    "\ndef broken(:\n",
]


@pytest.mark.parametrize("tampering", TAMPERINGS)
def test_structural_check_rejects_tampered_source(tampering: str) -> None:
    """Every escape from the template surface is caught structurally."""
    graph = make_chain((2, 8), [("linear", {"in_features": 8, "out_features": 4})])
    compiled = compile_graph_to_torch(graph)
    assert check_first_party_source(compiled.source + tampering) != ()


def test_structural_check_rejects_swapped_constructors() -> None:
    """Renaming a constructor to a non-allowlisted symbol fails the check."""
    graph = make_chain((2, 8), [("linear", {"in_features": 8, "out_features": 4})])
    compiled = compile_graph_to_torch(graph)
    swapped = compiled.source.replace("nn.Linear", "nn.Bogus", 1)
    assert check_first_party_source(swapped) != ()
    evil_call = compiled.source.replace(
        "x = self.layer_0(x)",
        "x = print(self.layer_0(x))",
        1,
    )
    assert check_first_party_source(evil_call) != ()
