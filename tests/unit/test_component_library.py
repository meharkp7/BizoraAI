"""Catalog integrity, search, preflight, and copilot behavior."""

import pytest
from tests.unit.test_entities_api import load_fixture_payload

from bizora.contracts.components import ComponentDetail
from bizora.contracts.graph import MethodologyGraph
from bizora.core.component_catalog import (
    CATALOG,
    get_component,
    list_categories,
    list_domains,
    search_components,
)
from bizora.core.component_service import build_replacement_node, preflight_replacement
from bizora.core.copilot_service import answer_copilot
from bizora.core.entity_registry import DomainProfile
from bizora.core.errors import BizoraError
from bizora.packs import ProfiledPack, default_registry


def load_graph(name: str) -> MethodologyGraph:
    return MethodologyGraph.model_validate(load_fixture_payload(name))


def pack_profile(pack_id: str) -> DomainProfile:
    """Return the detection profile for one built-in pack."""
    pack = default_registry().get(pack_id)
    assert isinstance(pack, ProfiledPack)
    return pack.profile


def test_catalog_entries_link_to_registry_types() -> None:
    """Every entry names a real domain and entity type; exact parts have numbers."""
    assert len(CATALOG) >= 50
    for detail in CATALOG.values():
        profile = pack_profile(detail.domain)
        assert detail.entity_type in {entity.type_id for entity in profile.entity_types}
        if not detail.generic:
            assert detail.part_number
        ComponentDetail.model_validate(detail.model_dump(mode="json"))


def test_search_ranks_part_numbers_and_filters_identity() -> None:
    """Part-number queries surface exact parts; generic filter excludes them."""
    hits = search_components("2N3904")
    assert hits[0].component_id == "npn-2n3904"
    assert not hits[0].generic

    generics = search_components("transistor", domain="electronics", generic=True)
    assert generics
    assert all(summary.generic for summary in generics)
    assert all(summary.domain == "electronics" for summary in generics)


def test_search_supports_category_filter() -> None:
    """Category filters narrow results to one visual archetype."""
    hits = search_components("", domain="electronics", category="passive")
    assert hits
    assert all(summary.category == "passive" for summary in hits)
    assert "passive" in list_categories("electronics")
    assert "electronics" in list_domains()


def test_catalog_entries_carry_entity_symbols() -> None:
    """Every entry projects its entity type's pack-declared symbol."""
    assert len(CATALOG) >= 50
    for detail in CATALOG.values():
        profile = pack_profile(detail.domain)
        expected = next(
            entity.symbol for entity in profile.entity_types if entity.type_id == detail.entity_type
        )
        assert detail.symbol == expected, detail.component_id
    hits = search_components("2N3904")
    assert hits[0].symbol == "transistor"


def test_preflight_approves_transistor_replacement() -> None:
    """2N3904 keeps the access-transistor interfaces and preserves edges."""
    graph = load_graph("sram")
    preflight = preflight_replacement(graph, "access-transistors", "npn-2n3904")

    assert preflight.compatible
    assert preflight.missing_interfaces == ()
    assert preflight.preserved_edge_ids == ()
    assert preflight.candidate.entity_type == "transistor"

    cell = preflight_replacement(graph, "sram-cell", "sram-6t-generic")
    assert cell.compatible
    assert set(cell.preserved_edge_ids) == {"e-cell-sense", "e-bias-cell"}


def test_preflight_notes_generic_to_exact_upgrade() -> None:
    """Pinning a generic placeholder to an exact part is called out."""
    graph = MethodologyGraph.model_validate(
        {
            "schema_version": "1.0",
            "project_id": "probe",
            "graph_id": "probe",
            "version": 1,
            "title": "Untitled assembly",
            "source_ids": [],
            "nodes": [{"id": "widget", "kind": "component", "label": "Widget"}],
            "edges": [],
            "created_by": "test",
        }
    )
    preflight = preflight_replacement(graph, "widget", "npn-2n3904")

    assert preflight.compatible
    assert any(w.code == "info_identity_upgrade" for w in preflight.warnings)


