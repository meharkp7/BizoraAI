"""Tests for the electronics pack and pack-routed core behavior.

The electronics pack is the Phase 2 launch pack: catalog entries and
detection profile moved from the core into pack data, served through
the generic DomainPack harness. These tests pin routing, the resolver
ladder, render specs, and preflight; fixtures may name real parts.
"""

from collections import Counter

from tests.unit.test_entities_api import load_fixture_payload
from tests.unit.test_pack_contracts import ToyPack

from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.packs import (
    DomainTag,
    PartRef,
    ResolutionConfidence,
    ResolutionLevel,
)
from bizora.contracts.patches import GraphPatch, PatchOperation
from bizora.core.component_catalog import CATALOG, get_component
from bizora.core.entity_registry import detect_domain
from bizora.core.entity_service import classify_graph
from bizora.packs import ProfiledPack, default_registry
from bizora.packs.base import DomainPack, PackRegistry
from bizora.packs.electronics import pack as electronics


def load_graph(name: str) -> MethodologyGraph:
    """Load one domain fixture as a validated methodology graph."""
    return MethodologyGraph.model_validate(load_fixture_payload(name))


def test_electronics_pack_implements_the_interface() -> None:
    """The pack satisfies DomainPack and exposes its profile and catalog."""
    assert isinstance(electronics, DomainPack)
    assert isinstance(electronics, ProfiledPack)
    assert electronics.pack_id == "electronics"
    assert electronics.pack_version == "1.0.0"
    assert len(electronics.vocabulary.kinds) == 11
    assert "transistor" in {kind.kind_id for kind in electronics.vocabulary.kinds}
    assert len(electronics.catalog_entries) == 21


def test_pack_copilot_tools_and_simulators_are_honest() -> None:
    """Two valid tool specs ship; no simulator is connected yet."""
    tools = electronics.copilot_tools
    assert len(tools) == 2
    assert {tool.tool_name for tool in tools} == {
        "electronics_search_library",
        "electronics_preflight",
    }
    assert all(tool.description and tool.input_schema for tool in tools)
    # ngspice lands in Phase 5; until then the pack reports no adapters.
    assert electronics.simulator_adapter_ids == ()


def test_default_registry_routes_each_pack_by_tags() -> None:
    """Open-vocabulary tags route to the best pack in fixed order."""
    registry = default_registry()
    assert tuple(pack.pack_id for pack in registry.packs) == (
        "electronics",
        "iot",
        "quantization",
        "signal-processing",
        "distributed-systems",
        "deep-learning",
    )
    cases = {
        "electronics": ("sram", "leakage"),
        "iot": ("microcontroller", "firmware"),
        "quantization": ("nf4", "bitsandbytes"),
        "signal-processing": ("qam", "ofdm"),
        "distributed-systems": ("raft", "quorum"),
        "deep-learning": ("backprop", "pretrain"),
    }
    for pack_id, labels in cases.items():
        routed = registry.route(tuple(DomainTag(label=label) for label in labels))
        assert routed is not None and routed.pack_id == pack_id


def test_routing_falls_back_to_explore_only() -> None:
    """Unknown tags, and single signals below threshold, route nowhere."""
    registry = default_registry()
    assert registry.route((DomainTag(label="some future field"),)) is None
    assert registry.route((DomainTag(label="sram"),)) is None
    assert registry.route(()) is None


def test_routing_to_profile_less_pack_keeps_pack_domain() -> None:
    """A routed pack without a profile still names its domain, with no signals."""
    classification = detect_domain(
        "Toy widgets",
        "A study of toy widgets.",
        (("Toy widgets", None, "component", {}),),
        PackRegistry([ToyPack()]),
    )

    assert classification.domain == "toy-widgets"
    assert classification.confidence > 0
    assert classification.signals == ()


def test_routing_breaks_ties_by_registration_order() -> None:
    """Two packs at equal affinity resolve to the first registered."""
    registry = default_registry()
    routed = registry.route(
        (DomainTag(label="voltage transistor"), DomainTag(label="sensor microcontroller"))
    )
    assert routed is not None and routed.pack_id == "electronics"


def test_fixtures_classify_through_pack_routing() -> None:
    """Every domain fixture still detects its pack-routed domain."""
    expected = {
        "sram": "electronics",
        "iot": "iot",
        "quant": "quantization",
        "signal": "signal-processing",
        "distributed": "distributed-systems",
        "deeplearning": "deep-learning",
    }
    for fixture, domain in expected.items():
        classification = classify_graph(load_graph(fixture))
        assert classification.domain == domain
        assert classification.confidence > 0
        assert classification.signals != ()


