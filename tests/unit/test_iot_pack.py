"""Tests for the Phase-9 IoT pack: identity, routing, link preflight."""

from bizora.contracts.graph import GraphNode, MethodologyGraph, NodeKind
from bizora.contracts.packs import DomainTag, PartRef, ResolutionLevel
from bizora.contracts.patches import GraphPatch, PatchOperation
from bizora.packs import default_registry, iot
from bizora.packs.base import DomainPack, ProfiledPack


def test_pack_identity_and_version() -> None:
    """The Phase-9 pack keeps its id and bumps to version 2.0.0."""
    assert iot.pack.pack_id == "iot"
    assert iot.pack.pack_version == "2.0.0"
    assert iot.PACK_ID == "iot"
    assert iot.PACK_VERSION == "2.0.0"


def test_pack_satisfies_domain_and_profiled_protocols() -> None:
    """The pack still quacks as a routable, profiled DomainPack."""
    assert isinstance(iot.pack, DomainPack)
    assert isinstance(iot.pack, ProfiledPack)
    assert iot.pack.profile.domain == "iot"


def test_detection_routing_is_preserved() -> None:
    """v1 signals still route to this pack; weak tags still route nowhere."""
    registry = default_registry()
    assert registry.get("iot") is iot.pack
    routed = registry.route((DomainTag(label="esp32"), DomainTag(label="mqtt")))
    assert routed is not None and routed.pack_id == "iot"
    assert registry.route((DomainTag(label="esp32"),)) is None


def test_lexical_behaviors_survive_upgrade() -> None:
    """Exact part matching and the two copilot tools survive Phase 9."""
    resolution = iot.pack.resolve_part(PartRef(raw_text="ESP32 module", part_number="ESP32-WROOM-32"))
    assert resolution.level is ResolutionLevel.EXACT
    assert {tool.tool_name for tool in iot.pack.copilot_tools} == {
        "iot_search_library",
        "iot_preflight",
    }
    assert iot.pack.simulator_adapter_ids == ()


def _sensor_graph() -> MethodologyGraph:
    """Build a one-node graph awaiting a sensor replacement."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Greenhouse monitor with temperature sensing",
        nodes=(
            GraphNode(id="s1", kind=NodeKind.COMPONENT, label="Temperature sensor"),
        ),
        created_by="tester",
    )


def _replace_patch(node_id: str, config: dict[str, object]) -> GraphPatch:
    """Build a replacement patch carrying one candidate node config."""
    return GraphPatch(
        patch_id="patch-1",
        base_graph_id="graph-1",
        base_version=1,
        operation=PatchOperation.REPLACE_NODE,
        target_id=node_id,
        payload={
            "node": {
                "id": node_id,
                "kind": "component",
                "label": "Candidate sensor",
                "config": config,
            }
        },
        rationale="Try the catalog sensor here.",
        requested_by="tester",
    )


def _iot_rules(graph: MethodologyGraph, patch: GraphPatch) -> dict[str, str]:
    """Return rule_id -> message for the pack's own IoT findings."""
    return {
        finding.rule_id: finding.message
        for finding in iot.pack.check_patch(graph, patch)
        if finding.rule_id.startswith("iot_")
    }


def test_preflight_blocks_missing_required_config() -> None:
    """A BME280 swap without its required I2C address is blocked."""
    graph = _sensor_graph()
    patch = _replace_patch("s1", {"model": "BME280"})

    findings = _iot_rules(graph, patch)

    assert "iot_config_required" in findings
    assert "i2c_address" in findings["iot_config_required"]


def test_preflight_accepts_complete_candidate_config() -> None:
    """A fully configured BME280 swap raises no IoT findings."""
    graph = _sensor_graph()
    patch = _replace_patch(
        "s1", {"model": "BME280", "i2c_address": "0x76", "sample_period_s": 60}
    )

    assert _iot_rules(graph, patch) == {}


def test_preflight_blocks_wrong_config_types() -> None:
    """Enum and number fields reject values of the wrong type."""
    graph = _sensor_graph()

    enum_typed = _iot_rules(graph, _replace_patch("s1", {"model": "BME280", "i2c_address": 118}))
    assert "iot_config_type" in enum_typed

    number_typed = _iot_rules(
        graph,
        _replace_patch("s1", {"model": "BME280", "i2c_address": "0x76", "sample_period_s": "fast"}),
    )
    assert "iot_config_type" in number_typed


def test_preflight_blocks_unknown_enum_option() -> None:
    """An I2C address outside the SDO options is blocked."""
    graph = _sensor_graph()
    patch = _replace_patch("s1", {"model": "BME280", "i2c_address": "0x75"})

    findings = _iot_rules(graph, patch)

    assert "iot_config_enum" in findings


def test_preflight_blocks_shared_gpio_pins() -> None:
    """Trig and echo on the same pin cannot work; distinct pins are clear."""
    graph = _sensor_graph()

    shared = _iot_rules(
        graph, _replace_patch("s1", {"model": "HC-SR04", "trig_gpio": 5, "echo_gpio": 5})
    )
    assert "iot_gpio_distinct" in shared

    distinct = _iot_rules(
        graph, _replace_patch("s1", {"model": "HC-SR04", "trig_gpio": 5, "echo_gpio": 18})
    )
    assert distinct == {}


def test_preflight_skips_unidentifiable_candidates() -> None:
    """Without a catalog match the pack adds no findings of its own."""
    graph = _sensor_graph()
    patch = _replace_patch("s1", {"model": "Mystery Widget 9000"})

    assert _iot_rules(graph, patch) == {}


def test_preflight_ignores_non_replacement_patches() -> None:
    """Config-only edits never trigger candidate-config rules."""
    graph = _sensor_graph()
    patch = GraphPatch(
        patch_id="patch-2",
        base_graph_id="graph-1",
        base_version=1,
        operation=PatchOperation.UPDATE_NODE_CONFIG,
        target_id="s1",
        payload={"config": {"sample_period_s": 30}},
        rationale="Retune the existing node.",
        requested_by="tester",
    )

    assert _iot_rules(graph, patch) == {}
