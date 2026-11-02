"""Tests for the method-pipeline pack: identity, routing, catalog."""

from bizora.contracts.graph import NodeKind
from bizora.contracts.packs import DomainTag
from bizora.packs import default_registry, method_pipeline
from bizora.packs.base import DomainPack, ProfiledPack


def test_pack_identity_and_version() -> None:
    assert method_pipeline.pack.pack_id == "method-pipeline"
    assert method_pipeline.pack.pack_version == "1.0.0"
    assert method_pipeline.PACK_ID == "method-pipeline"
    assert method_pipeline.PACK_VERSION == "1.0.0"


def test_pack_satisfies_domain_and_profiled_protocols() -> None:
    assert isinstance(method_pipeline.pack, DomainPack)
    assert isinstance(method_pipeline.pack, ProfiledPack)
    assert method_pipeline.pack.profile.domain == "method-pipeline"


def test_pipeline_tags_route_here() -> None:
    registry = default_registry()
    assert registry.get("method-pipeline") is method_pipeline.pack
    routed = registry.route(
        (DomainTag(label="dataset"), DomainTag(label="preprocessing"))
    )
    assert routed is not None and routed.pack_id == "method-pipeline"
    assert registry.route((DomainTag(label="dataset"),)) is None


def test_specialized_packs_keep_their_graphs() -> None:
    """Deep-learning affinity beats the generic fallback on DL vocabulary."""
    registry = default_registry()
    routed = registry.route(
        (
            DomainTag(label="transformer"),
            DomainTag(label="attention"),
            DomainTag(label="dataset"),
        )
    )
    assert routed is not None and routed.pack_id == "deep-learning"


def test_ties_resolve_to_specialized_packs() -> None:
    """Equal affinity keeps the earlier-registered specialized pack."""
    registry = default_registry()
    routed = registry.route(
        (DomainTag(label="training"), DomainTag(label="epoch"))
    )
    assert routed is not None and routed.pack_id == "deep-learning"


def test_catalog_entries_are_valid_generics() -> None:
    entries = method_pipeline.pack.catalog_entries
    assert len(entries) == 6
    assert len({entry.component_id for entry in entries}) == 6
    kinds = {kind.value for kind in NodeKind}
    for entry in entries:
        assert entry.domain == "method-pipeline"
        assert entry.generic is True
        assert entry.kind in kinds
        assert entry.evidence == ()


def test_catalog_search_finds_pipeline_stages() -> None:
    from bizora.core.component_catalog import search_components

    results = search_components("augmentation")
    assert any(entry.component_id == "augment-generic" for entry in results)