def test_resolve_part_exact_match() -> None:
    """A stated part number resolves exactly to its catalog entry."""
    resolution = electronics.resolve_part(
        PartRef(raw_text="2N3904 NPN transistor", part_number="2N3904")
    )

    assert resolution.level is ResolutionLevel.EXACT
    assert resolution.confidence is ResolutionConfidence.FROM_PAPER
    assert resolution.pack_id == "electronics"
    assert resolution.kind_id == "transistor"
    assert resolution.asset_key == "npn-2n3904"


def test_resolve_part_family_and_category_ladder() -> None:
    """Package matches resolve by family; label overlap by category."""
    family = electronics.resolve_part(PartRef(raw_text="NPN transistor", package="TO-92"))

    assert family.level is ResolutionLevel.FAMILY
    assert family.confidence is ResolutionConfidence.MATCHED
    assert family.kind_id == "transistor"

    category = electronics.resolve_part(PartRef(raw_text="NPN transistor"))

    assert category.level is ResolutionLevel.CATEGORY
    assert category.kind_id == "transistor"
    assert category.asset_key == "npn-2n3904"


def test_resolve_part_unknown_is_unresolved_with_reason() -> None:
    """Unknown parts resolve to UNRESOLVED with a reason, never a guess."""
    resolution = electronics.resolve_part(PartRef(raw_text="xyzzy nonexistent"))

    assert resolution.level is ResolutionLevel.UNRESOLVED
    assert resolution.confidence is ResolutionConfidence.ASSUMED
    assert resolution.kind_id is None
    assert resolution.asset_key is None
    assert resolution.reason

    punctuated = electronics.resolve_part(PartRef(raw_text="?!- ..."))
    assert punctuated.level is ResolutionLevel.UNRESOLVED


def test_render_spec_stays_illustrative_without_asset_registry() -> None:
    """Resolved parts pin an asset key; everything renders illustrative."""
    exact = electronics.resolve_part(
        PartRef(raw_text="2N3904 NPN transistor", part_number="2N3904")
    )
    spec = electronics.render_spec(exact)

    assert spec.label == "Transistor"
    assert spec.asset_uri is None
    assert spec.fallback_package == "npn-2n3904"
    assert spec.illustrative is True

    missed = electronics.resolve_part(PartRef(raw_text="xyzzy nonexistent"))
    unresolved_spec = electronics.render_spec(missed)

    assert unresolved_spec.label == "Unresolved part"
    assert unresolved_spec.illustrative is True


def _replace_patch(target_id: str, node: dict) -> GraphPatch:
    return GraphPatch.model_validate(
        {
            "patch_id": f"patch-{target_id}",
            "base_graph_id": "main",
            "base_version": 1,
            "rationale": "probe",
            "operation": PatchOperation.REPLACE_NODE.value,
            "target_id": target_id,
            "payload": {"node": node},
            "requested_by": "test",
        }
    )


def test_check_patch_blocks_interface_dropping_swap() -> None:
    """A voltage source cannot replace a sense amplifier: data/sense drop."""
    graph = load_graph("sram")
    patch = _replace_patch(
        "sense-amplifier",
        {"id": "sense-amplifier", "kind": "component", "label": "Voltage source"},
    )

    findings = electronics.check_patch(graph, patch)

    assert findings
    assert all(finding.severity.value == "block" for finding in findings)
    assert all(finding.rule_id == "electronics_interface_preserved" for finding in findings)


def test_check_patch_clears_compatible_and_non_replace_edits() -> None:
    """Compatible swaps and other operations return no findings."""
    graph = load_graph("sram")
    compatible = _replace_patch(
        "access-transistors",
        {
            "id": "access-transistors",
            "kind": "component",
            "label": "2N3904 NPN transistor",
            "config": {"part": "2N3904"},
        },
    )
    assert electronics.check_patch(graph, compatible) == ()

    other = GraphPatch.model_validate(
        {
            "patch_id": "patch-add",
            "base_graph_id": "main",
            "base_version": 1,
            "rationale": "probe",
            "operation": PatchOperation.ADD_NODE.value,
            "target_id": "main",
            "payload": {"node": {"id": "new", "kind": "component", "label": "New"}},
            "requested_by": "test",
        }
    )
    assert electronics.check_patch(graph, other) == ()

    missing_target = _replace_patch(
        "no-such-node",
        {"id": "no-such-node", "kind": "component", "label": "Voltage source"},
    )
    assert electronics.check_patch(graph, missing_target) == ()


def test_moved_catalog_preserves_every_part() -> None:
    """All 58 catalog entries survive the move from core to packs."""
    assert len(CATALOG) == 58
    assert Counter(detail.domain for detail in CATALOG.values()) == Counter(
        {
            "electronics": 21,
            "iot": 13,
            "quantization": 9,
            "signal-processing": 8,
            "distributed-systems": 7,
        }
    )
    for component_id in (
        "npn-2n3904",
        "mcu-esp32-wroom32",
        "format-nf4",
        "sig-modulator-psk",
        "svc-client-generic",
    ):
        assert get_component(component_id) is not None
