from collections.abc import Sequence

from bizora.contracts.evidence import EvidenceRef, Provenance
from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
    ResearchBrief,
    validate_graph,
)


def make_graph(*, nodes: Sequence[GraphNode] | None = None, edges: Sequence[GraphEdge] | None = None, source_ids: tuple[str, ...] = ("paper-1",),) -> MethodologyGraph:
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Vision transformer",
        source_ids=source_ids,
        nodes=tuple(nodes or [
            GraphNode(id="input", kind=NodeKind.INPUT, label="Image", provenance=Provenance.VERIFIED),
            GraphNode(
                id="encoder", kind=NodeKind.MODEL, label="Transformer encoder",
                evidence=(EvidenceRef(source_id="paper-1", page=4, quote="Transformer encoder"),),
                provenance=Provenance.EXTRACTED,
            ),
            GraphNode(id="output", kind=NodeKind.OUTPUT, label="Logits"),
        ]),
        edges=tuple(edges or [
            GraphEdge(id="e1", source="input", target="encoder"),
            GraphEdge(id="e2", source="encoder", target="output"),
        ]),
        created_by="test",
    )


def test_valid_graph_passes() -> None:
    assert validate_graph(make_graph()) == []


def test_missing_edge_endpoint_is_rejected_by_validator() -> None:
    graph = make_graph(edges=[GraphEdge(id="e1", source="input", target="missing")])
    assert any("missing target node 'missing'" in error for error in validate_graph(graph))


def test_cycle_is_rejected_for_feed_forward_profile() -> None:
    graph = make_graph(edges=[
        GraphEdge(id="e1", source="input", target="encoder"),
        GraphEdge(id="e2", source="encoder", target="input"),
    ])
    assert any("contains a cycle" in error for error in validate_graph(graph, require_dag=True))


def test_cycle_is_accepted_by_default() -> None:
    graph = make_graph(edges=[
        GraphEdge(id="e1", source="input", target="encoder"),
        GraphEdge(id="e2", source="encoder", target="input"),
    ])
    assert validate_graph(graph) == []


def test_evidence_must_reference_declared_source() -> None:
    graph = make_graph(source_ids=("paper-2",))
    assert any("undeclared source 'paper-1'" in error for error in validate_graph(graph))


def test_brief_defaults_to_unknown() -> None:
    assert make_graph().brief is None


def test_brief_round_trip() -> None:
    graph = make_graph()
    with_brief = graph.model_copy(
        update={
            "brief": ResearchBrief(
                problem="Low SRAM yield.",
                objectives=("Raise yield",),
                findings=("Yield rose 5%.",),
                limitations=(),
            )
        }
    )

    assert with_brief.brief is not None
    assert with_brief.brief.problem == "Low SRAM yield."
    assert with_brief.brief.objectives == ("Raise yield",)
    assert with_brief.brief.limitations == ()
    assert validate_graph(with_brief) == []


def test_component_kind_is_supported() -> None:
    node = GraphNode(id="sense-amp", kind=NodeKind.COMPONENT, label="Sense amplifier")

    assert node.kind == "component"
