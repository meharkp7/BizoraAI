"""Contract tests for domain tags and the pack interface (Phase 2 slice).

The toy pack below lives in test code on purpose: it proves a new pack
registers and routes with zero changes to core code, as R4 requires.
"""

import pytest
from pydantic import ValidationError

from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.packs import (
    CopilotToolSpec,
    DomainTag,
    PackPreflightFinding,
    PackPreflightSeverity,
    PackVocabulary,
    PartRef,
    PartResolution,
    RenderSpec,
    ResolutionConfidence,
    ResolutionLevel,
    normalize_tag_label,
)
from bizora.contracts.patches import GraphPatch
from bizora.packs.base import DomainPack, PackRegistry


class ToyPack:
    """Minimal pack used only to exercise the interface contract."""

    pack_id = "toy-widgets"
    pack_version = "0.1.0"

    @property
    def vocabulary(self) -> PackVocabulary:
        from bizora.contracts.packs import PackComponentKind

        return PackVocabulary(kinds=(PackComponentKind(kind_id="widget", display_label="Widget"),))

    @property
    def simulator_adapter_ids(self) -> tuple[str, ...]:
        return ()

    @property
    def copilot_tools(self) -> tuple[CopilotToolSpec, ...]:
        return (CopilotToolSpec(tool_name="lookup_widget", description="Look up a widget."),)

    def detect(self, tags: tuple[DomainTag, ...]) -> float:
        return 0.9 if any(tag.label == "toy widgets" for tag in tags) else 0.0

    def resolve_part(self, ref: PartRef) -> PartResolution:
        if ref.part_number == "W-1":
            return PartResolution(
                level=ResolutionLevel.EXACT,
                confidence=ResolutionConfidence.FROM_PAPER,
                pack_id=self.pack_id,
                kind_id="widget",
                asset_key="toy/w-1",
                reason="Exact part number from the paper text.",
            )
        return PartResolution(
            level=ResolutionLevel.UNRESOLVED,
            confidence=ResolutionConfidence.ASSUMED,
            pack_id=self.pack_id,
            reason=f"No widget matches {ref.raw_text!r}.",
        )

    def render_spec(self, resolution: PartResolution) -> RenderSpec:
        return RenderSpec(
            label="Toy widget",
            asset_uri=None,
            fallback_package="widget-illustrative",
            illustrative=True,
        )

    def check_patch(
        self, graph: MethodologyGraph, patch: GraphPatch
    ) -> tuple[PackPreflightFinding, ...]:
        return ()


def test_domain_tags_accept_open_vocabulary() -> None:
    """Arbitrary model-produced labels validate; nothing is enumerated."""
    tags = [
        DomainTag(label="embedded IoT"),
        DomainTag(label="analog circuit", confidence=0.7),
        DomainTag(label="vision transformer"),
        DomainTag(label="some future field nobody named yet"),
    ]
    assert [tag.label for tag in tags] == [
        "embedded iot",
        "analog circuit",
        "vision transformer",
        "some future field nobody named yet",
    ]


def test_domain_tag_normalization_and_bounds() -> None:
    """Labels normalize; empty, overlong, and out-of-range values reject."""
    assert normalize_tag_label("  Vision   Transformer ") == "vision transformer"
    assert DomainTag(label="  Analog  Circuit ").label == "analog circuit"
    with pytest.raises(ValidationError):
        DomainTag(label="   ")
    with pytest.raises(ValidationError):
        DomainTag(label="x" * 129)
    with pytest.raises(ValidationError):
        DomainTag(label="ok", confidence=1.5)


def test_resolution_requires_a_reason_and_allows_unresolved() -> None:
    """Unknown parts resolve to UNRESOLVED with a reason, never a guess."""
    resolution = PartResolution(
        level=ResolutionLevel.UNRESOLVED,
        confidence=ResolutionConfidence.ASSUMED,
        pack_id="toy-widgets",
        reason="Nothing in the vocabulary matches.",
    )
    assert resolution.asset_key is None
    with pytest.raises(ValidationError):
        PartResolution(
            level=ResolutionLevel.EXACT,
            confidence=ResolutionConfidence.MATCHED,
            pack_id="toy-widgets",
            reason="",
        )


def test_vocabulary_and_tool_contracts_validate() -> None:
    """Pack data shapes reject empty vocabularies and bad tool names."""
    pack = ToyPack()
    assert isinstance(pack, DomainPack)
    assert pack.vocabulary.kinds[0].kind_id == "widget"
    with pytest.raises(ValidationError):
        PackVocabulary(kinds=())
    with pytest.raises(ValidationError):
        CopilotToolSpec(tool_name="Not A Tool", description="bad name")


def test_registry_routes_to_best_pack_or_explore_only() -> None:
    """A toy pack registers with zero core changes; unknown tags route to None."""
    registry = PackRegistry([ToyPack()])
    assert registry.available() == (("toy-widgets", "0.1.0"),)
    assert registry.get("toy-widgets") is not None
    assert registry.get("nope") is None

    claimed = registry.route((DomainTag(label="toy widgets"),))
    assert claimed is not None and claimed.pack_id == "toy-widgets"
    assert registry.route((DomainTag(label="unrelated field"),)) is None
    assert registry.route(()) is None

    with pytest.raises(ValueError, match="already registered"):
        registry.register(ToyPack())


def test_toy_pack_exercises_full_interface() -> None:
    """Resolve, render, and preflight round-trip through the protocol."""
    pack: DomainPack = ToyPack()
    exact = pack.resolve_part(PartRef(raw_text="W-1 widget", part_number="W-1"))
    assert exact.level is ResolutionLevel.EXACT
    assert exact.confidence is ResolutionConfidence.FROM_PAPER

    missed = pack.resolve_part(PartRef(raw_text="mystery widget"))
    assert missed.level is ResolutionLevel.UNRESOLVED

    spec = pack.render_spec(exact)
    assert spec.illustrative is True

    graph = MethodologyGraph.model_validate(
        {
            "schema_version": "1.0",
            "project_id": "probe",
            "graph_id": "probe",
            "version": 1,
            "title": "Probe",
            "source_ids": [],
            "nodes": [],
            "edges": [],
            "created_by": "test",
        }
    )
    patch = GraphPatch.model_validate(
        {
            "patch_id": "probe-1",
            "base_graph_id": "probe",
            "base_version": 1,
            "operation": "add_node",
            "target_id": "probe",
            "payload": {},
            "rationale": "probe",
            "requested_by": "test",
        }
    )
    assert pack.check_patch(graph, patch) == ()
    assert (
        PackPreflightFinding(
            rule_id="toy-rule",
            severity=PackPreflightSeverity.BLOCK,
            message="Blocked for test.",
        ).severity
        is PackPreflightSeverity.BLOCK
    )