def test_preflight_rejects_interface_dropping_swap() -> None:
    """A voltage source cannot replace a sense amplifier: data/sense drop."""
    graph = load_graph("sram")
    preflight = preflight_replacement(graph, "sense-amplifier", "psu-vdd-generic")

    assert not preflight.compatible
    kinds = {missing.kind for missing in preflight.missing_interfaces}
    assert {"data", "analog"} <= kinds


def test_preflight_merges_configuration_and_checks_supply() -> None:
    """Component defaults merge with overrides; out-of-range rails warn."""
    graph = load_graph("sram")
    target = next(node for node in graph.nodes if node.id == "bias-control")
    detail = get_component("ic-ne555")
    assert detail is not None
    node = build_replacement_node(target, detail, {"mode": "monostable"})

    assert node.id == "bias-control"
    assert node.config["mode"] == "monostable"
    assert node.config["part"] == "NE555"
    assert node.evidence == target.evidence

    preflight = preflight_replacement(graph, "bias-control", "ic-lm358", {"supply_V": 48})
    assert any(w.code == "supply_above_maximum" for w in preflight.warnings)


def test_preflight_rejects_unknown_node_and_component() -> None:
    """Unknown nodes and components report not-found instead of guessing."""
    graph = load_graph("sram")
    with pytest.raises(BizoraError):
        preflight_replacement(graph, "no-such-node", "npn-2n3904")
    with pytest.raises(BizoraError):
        preflight_replacement(graph, "sram-cell", "no-such-component")


def test_preflight_rejects_invalid_configuration() -> None:
    """Enum violations fail before any revision is created."""
    graph = load_graph("quant")
    with pytest.raises(BizoraError):
        preflight_replacement(graph, "nf4-quantizer", "format-gptq", {"bits": "16"})


def test_preflight_supports_quant_and_signal_replacements() -> None:
    """The same architecture validates NF4->FP16 and modulator swaps."""
    quant = load_graph("quant")
    fp16 = preflight_replacement(quant, "nf4-quantizer", "format-fp16")
    assert fp16.compatible
    assert fp16.candidate.entity_type == "quant-format"

    signal = load_graph("signal")
    psk = preflight_replacement(signal, "modulator", "sig-modulator-psk")
    assert psk.compatible
    assert psk.candidate.entity_type == "modulator"


def test_copilot_finds_components() -> None:
    """Find queries return matching library cards."""
    response = answer_copilot(load_graph("sram"), "find NPN transistor")

    assert "2N3904" in response.reply
    assert response.proposal is None
    assert any(card.kind == "component" for card in response.cards)


def test_copilot_compares_two_components() -> None:
    """Compare queries render a spec comparison card."""
    response = answer_copilot(load_graph("quant"), "compare NF4 vs FP16")

    assert len(response.cards) == 1
    assert response.cards[0].kind == "comparison"
    assert "Bits per weight" in response.cards[0].body


def test_copilot_proposes_compatible_replacement() -> None:
    """Replace queries validate and propose without applying anything."""
    graph = load_graph("sram")
    response = answer_copilot(
        graph, "replace access-transistors with 2N3904", selected_node_id=None
    )

    assert response.proposal is not None
    assert response.proposal.node_id == "access-transistors"
    assert response.proposal.component_id == "npn-2n3904"
    assert response.proposal.config["part"] == "2N3904"


def test_copilot_refuses_incompatible_replacement() -> None:
    """Incompatible swaps explain the missing interfaces with no proposal."""
    response = answer_copilot(load_graph("sram"), "replace sense-amplifier with psu-vdd-generic")

    assert response.proposal is None
    assert "not compatible" in response.reply


def test_copilot_proposes_configuration_change() -> None:
    """Set queries build config proposals against the selected node."""
    graph = load_graph("signal")
    response = answer_copilot(graph, "set sampling_rate_hz to 16000", selected_node_id="sampler")

    assert response.proposal is not None
    assert response.proposal.node_id == "sampler"
    assert response.proposal.config["sampling_rate_hz"] == 16000


def test_copilot_explains_execution_support_honestly() -> None:
    """Run questions name the connected adapter and unsupported simulators."""
    response = answer_copilot(load_graph("sram"), "can you simulate this circuit?")

    assert "bizora.deterministic-test" in response.reply
    assert "not connected" in response.reply
