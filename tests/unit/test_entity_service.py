"""Fixture-driven tests for domain detection and entity resolution."""

import json
from pathlib import Path

import pytest

from bizora.contracts.graph import GraphNode, MethodologyGraph
from bizora.contracts.patches import GraphPatch, PatchOperation
from bizora.core.entity_service import check_replacement, classify_graph, resolve_graph
from bizora.core.errors import BizoraError
from bizora.core.patch_service import GraphPatchService

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "domains"


def load_fixture(name: str) -> MethodologyGraph:
    """Load one domain fixture as a validated methodology graph."""
    payload = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return MethodologyGraph.model_validate(payload)


@pytest.mark.parametrize(
    "fixture,domain",
    [
        ("sram", "electronics"),
        ("iot", "iot"),
        ("quant", "quantization"),
        ("signal", "signal-processing"),
        ("distributed", "distributed-systems"),
        ("deeplearning", "deep-learning"),
    ],
)
def test_fixtures_classify_to_expected_domain(fixture: str, domain: str) -> None:
    """Each scenario fixture detects its own research domain."""
    classification = classify_graph(load_fixture(fixture))

    assert classification.domain == domain
    assert classification.confidence > 0
    assert classification.signals != ()


def test_sram_resolution_identifies_circuit_entities() -> None:
    """SRAM nodes resolve to memory, sensing, and bias entities with terms."""
    entities = resolve_graph(load_fixture("sram"))
    by_node = {entity.node_id: entity for entity in entities.entities}

    assert entities.classification.domain == "electronics"
    assert by_node["sram-cell"].entity_type == "memory-cell"
    assert by_node["sense-amplifier"].entity_type == "sense-amplifier"
    assert by_node["bias-control"].entity_type == "bias-controller"
    assert by_node["leakage-monitor"].entity_type == "measurement"
    assert all(entity.matched_terms for entity in entities.entities)


def test_distributed_resolution_identifies_services_and_storage() -> None:
    """Coordinator, workers, and storage resolve to their own entity types."""
    entities = resolve_graph(load_fixture("distributed"))
    by_node = {entity.node_id: entity for entity in entities.entities}

    assert by_node["clients"].entity_type == "client"
    assert by_node["coordinator"].entity_type == "coordinator"
    assert by_node["workers"].entity_type == "worker"
    assert by_node["storage"].entity_type == "storage-node"
    assert by_node["replica"].entity_type == "storage-node"


def test_quant_resolution_identifies_pipeline_stages() -> None:
    """Weights, formats, inference, and evaluation each resolve distinctly."""
    entities = resolve_graph(load_fixture("quant"))
    by_node = {entity.node_id: entity for entity in entities.entities}

    assert by_node["model-weights"].entity_type == "weight-tensor"
    assert by_node["nf4-quantizer"].entity_type == "quant-format"
    assert by_node["fp16-conversion"].entity_type == "quant-format"
    assert by_node["inference"].entity_type == "inference-engine"
    assert by_node["evaluation"].entity_type == "quant-evaluator"


def test_signal_resolution_identifies_pipeline_stages() -> None:
    """Modulator, channel, and demodulator resolve to their own stages."""
    entities = resolve_graph(load_fixture("signal"))
    by_node = {entity.node_id: entity for entity in entities.entities}

    assert by_node["modulator"].entity_type == "modulator"
    assert by_node["channel"].entity_type == "channel-model"
    assert by_node["demodulator"].entity_type == "demodulator"
    assert by_node["decoder"].entity_type == "source-decoder"


def test_deeplearning_resolution_identifies_layers_and_data() -> None:
    """Training data resolves to the data loader, not an embedding layer."""
    entities = resolve_graph(load_fixture("deeplearning"))
    by_node = {entity.node_id: entity for entity in entities.entities}

    assert by_node["training-data"].entity_type == "dataloader"
    assert by_node["embedding"].entity_type == "embedding"
    assert by_node["attention"].entity_type == "attention-block"
    assert by_node["optimizer"].entity_type == "optimizer"


def test_quant_replacement_nf4_to_fp16_is_compatible() -> None:
    """Replacing NF4 with FP16 keeps the shared weight-format interfaces."""
    graph = load_fixture("quant")
    replacement = GraphNode.model_validate(
        {
            "id": "nf4-quantizer",
            "kind": "operation",
            "label": "FP16 conversion",
            "description": "Half-precision floating-point conversion.",
            "config": {"bits": 16, "format": "FP16"},
        }
    )

    compatibility = check_replacement(graph, "nf4-quantizer", replacement)

    assert compatibility.compatible is True
    assert compatibility.incident_edge_ids != ()


def test_iot_replacement_dropping_gpio_is_rejected() -> None:
    """Replacing the ESP32 board with a sensor drops gpio and is rejected."""
    graph = load_fixture("iot")
    replacement = GraphNode.model_validate(
        {
            "id": "esp32-board",
            "kind": "component",
            "label": "Temperature sensor",
            "config": {},
        }
    )

    compatibility = check_replacement(graph, "esp32-board", replacement)

    assert compatibility.compatible is False
    assert any(missing.kind == "gpio" for missing in compatibility.missing_interfaces)


def test_patch_service_accepts_compatible_replacement() -> None:
    """A compatible REPLACE_NODE patch creates a new revision as before."""
    graph = load_fixture("quant")
    patch = GraphPatch.model_validate(
        {
            "patch_id": "patch-nf4-fp16",
            "base_graph_id": graph.graph_id,
            "base_version": 1,
            "rationale": "Compare FP16 against NF4.",
            "operation": PatchOperation.REPLACE_NODE.value,
            "target_id": "nf4-quantizer",
            "payload": {
                "node": {
                    "id": "nf4-quantizer",
                    "kind": "operation",
                    "label": "FP16 conversion",
                    "description": "Half-precision floating-point conversion.",
                    "config": {"bits": 16, "format": "FP16"},
                },
            },
            "requested_by": "test",
        }
    )

    revised = GraphPatchService.apply_patch(graph, patch)

    assert revised.version == 2
    assert revised.parent_version == 1
    replaced = next(node for node in revised.nodes if node.id == "nf4-quantizer")
    assert replaced.label == "FP16 conversion"
    assert len(revised.edges) == len(graph.edges)


def test_patch_service_rejects_incompatible_replacement() -> None:
    """An incompatible REPLACE_NODE patch fails with interface detail."""
    graph = load_fixture("iot")
    patch = GraphPatch.model_validate(
        {
            "patch_id": "patch-mcu-sensor",
            "base_graph_id": graph.graph_id,
            "base_version": 1,
            "rationale": "Attempt an incompatible swap.",
            "operation": PatchOperation.REPLACE_NODE.value,
            "target_id": "esp32-board",
            "payload": {
                "node": {
                    "id": "esp32-board",
                    "kind": "component",
                    "label": "Temperature sensor",
                    "config": {},
                },
            },
            "requested_by": "test",
        }
    )

    with pytest.raises(BizoraError) as exc_info:
        GraphPatchService.apply_patch(graph, patch)

    assert exc_info.value.details["node_id"] == "esp32-board"
    assert any(
        missing["kind"] == "gpio" for missing in exc_info.value.details["missing_interfaces"]
    )
