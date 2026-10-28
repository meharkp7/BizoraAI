"""Tests for assumed-claim marking contracts and helpers.

All graphs and nodes below are clearly-marked fakes built by the
``make_fake_*`` helpers. No network calls, no live providers.
"""

import pytest
from pydantic import ValidationError

from bizora.contracts.assumptions import (
    ASSUMED_CONFIG_KEY,
    ASSUMPTION_REASON_CONFIG_KEY,
    DEFAULT_ASSUMPTION_REASON,
    MAX_ASSUMPTION_REASON_LENGTH,
    AssumedComponent,
    AssumedPart,
    AssumptionFlag,
    annotate_graph,
    assumption_config,
    assumption_reason,
    clear_assumed,
    edge_is_assumed,
    ensure_explicit_edge,
    ensure_explicit_node,
    is_assumed,
    mark_assumed,
    node_assumption_reason,
    node_is_assumed,
    strip_assumption,
    summarize_assumptions,
)
from bizora.contracts.evidence import EvidenceRef, EvidenceStatus, Provenance
from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
    RelationKind,
)


def make_fake_node(
    node_id: str = "fake-node",
    *,
    evidence: tuple[EvidenceRef, ...] = (),
    provenance: Provenance = Provenance.UNRESOLVED,
    config: dict[str, object] | None = None,
) -> GraphNode:
    """Fake fixture: one extracted component with caller-chosen grounding."""
    return GraphNode(
        id=node_id,
        kind=NodeKind.COMPONENT,
        label=f"Fake component {node_id}",
        config=dict(config) if config else {},
        evidence=evidence,
        provenance=provenance,
    )


def make_fake_evidence() -> EvidenceRef:
    """Fake fixture: one evidence pointer to a fake source page."""
    return EvidenceRef(
        source_id="fake-paper",
        page=3,
        quote="The fake widget processes the input.",
        status=EvidenceStatus.SUPPORTED,
    )


def make_fake_graph(nodes: tuple[GraphNode, ...]) -> MethodologyGraph:
    """Fake fixture: one draft revision holding the given fake nodes."""
    return MethodologyGraph(
        schema_version="1.0",
        project_id="fake-project",
        graph_id="fake-graph",
        version=1,
        title="Fake methodology",
        source_ids=("fake-paper",),
        nodes=nodes,
        edges=(),
        created_by="fake-user",
    )


def test_assumption_flag_requires_reason_iff_assumed() -> None:
    assert AssumptionFlag(assumed=True, reason="fake reason").assumed is True
    assert AssumptionFlag(assumed=False, reason=None).assumed is False

    with pytest.raises(ValidationError):
        AssumptionFlag(assumed=True, reason=None)
    with pytest.raises(ValidationError):
        AssumptionFlag(assumed=True, reason="   ")
    with pytest.raises(ValidationError):
        AssumptionFlag(assumed=False, reason="stale fake reason")
    with pytest.raises(ValidationError):
        AssumptionFlag(assumed=True, reason="x" * (MAX_ASSUMPTION_REASON_LENGTH + 1))


def test_assumed_component_and_part_models() -> None:
    component = AssumedComponent(
        node_id="fake-node", assumed=True, reason="fake reason", confidence=0.4
    )
    assert component.node_id == "fake-node"
    assert component.confidence == pytest.approx(0.4)

    part = AssumedPart(
        reference="fake part mention",
        part_number=None,
        assumed=True,
        reason="fake reason",
    )
    assert part.reference == "fake part mention"

    with pytest.raises(ValidationError):
        AssumedComponent(node_id="fake-node", assumed=True, reason=None)
    with pytest.raises(ValidationError):
        AssumedPart(reference="fake part mention", assumed=False, reason="stale")


def test_config_mapping_helpers() -> None:
    assert is_assumed({ASSUMED_CONFIG_KEY: True}) is True
    assert is_assumed({}) is False
    assert is_assumed({ASSUMED_CONFIG_KEY: False}) is False
    # Only an explicit boolean true counts; truthy lookalikes do not.
    assert is_assumed({ASSUMED_CONFIG_KEY: 1}) is False
    assert is_assumed({ASSUMED_CONFIG_KEY: "yes"}) is False

    assert assumption_reason(assumption_config("fake reason")) == "fake reason"
    assert assumption_reason({}) is None
    assert assumption_reason({ASSUMPTION_REASON_CONFIG_KEY: "  "}) is None

    marked = {"setting": "kept", **assumption_config("fake reason")}
    stripped = strip_assumption(marked)
    assert stripped == {"setting": "kept"}
    assert marked[ASSUMED_CONFIG_KEY] is True  # input mapping untouched


def test_node_helpers_read_flags() -> None:
    assert node_is_assumed(make_fake_node()) is False
    assert node_assumption_reason(make_fake_node()) is None

    marked = mark_assumed(make_fake_node(), "fake reason")
    assert node_is_assumed(marked) is True
    assert node_assumption_reason(marked) == "fake reason"


