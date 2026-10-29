"""Tests for pack-declared per-entity render specs.

Every entity type declares how it renders: a 2D symbol id, an
optional representative 3D model key, and whether it is physical.
Non-physical entities never reach the hardware scene; unresolved
physical nodes keep a neutral placeholder instead of a kind shape.
"""

from bizora.packs import ProfiledPack, default_registry

REGISTRY = default_registry()

EXPECTED_NON_PHYSICAL = {
    ("iot", "cloud-service"),
    ("quantization", "weight-tensor"),
    ("quantization", "quant-format"),
    ("quantization", "inference-engine"),
    ("quantization", "quant-evaluator"),
    ("signal-processing", "channel-model"),
    ("deep-learning", "loss-function"),
    ("deep-learning", "optimizer"),
    ("deep-learning", "dataloader"),
    ("deep-learning", "model-evaluator"),
}


def _entity_types() -> dict[tuple[str, str], object]:
    """Index every pack entity type by (pack id, type id)."""
    indexed = {}
    for pack in REGISTRY.packs:
        assert isinstance(pack, ProfiledPack)
        for entity in pack.profile.entity_types:
            indexed[(pack.pack_id, entity.type_id)] = entity
    return indexed


def test_every_entity_type_declares_symbol_and_physicality() -> None:
    """No type renders by accident: symbol and physicality are explicit."""
    indexed = _entity_types()

    assert len(indexed) == 42
    for key, entity in indexed.items():
        assert entity.symbol, key
        assert isinstance(entity.physical, bool), key


def test_non_physical_entity_types_are_exactly_the_process_set() -> None:
    """Data, formats, engines, services, and evaluators stay out of hardware."""
    indexed = _entity_types()

    actual = {key for key, entity in indexed.items() if not entity.physical}
    assert actual == EXPECTED_NON_PHYSICAL


def test_no_entity_type_claims_a_type_level_model_yet() -> None:
    """Type-level 3D models stay unclaimed: parts resolve via the catalog.

    A representative model per entity type would guess packages; the
    mechanism exists for curated packs, but no pack curates one yet.
    """
    indexed = _entity_types()

    assert all(entity.model_3d is None for entity in indexed.values())


def test_memory_cell_is_a_physical_symbol_without_a_package_model() -> None:
    """A bitcell is silicon, not a package: symbol yes, 3D part no."""
    indexed = _entity_types()

    cell = indexed[("electronics", "memory-cell")]
    assert cell.physical is True
    assert cell.symbol == "bitcell"
    assert cell.model_3d is None
