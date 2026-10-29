"""Unit tests for the paper-agnostic entity registry."""

from bizora.core.entity_registry import (
    DomainProfile,
    check_compatible,
    detect_domain,
    resolve_generic,
    resolve_node,
)
from bizora.packs import ProfiledPack, default_registry

REGISTRY = default_registry()


def profile(pack_id: str) -> DomainProfile:
    """Return the detection profile for one built-in pack."""
    pack = REGISTRY.get(pack_id)
    assert isinstance(pack, ProfiledPack)
    return pack.profile


def test_detect_domain_matches_keyword_signals() -> None:
    """Detection returns the domain whose signals the graph text carries."""
    classification = detect_domain(
        "NBTI aging in 6T SRAM",
        "Body-bias compensation reduces leakage.",
        (("6T SRAM cell", None, "component", {}),),
        REGISTRY,
    )

    assert classification.domain == "electronics"
    assert classification.confidence > 0
    assert "sram" in classification.signals


def test_detect_domain_returns_generic_without_signals() -> None:
    """Text without registry signals classifies as generic, never a guess."""
    classification = detect_domain(
        "A generic widget study",
        "Widgets are processed generically.",
        (("Widget", None, "operation", {}),),
        REGISTRY,
    )

    assert classification.domain == "generic"
    assert classification.confidence == 0.0
    assert classification.signals == ()


def test_detect_domain_needs_two_distinct_signals() -> None:
    """A single stray keyword stays below the detection threshold."""
    classification = detect_domain(
        "A study of something",
        "",
        (("Sensor", None, "component", {}),),
        REGISTRY,
    )

    assert classification.domain == "generic"


def test_detect_domain_prefers_model_label() -> None:
    """A valid model-produced label wins over lexical signals."""
    classification = detect_domain(
        "NBTI aging in 6T SRAM",
        "Body-bias compensation reduces leakage.",
        (("6T SRAM cell", None, "component", {}),),
        REGISTRY,
        domain_hint="iot",
    )

    assert classification.domain == "iot"
    assert classification.signals == ("model-label",)


def test_detect_domain_ignores_unregistered_model_label() -> None:
    """An unknown model label falls back to lexical detection."""
    classification = detect_domain(
        "NBTI aging in 6T SRAM",
        "Body-bias compensation reduces leakage.",
        (("6T SRAM cell", None, "component", {}),),
        REGISTRY,
        domain_hint="hardware-security",
    )

    assert classification.domain == "electronics"
    assert "sram" in classification.signals


def test_resolve_node_matches_entity_type_and_records_terms() -> None:
    """A temperature sensor resolves to the sensor-module entity type."""
    resolution = resolve_node(
        profile("iot"), "temp", "Temperature sensor", None, "component", {}
    )

    assert resolution.entity_type == "sensor-module"
    assert resolution.domain == "iot"
    assert resolution.generic is False
    assert "temperature" in resolution.matched_terms
    assert resolution.confidence > 0


def test_resolve_node_exact_identity_from_config() -> None:
    """A config model key pins the exact identity into the display label."""
    resolution = resolve_node(
        profile("iot"),
        "mcu",
        "Microcontroller",
        None,
        "component",
        {"model": "ESP32"},
    )

    assert resolution.entity_type == "microcontroller"
    assert resolution.display_label == "ESP32"


def test_resolve_node_prefers_label_over_description_words() -> None:
    """A coordinator serving clients resolves as a coordinator, not a client."""
    resolution = resolve_node(
        profile("distributed-systems"),
        "coord",
        "Coordinator",
        "Coordinator that routes client requests to workers.",
        "component",
        {},
    )

    assert resolution.entity_type == "coordinator"
    assert "coordinator" in resolution.matched_terms


def test_resolve_node_dedups_overlapping_terms() -> None:
    """The stem cli inside client counts once, not twice."""
    resolution = resolve_node(
        profile("distributed-systems"), "cli", "Client", None, "input", {}
    )

    assert resolution.entity_type == "client"
    assert resolution.matched_terms == ("client",)


def test_resolve_node_prefers_longer_term_on_label_tie() -> None:
    """Demodulator beats modulator: the longer term is more specific."""
    resolution = resolve_node(
        profile("signal-processing"),
        "demod",
        "Demodulator",
        None,
        "operation",
        {},
    )

    assert resolution.entity_type == "demodulator"


def test_resolve_node_routes_process_kinds_apart_from_text() -> None:
    """A dataset stays a dataset even when its text names instruments."""
    resolution = resolve_node(
        profile("electronics"),
        "ds",
        "Dataset",
        "CRP measurements from the probe station for evaluation",
        "dataset",
        {},
    )

    assert resolution.entity_type == "dataset"
    assert resolution.physical is False
    assert resolution.symbol == "dataset"
    assert resolution.model_3d is None
    assert resolution.category == "process"
    assert resolution.generic is False
    assert resolution.confidence == 1.0


def test_resolve_node_routes_every_process_kind() -> None:
    """Operations, evaluations, losses, optimizers, and preprocessing agree."""
    for kind in ("operation", "evaluation", "loss", "optimizer", "preprocessing"):
        resolution = resolve_node(
            profile("electronics"), "n", "Some node", "VDD supply transistor", kind, {}
        )

        assert resolution.entity_type == kind, kind
        assert resolution.physical is False, kind
        assert resolution.generic is False, kind


def test_resolve_node_keeps_ambiguous_kinds_text_matched() -> None:
    """Inputs and models still resolve by text: a supply input is hardware."""
    resolution = resolve_node(
        profile("electronics"), "in", "Input", "VDD supply rail", "input", {}
    )

    assert resolution.entity_type == "voltage-source"
    assert resolution.physical is True


