"""Tests for the asset resolver ladder.

Exact model, then manufacturer family, then package fallback, then a
generated illustrative primitive; anything below every rung stays
unresolved with a reason. Registry entries are generated fixtures;
package-dimension hits use the shipped generic outline table.
"""

from tests.unit.test_asset_contracts import make_record
from tests.unit.test_asset_registry import make_registry

from bizora.assets.registry import AssetRegistry
from bizora.assets.resolver import known_packages, package_spec, resolve_asset
from bizora.contracts.assets import (
    AssetLevel,
    AssetManifest,
    AssetProvenance,
    AssetQuery,
)


def test_exact_model_match_returns_the_measured_record() -> None:
    """A known model key resolves exactly with its own provenance."""
    outcome = resolve_asset(make_registry(), AssetQuery(model_key="gen-model-5"))
    assert outcome.level is AssetLevel.EXACT
    assert outcome.provenance is AssetProvenance.MEASURED
    assert outcome.asset is not None and outcome.asset.model_key == "gen-model-5"
    assert outcome.procedural is None
    assert outcome.reason


def test_family_match_returns_an_illustrative_representative() -> None:
    """Family hits never claim to be the exact part: illustrative."""
    outcome = resolve_asset(make_registry(), AssetQuery(manufacturer="maker-1", family="family-1"))
    assert outcome.level is AssetLevel.FAMILY
    assert outcome.provenance is AssetProvenance.ILLUSTRATIVE
    assert outcome.asset is not None
    assert outcome.asset.manufacturer == "maker-1"
    assert "illustrative" in outcome.reason


def test_exact_beats_family_when_both_could_match() -> None:
    """Rung order holds: the exact key wins over family data."""
    outcome = resolve_asset(
        make_registry(),
        AssetQuery(model_key="gen-model-1", manufacturer="maker-1", family="family-1"),
    )
    assert outcome.level is AssetLevel.EXACT
    assert outcome.asset is not None and outcome.asset.model_key == "gen-model-1"


def test_package_fallback_uses_registry_entry_first() -> None:
    """A package shared by registry records resolves to a representative."""
    outcome = resolve_asset(make_registry(), AssetQuery(package="pkg-3"))
    assert outcome.level is AssetLevel.PACKAGE
    assert outcome.provenance is AssetProvenance.ILLUSTRATIVE
    assert outcome.asset is not None and outcome.asset.package == "pkg-3"
    assert "illustrative" in outcome.reason


def test_package_without_registry_entry_generates_a_primitive() -> None:
    """Known outline, no model bytes: a parametric spec, clearly labelled."""
    empty = AssetRegistry(AssetManifest(registry_version="1.0.0"))
    assert "soic-8" in known_packages()
    outcome = resolve_asset(empty, AssetQuery(package="SOIC-8"))
    assert outcome.level is AssetLevel.PRIMITIVE
    assert outcome.provenance is AssetProvenance.ILLUSTRATIVE
    assert outcome.asset is None
    assert outcome.procedural is not None
    assert outcome.procedural.pin_count == 8
    assert "parametric" in outcome.reason


def test_unknown_package_stays_unresolved_with_reason() -> None:
    """No registry entry and no outline data means no visual, with a why."""
    empty = AssetRegistry(AssetManifest(registry_version="1.0.0"))
    outcome = resolve_asset(empty, AssetQuery(package="pkg-unknown-xyz"))
    assert outcome.level is AssetLevel.UNRESOLVED
    assert outcome.asset is None
    assert outcome.procedural is None
    assert "pkg-unknown-xyz" in outcome.reason


def test_empty_query_stays_unresolved() -> None:
    """Nothing to match on resolves to nothing, honestly."""
    outcome = resolve_asset(make_registry(), AssetQuery())
    assert outcome.level is AssetLevel.UNRESOLVED
    assert "empty query" in outcome.reason


def test_package_table_covers_expected_generic_outlines() -> None:
    """The shipped outline table spans two-terminal, leaded, and module forms."""
    assert package_spec("passive-0603") is not None
    assert package_spec("sot-23") is not None
    assert package_spec("to-92") is not None
    assert package_spec("module-pin-field") is not None
    assert package_spec("not-a-package") is None
    assert tuple(sorted(known_packages())) == known_packages()


def test_pack_render_spec_serves_registry_hits_and_misses() -> None:
    """render_spec serves registry URIs with provenance; misses stay illustrative."""
    from bizora.contracts.packs import PartResolution, ResolutionConfidence, ResolutionLevel
    from bizora.core.entity_registry import EntityTypeDef
    from bizora.packs.electronics import pack as electronics
    from bizora.packs.lexical import LexicalPack

    assert electronics.asset_registry_version == "1.0.0"
    missed = electronics.render_spec(
        PartResolution(
            level=ResolutionLevel.EXACT,
            confidence=ResolutionConfidence.FROM_PAPER,
            pack_id="electronics",
            kind_id="transistor",
            asset_key="gen-model-0",
            reason="probe",
        )
    )
    assert missed.asset_uri is None
    assert missed.fallback_package == "gen-model-0"
    assert missed.illustrative is True

    seeded = LexicalPack(
        pack_id="probe-pack",
        pack_version="0.0.0",
        display="Probe",
        signals=("probe",),
        threshold=1,
        entity_types=(EntityTypeDef("widget", "Widget", "package", ("widget",)),),
        catalog=[],
        assets=make_registry(4),
    )
    assert seeded.asset_registry_version == "2.1.0"
    hit = seeded.render_spec(
        PartResolution(
            level=ResolutionLevel.EXACT,
            confidence=ResolutionConfidence.FROM_PAPER,
            pack_id="probe-pack",
            kind_id="widget",
            asset_key="gen-model-2",
            reason="probe",
        )
    )
    assert hit.asset_uri == "asset://fixtures/gen-model-2.glb"
    assert hit.fallback_package == "gen-model-2"
    assert hit.illustrative is False

    stand_in = LexicalPack(
        pack_id="probe-pack",
        pack_version="0.0.0",
        display="Probe",
        signals=("probe",),
        threshold=1,
        entity_types=(EntityTypeDef("widget", "Widget", "package", ("widget",)),),
        catalog=[],
        assets=AssetRegistry(
            AssetManifest(
                registry_version="3.0.0",
                assets=(
                    make_record(
                        50,
                        model_key="stand-in-widget",
                        provenance=AssetProvenance.ILLUSTRATIVE,
                    ),
                ),
            )
        ),
    )
    stand_in_spec = stand_in.render_spec(
        PartResolution(
            level=ResolutionLevel.FAMILY,
            confidence=ResolutionConfidence.MATCHED,
            pack_id="probe-pack",
            kind_id="widget",
            asset_key="stand-in-widget",
            reason="probe",
        )
    )
    assert stand_in_spec.asset_uri == "asset://fixtures/gen-model-50.glb"
    assert stand_in_spec.illustrative is True
