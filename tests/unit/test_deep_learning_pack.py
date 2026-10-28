"""Tests for the Phase-6 deep-learning pack: identity, routing, vocabulary."""

from bizora.contracts.packs import (
    DomainTag,
    PartRef,
    ResolutionLevel,
)
from bizora.packs import deep_learning, default_registry
from bizora.packs.base import DomainPack, PackRegistry, ProfiledPack


def test_pack_identity_and_version() -> None:
    """The Phase-6 pack keeps its id and bumps to version 2.0.0."""
    assert deep_learning.pack.pack_id == "deep-learning"
    assert deep_learning.pack.pack_version == "2.0.0"
    assert deep_learning.PACK_ID == "deep-learning"
    assert deep_learning.PACK_VERSION == "2.0.0"


def test_pack_satisfies_domain_and_profiled_protocols() -> None:
    """The pack still quacks as a routable, profiled DomainPack."""
    assert isinstance(deep_learning.pack, DomainPack)
    assert isinstance(deep_learning.pack, ProfiledPack)
    assert deep_learning.pack.profile.domain == "deep-learning"
    assert len(deep_learning.pack.vocabulary.kinds) == 8


def test_detection_routing_is_preserved() -> None:
    """v1 signals still route to this pack; weak tags still route nowhere."""
    registry = default_registry()
    assert registry.get("deep-learning") is deep_learning.pack
    routed = registry.route(
        (DomainTag(label="backprop"), DomainTag(label="pretrain")),
    )
    assert routed is not None and routed.pack_id == "deep-learning"
    assert registry.route((DomainTag(label="backprop"),)) is None
    assert registry.route((DomainTag(label="some future field"),)) is None


def test_routing_tie_order_is_preserved() -> None:
    """Registration order (and tie-breaking) is unchanged from v1."""
    registry = default_registry()
    assert tuple(pack.pack_id for pack in registry.packs) == (
        "electronics",
        "iot",
        "quantization",
        "signal-processing",
        "distributed-systems",
        "deep-learning",
    )
    assert isinstance(registry, PackRegistry)


def test_pack_reports_no_runnable_adapter_yet() -> None:
    """No runnable adapter until torch/Modal execution exists; flip with registry."""
    assert deep_learning.pack.simulator_adapter_ids == ()
    assert deep_learning.TORCH_ADAPTER_ID == "bizora.torch-train"


def test_copilot_tools_are_unchanged() -> None:
    """The two lexical copilot tools survive the Phase-6 upgrade."""
    tools = deep_learning.pack.copilot_tools
    assert {tool.tool_name for tool in tools} == {
        "deep_learning_search_library",
        "deep_learning_preflight",
    }
    assert all(tool.description and tool.input_schema for tool in tools)


def test_resolve_and_render_delegate_to_lexical_harness() -> None:
    """No catalog ships, so parts stay unresolved with illustrative renders."""
    resolution = deep_learning.pack.resolve_part(PartRef(raw_text="mystery layer"))
    assert resolution.level is ResolutionLevel.UNRESOLVED
    assert resolution.pack_id == "deep-learning"
    spec = deep_learning.pack.render_spec(resolution)
    assert spec.illustrative is True


def test_layer_vocabulary_is_exactly_the_allowlist() -> None:
    """Eleven structural layer kinds, no more, no less, no duplicates."""
    assert deep_learning.LAYER_IDS == (
        "linear",
        "convolution",
        "normalization",
        "activation",
        "dropout",
        "attention",
        "mlp-block",
        "residual",
        "embedding",
        "pooling",
        "positional-encoding",
    )
    assert len(set(deep_learning.LAYER_IDS)) == 11
    assert deep_learning.pack.layers == deep_learning.LAYER_SPECS
    assert set(deep_learning.LAYER_INDEX) == set(deep_learning.LAYER_IDS)


def test_layer_specs_are_well_formed_data() -> None:
    """Every layer kind carries a template, unique params, and sane enums."""
    seen_templates: set[str] = set()
    for spec in deep_learning.LAYER_SPECS:
        assert spec.display and spec.description
        assert spec.template_id
        assert spec.template_id not in seen_templates
        seen_templates.add(spec.template_id)
        names = [param.name for param in spec.params]
        assert len(names) == len(set(names))
        for param in spec.params:
            assert param.kind in {"int", "float", "bool", "enum", "block"}
            if param.kind == "enum":
                assert param.choices
            if param.minimum is not None and param.maximum is not None:
                assert param.minimum <= param.maximum


def _minimal_config(spec: deep_learning.LayerSpec) -> dict[str, object]:
    """Build the smallest valid config for one layer spec, generically."""
    config: dict[str, object] = {}
    for param in spec.params:
        if not param.required:
            continue
        if param.kind == "int":
            config[param.name] = int(param.minimum) if param.minimum else 1
        elif param.kind == "float":
            config[param.name] = float(param.minimum or 0.0)
        elif param.kind == "bool":
            config[param.name] = False
        elif param.kind == "enum":
            config[param.name] = param.choices[0]
        elif param.kind == "block":
            branch = next(
                item
                for item in deep_learning.LAYER_SPECS
                if all(not item_param.required for item_param in item.params)
            )
            config[param.name] = {"layer": branch.layer_id}
    return config


def test_every_layer_accepts_a_minimal_config() -> None:
    """Each spec validates some config built from its own data (no gaps)."""
    for spec in deep_learning.LAYER_SPECS:
        config = _minimal_config(spec)
        # Constraints need coherent values, not bare minima: heads/groups of
        # one always divide, so pin those where the spec declares them.
        for constraint in spec.constraints:
            if constraint.kind == "divides":
                config[constraint.right] = 1
        _, errors = deep_learning.validate_layer_params(
            spec,
            config,
            where="test",
        )
        assert errors == (), f"{spec.layer_id}: {errors}"


def test_specs_reject_unknown_parameters() -> None:
    """Strict params: nothing model-written smuggles through to codegen."""
    spec = deep_learning.LAYER_INDEX["linear"]
    _, errors = deep_learning.validate_layer_params(
        spec,
        {"in_features": 8, "out_features": 4, "sneaky": "import os"},
        where="test",
    )
    assert len(errors) == 1
    assert "unknown parameter 'sneaky'" in errors[0]