def test_resolve_node_ignores_prose_mentions_without_label_anchor() -> None:
    """A process node stays generic when only its long description names a part."""
    resolution = resolve_node(
        profile("electronics"),
        "fab",
        "65nm CMOS Fabrication",
        "Standard 65nm CMOS process implementation with bitcell area 4.38 um2",
        "component",
        {},
    )

    assert resolution.entity_type == "generic-component"
    assert resolution.generic is True
    assert resolution.matched_terms == ()


def test_resolve_node_accepts_config_stated_identity() -> None:
    """Config-declared identity anchors a match the label does not state."""
    resolution = resolve_node(
        profile("electronics"),
        "cell",
        "Array site",
        "One site of a large memory array with shared periphery circuits",
        "component",
        {"cell_type": "6T SRAM"},
    )

    assert resolution.entity_type == "memory-cell"
    assert resolution.generic is False


def test_resolve_node_ignores_config_keys_naming_measurements() -> None:
    """A config key reporting bitcell area does not make a fab node a cell."""
    resolution = resolve_node(
        profile("electronics"),
        "fab",
        "65nm CMOS Fabrication",
        "Standard 65nm CMOS process implementation with measured areas",
        "component",
        {"technology_nm": 65, "bitcell_area_um2": 4.38},
    )

    assert resolution.entity_type == "generic-component"
    assert resolution.generic is True


def test_resolve_node_matches_terms_across_spacing_variants() -> None:
    """Spaced, hyphenated, and joined spellings identify the same entity."""
    for label in ("Bit Cell Cross-Coupled Pair", "Bit-Cell Array", "Bitcell"):
        resolution = resolve_node(
            profile("electronics"), "cell", label, None, "component", {}
        )

        assert resolution.entity_type == "memory-cell", label
        assert resolution.generic is False, label


def test_resolve_node_requires_label_coverage_for_process_escape() -> None:
    """One shared word does not promote an operation into a physical part."""
    resolution = resolve_node(
        profile("electronics"),
        "comp",
        "CTAT/PTAT Temperature Compensation Sizing",
        "Optimization of transistor sizes via Monte Carlo simulations",
        "operation",
        {},
    )

    assert resolution.entity_type == "operation"
    assert resolution.physical is False
    assert resolution.generic is False


def test_resolve_node_carries_pack_render_declaration() -> None:
    """Matched resolutions carry the pack's physicality, symbol, and model."""
    resolution = resolve_node(
        profile("iot"), "temp", "Temperature sensor", None, "component", {}
    )

    assert resolution.physical is True
    assert resolution.symbol == "sensor"
    assert resolution.model_3d is None


def test_generic_fallbacks_stay_visible_physical() -> None:
    """Unknown nodes keep a physical placeholder, never vanish or fake a part."""
    resolution = resolve_node(
        profile("electronics"), "x", "Xyzzq widget", None, "component", {}
    )

    assert resolution.generic is True
    assert resolution.physical is True
    assert resolution.symbol == "generic"
    assert resolution.model_3d is None


def test_resolve_node_falls_back_to_generic_component() -> None:
    """An unmatched node resolves to an explicit generic fallback."""
    resolution = resolve_node(
        profile("iot"), "odd", "Whirligig widget", None, "component", {}
    )

    assert resolution.entity_type == "generic-component"
    assert resolution.generic is True
    assert resolution.confidence == 0.0
    assert resolution.interfaces == ()


def test_resolve_generic_is_honest_unknown() -> None:
    """The generic resolver never fabricates an entity type."""
    resolution = resolve_generic("n1", "Mystery node")

    assert resolution.domain == "generic"
    assert resolution.entity_type == "generic-component"
    assert resolution.generic is True


def test_check_compatible_accepts_matching_format_swap() -> None:
    """NF4 and FP16 share the quantization-format interfaces, so they swap."""
    old = resolve_node(
        profile("quantization"), "nf4", "NF4 quantization", None, "operation", {}
    )
    new = resolve_node(
        profile("quantization"), "nf4", "FP16 conversion", None, "operation", {}
    )

    assert old.entity_type == "quant-format" == new.entity_type
    compatibility = check_compatible(old, new, ("e1",))

    assert compatibility.compatible is True
    assert compatibility.missing_interfaces == ()
    assert compatibility.incident_edge_ids == ("e1",)


def test_check_compatible_blocks_dropped_known_interface() -> None:
    """Swapping a microcontroller for a sensor drops gpio and is rejected."""
    old = resolve_node(
        profile("iot"), "mcu", "ESP32 microcontroller", None, "component", {}
    )
    new = resolve_node(
        profile("iot"), "mcu", "Temperature sensor", None, "component", {}
    )

    assert old.entity_type == "microcontroller"
    assert new.entity_type == "sensor-module"
    compatibility = check_compatible(old, new, ("e1", "e2"))

    assert compatibility.compatible is False
    assert compatibility.incident_edge_ids == ("e1", "e2")
    assert any(missing.kind == "gpio" for missing in compatibility.missing_interfaces)


def test_check_compatible_never_blocks_generic() -> None:
    """Unknown interfaces never block a replacement."""
    old = resolve_generic("n1", "Mystery node")
    new = resolve_node(
        profile("iot"), "n1", "ESP32 microcontroller", None, "component", {}
    )

    assert check_compatible(old, new, ()).compatible is True
    assert check_compatible(new, old, ()).compatible is True
