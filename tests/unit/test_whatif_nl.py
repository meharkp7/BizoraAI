"""Unit tests for deterministic plain-English what-if parsing."""

import pytest

from bizora.contracts.diagram_ir import MethodologyNode
from bizora.core.whatif_nl import WhatIfParseError, parse_whatif_text


def make_node(
    node_id: str = "encoder",
    label: str = "Transformer encoder",
    params: dict[str, object] | None = None,
) -> MethodologyNode:
    return MethodologyNode.model_validate(
        {
            "id": node_id,
            "label": label,
            "kind": "model",
            "params": params if params is not None else {"layers": 12, "dropout": 0.1},
            "confidence": 0.9,
        }
    )


NODES = [
    make_node(),
    make_node(
        "classifier",
        "Linear classifier",
        {"units": 768, "activation": "softmax"},
    ),
]


def test_parses_named_step_with_verb_separator() -> None:
    parsed = parse_whatif_text(NODES, "What if the encoder layers were 6?")

    assert parsed.node_id == "encoder"
    assert parsed.node_label == "Transformer encoder"
    assert parsed.params == {"layers": "6"}


def test_parses_reversed_numeric_value() -> None:
    parsed = parse_whatif_text(NODES, "what if the encoder had 6 layers?")

    assert parsed.node_id == "encoder"
    assert parsed.params == {"layers": "6"}


def test_parses_leader_phrasing_with_of() -> None:
    parsed = parse_whatif_text(NODES, "try the encoder with dropout of 0.5")

    assert parsed.node_id == "encoder"
    assert parsed.params == {"dropout": "0.5"}


def test_parses_multiple_settings_across_clauses() -> None:
    parsed = parse_whatif_text(
        NODES, "encoder with layers 6 and dropout 0.5, please"
    )

    assert parsed.params == {"layers": "6", "dropout": "0.5"}


def test_matches_full_label_over_id() -> None:
    parsed = parse_whatif_text(NODES, "linear classifier units = 256")

    assert parsed.node_id == "classifier"
    assert parsed.params == {"units": "256"}


def test_falls_back_to_context_step_when_unnamed() -> None:
    parsed = parse_whatif_text(NODES, "what if layers were 6?", context_node_id="encoder")

    assert parsed.node_id == "encoder"
    assert parsed.params == {"layers": "6"}


def test_named_step_beats_context() -> None:
    parsed = parse_whatif_text(
        NODES, "classifier units to 256", context_node_id="encoder"
    )

    assert parsed.node_id == "classifier"
    assert parsed.params == {"units": "256"}


def test_empty_text_asks_for_a_change() -> None:
    with pytest.raises(WhatIfParseError, match="Describe a change"):
        parse_whatif_text(NODES, "   ")


def test_unnamed_step_lists_known_steps() -> None:
    with pytest.raises(WhatIfParseError) as excinfo:
        parse_whatif_text(NODES, "what if layers were 6?")

    message = str(excinfo.value)
    assert "Which step?" in message
    assert "Transformer encoder" in message
    assert "Linear classifier" in message


def test_two_named_steps_refuses_to_guess() -> None:
    with pytest.raises(WhatIfParseError, match="more than one step"):
        parse_whatif_text(NODES, "encoder and classifier layers to 6")


def test_found_step_without_settings_lists_them() -> None:
    with pytest.raises(WhatIfParseError) as excinfo:
        parse_whatif_text(NODES, "tell me about the encoder")

    message = str(excinfo.value)
    assert "Transformer encoder" in message
    assert "layers (now 12)" in message
    assert "dropout (now 0.1)" in message


def test_step_without_settings_says_so() -> None:
    nodes = [make_node("io", "Input", {})]

    with pytest.raises(WhatIfParseError, match="no settings for this step"):
        parse_whatif_text(nodes, "what if input changed?")