def test_mark_assumed_upgrades_unresolved_provenance_only() -> None:
    marked = mark_assumed(make_fake_node(), "fake reason")
    assert marked.provenance == Provenance.INFERRED
    assert marked.confidence is None

    extracted = make_fake_node(provenance=Provenance.EXTRACTED)
    kept = mark_assumed(extracted, "fake reason", confidence=0.25)
    assert kept.provenance == Provenance.EXTRACTED
    assert kept.confidence == pytest.approx(0.25)


def test_mark_assumed_never_fails_on_reason_text() -> None:
    blank = mark_assumed(make_fake_node(), "   ")
    assert node_assumption_reason(blank) == DEFAULT_ASSUMPTION_REASON

    long_reason = "r" * (MAX_ASSUMPTION_REASON_LENGTH + 50)
    truncated = mark_assumed(make_fake_node(), long_reason)
    stored = node_assumption_reason(truncated)
    assert stored is not None
    assert len(stored) <= MAX_ASSUMPTION_REASON_LENGTH


def test_clear_assumed_removes_marking_and_verifies() -> None:
    marked = mark_assumed(make_fake_node(config={"setting": "kept"}), "fake reason")
    cleared = clear_assumed(marked)
    assert node_is_assumed(cleared) is False
    assert node_assumption_reason(cleared) is None
    assert cleared.config == {"setting": "kept"}
    assert cleared.provenance == Provenance.VERIFIED

    custom = clear_assumed(marked, provenance=Provenance.EXTRACTED)
    assert custom.provenance == Provenance.EXTRACTED


def test_ensure_explicit_node_marks_only_ungrounded_claims() -> None:
    evidenced = make_fake_node(evidence=(make_fake_evidence(),))
    assert ensure_explicit_node(evidenced) == evidenced

    already = mark_assumed(make_fake_node(), "fake provider reason")
    assert ensure_explicit_node(already) == already

    bare = make_fake_node()
    marked = ensure_explicit_node(bare)
    assert node_is_assumed(marked) is True
    assert node_assumption_reason(marked) == DEFAULT_ASSUMPTION_REASON
    assert marked.provenance == Provenance.INFERRED

    # A flag without a usable reason is repaired, not dropped.
    broken = make_fake_node(config={ASSUMED_CONFIG_KEY: True})
    repaired = ensure_explicit_node(broken)
    assert node_assumption_reason(repaired) == DEFAULT_ASSUMPTION_REASON

    # Idempotent: annotating twice changes nothing further.
    assert ensure_explicit_node(marked) == marked


def test_edge_marking_uses_inferred_provenance() -> None:
    bare = GraphEdge(id="fake-edge", source="a", target="b")
    assert edge_is_assumed(bare) is False
    marked = ensure_explicit_edge(bare)
    assert marked.provenance == Provenance.INFERRED
    assert edge_is_assumed(marked) is True
    assert ensure_explicit_edge(marked) == marked

    evidenced = GraphEdge(
        id="fake-edge-2",
        source="a",
        target="b",
        relation=RelationKind.DATA_FLOW,
        evidence=(make_fake_evidence(),),
        provenance=Provenance.EXTRACTED,
    )
    assert ensure_explicit_edge(evidenced) == evidenced
    assert edge_is_assumed(evidenced) is False


def test_annotate_graph_marks_all_claims_and_preserves_identity() -> None:
    evidenced = make_fake_node(
        "fake-evidenced",
        evidence=(make_fake_evidence(),),
        provenance=Provenance.EXTRACTED,
    )
    graph = make_fake_graph((evidenced, make_fake_node("fake-bare")))
    annotated = annotate_graph(graph)

    assert annotated.project_id == graph.project_id
    assert annotated.graph_id == graph.graph_id
    assert annotated.version == graph.version
    assert annotated.parent_version == graph.parent_version
    assert annotated.nodes[0] == evidenced
    assert node_is_assumed(annotated.nodes[1]) is True
    assert node_assumption_reason(annotated.nodes[1]) == DEFAULT_ASSUMPTION_REASON

    # Idempotent across the whole graph.
    assert annotate_graph(annotated) == annotated


def test_summarize_assumptions_reports_r2_coverage() -> None:
    evidenced = make_fake_node("fake-evidenced", evidence=(make_fake_evidence(),))
    assumed = mark_assumed(make_fake_node("fake-assumed"), "fake reason")
    graph = make_fake_graph((evidenced, assumed, make_fake_node("fake-bare")))

    before = summarize_assumptions(graph)
    assert before.total_nodes == 3
    assert before.assumed_nodes == 1
    assert before.evidenced_nodes == 1
    assert before.unmarked_nodes == 1
    assert before.complete is False

    after = summarize_assumptions(annotate_graph(graph))
    assert after.unmarked_nodes == 0
    assert after.complete is True


def test_default_reason_names_no_domain_paper_or_part() -> None:
    assert DEFAULT_ASSUMPTION_REASON == ("Not stated in the source; confirm or correct this claim.")
