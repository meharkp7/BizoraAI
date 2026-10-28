"""Tests for the versioned asset registry index.

The registry is data-driven: every entry below is generated from loop
counters, and lookups are plain normalized-text matching over that
data. No part names appear in the assertions beyond generated tokens.
"""

from tests.unit.test_asset_contracts import make_record

from bizora.assets.registry import AssetRegistry
from bizora.contracts.assets import AssetManifest, AssetProvenance


def make_registry(count: int = 12) -> AssetRegistry:
    """Build a registry snapshot from generated records."""
    return AssetRegistry(
        AssetManifest(
            registry_version="2.1.0",
            assets=tuple(make_record(i) for i in range(count)),
        )
    )


def test_registry_reports_its_snapshot_version() -> None:
    """The index pins the manifest version it was built from."""
    registry = make_registry()
    assert registry.version == "2.1.0"
    assert len(registry) == 12
    assert registry.manifest.registry_version == "2.1.0"


def test_exact_lookup_is_case_and_space_insensitive() -> None:
    """Model keys match after normalization; misses return None."""
    registry = make_registry()
    assert registry.get("gen-model-4") is not None
    assert registry.get("  GEN-Model-4 ") is not None
    assert registry.get("gen-model-4") == registry.get("GEN-MODEL-4")
    assert registry.get("no-such-model") is None


def test_family_and_package_indexes_group_generated_entries() -> None:
    """Family and package rungs return every sharing record, in order."""
    registry = make_registry(12)
    family = registry.by_family("maker-1", "family-1")
    assert family
    assert all((record.manufacturer, record.family) == ("maker-1", "family-1") for record in family)
    assert family == registry.by_family("MAKER-1", "Family-1")
    assert registry.by_family("maker-9", "family-9") == ()

    packaged = registry.by_package("pkg-2")
    assert len(packaged) == 3
    assert all(record.package == "pkg-2" for record in packaged)
    assert registry.by_package("pkg-9") == ()


def test_listings_report_distinct_sorted_tokens() -> None:
    """Inventory helpers surface what the data contains, sorted."""
    registry = make_registry(12)
    assert registry.manufacturers() == ("maker-0", "maker-1", "maker-2")
    assert registry.packages() == ("pkg-0", "pkg-1", "pkg-2", "pkg-3")


def test_empty_registry_answers_everything_with_nothing() -> None:
    """A versioned-but-empty snapshot is valid and matches nothing."""
    registry = AssetRegistry(AssetManifest(registry_version="1.0.0"))
    assert registry.version == "1.0.0"
    assert len(registry) == 0
    assert registry.get("gen-model-0") is None
    assert registry.by_family("maker-0", "family-0") == ()
    assert registry.by_package("pkg-0") == ()
    assert registry.manufacturers() == ()
    assert registry.packages() == ()


def test_records_without_grouping_fields_skip_indexes() -> None:
    """Entries lacking family or package data stay exactly findable."""
    record = make_record(
        100,
        model_key="lone-model",
        manufacturer=None,
        family=None,
        package=None,
        provenance=AssetProvenance.ILLUSTRATIVE,
        checksum_sha256=None,
    )
    registry = AssetRegistry(AssetManifest(registry_version="1.0.0", assets=(record,)))
    assert registry.get("lone-model") == record
    assert registry.manufacturers() == ()
    assert registry.packages() == ()
