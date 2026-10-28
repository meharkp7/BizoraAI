"""Contract tests for the Phase 4 asset registry schema.

Fixtures are generated in code: model keys, URIs, and checksums are
formatted from loop counters and content hashes, never copied from a
real corpus (no downloads happen in this phase).
"""

import hashlib

import pytest
from pydantic import ValidationError

from bizora.contracts.assets import (
    AssetLevel,
    AssetManifest,
    AssetProvenance,
    AssetQuery,
    AssetRecord,
    MeshBounds,
    MeshPart,
    ProceduralKind,
    ProceduralMesh,
    ProceduralSpec,
    ResolvedAsset,
)


def make_record(index: int, **overrides: object) -> AssetRecord:
    """Generate one measured record with a self-consistent checksum."""
    body = f"generated-model-bytes-{index}".encode()
    params: dict[str, object] = {
        "model_key": f"gen-model-{index}",
        "uri": f"asset://fixtures/gen-model-{index}.glb",
        "license": "CC0-1.0 (generated fixture)",
        "source": "procedural test fixture",
        "checksum_sha256": hashlib.sha256(body).hexdigest(),
        "manufacturer": f"maker-{index % 3}",
        "family": f"family-{index % 2}",
        "package": f"pkg-{index % 4}",
        "provenance": AssetProvenance.MEASURED,
    }
    params.update(overrides)
    return AssetRecord.model_validate(params)


def test_measured_record_requires_a_valid_checksum() -> None:
    """Measured visuals must be verifiable; malformed digests reject."""
    record = make_record(1)
    assert record.provenance is AssetProvenance.MEASURED
    assert len(record.checksum_sha256 or "") == 64
    with pytest.raises(ValidationError, match="sha256 checksum"):
        make_record(2, checksum_sha256=None)
    with pytest.raises(ValidationError, match="64 lowercase hex"):
        make_record(3, checksum_sha256="not-a-digest")
    upper = make_record(4, checksum_sha256="AB" * 32)
    assert upper.checksum_sha256 == "ab" * 32


def test_illustrative_record_may_omit_checksum() -> None:
    """Stand-ins carry no bytes to verify, so the digest stays optional."""
    record = make_record(5, checksum_sha256=None, provenance=AssetProvenance.ILLUSTRATIVE)
    assert record.checksum_sha256 is None


def test_manifest_versions_and_rejects_duplicate_keys() -> None:
    """Snapshots carry a semver version and unique model keys."""
    manifest = AssetManifest(
        registry_version="1.2.3", assets=tuple(make_record(i) for i in range(10))
    )
    assert manifest.registry_version == "1.2.3"
    assert len(manifest.assets) == 10
    with pytest.raises(ValidationError, match="unique"):
        AssetManifest(registry_version="1.0.0", assets=(make_record(1), make_record(1)))
    with pytest.raises(ValidationError):
        AssetManifest(registry_version="v1", assets=())


def test_asset_query_normalizes_and_drops_blanks() -> None:
    """Lookups compare lowercased tokens; blank strings mean absent."""
    query = AssetQuery(
        model_key="  GEN-Model-7 ",
        manufacturer="   ",
        family="Family-1",
        package="PKG-2",
    )
    assert query.model_key == "gen-model-7"
    assert query.manufacturer is None
    assert query.family == "family-1"
    assert query.package == "pkg-2"


def test_procedural_spec_requires_pitch_for_pins() -> None:
    """Pinned fallbacks must state how far apart the pins sit."""
    spec = ProceduralSpec(
        kind=ProceduralKind.BOX,
        body_length_mm=4.0,
        body_width_mm=2.0,
        body_height_mm=1.0,
        pin_count=4,
        pin_pitch_mm=1.27,
        pin_rows=2,
    )
    assert spec.pin_count == 4
    with pytest.raises(ValidationError, match="pin pitch"):
        ProceduralSpec(
            kind=ProceduralKind.BOX,
            body_length_mm=4.0,
            body_width_mm=2.0,
            body_height_mm=1.0,
            pin_count=4,
        )
    with pytest.raises(ValidationError):
        ProceduralSpec(
            kind=ProceduralKind.BOX,
            body_length_mm=0,
            body_width_mm=2.0,
            body_height_mm=1.0,
            pin_count=0,
        )


def test_mesh_part_rejects_bad_faces() -> None:
    """Faces must index real vertices and span a triangle."""
    MeshPart(
        name="body",
        vertices=((0, 0, 0), (1, 0, 0), (0, 1, 0)),
        faces=((0, 1, 2),),
    )
    with pytest.raises(ValidationError, match="outside"):
        MeshPart(
            name="body",
            vertices=((0, 0, 0), (1, 0, 0)),
            faces=((0, 1, 2),),
        )
    with pytest.raises(ValidationError, match="degenerate"):
        MeshPart(
            name="body",
            vertices=((0, 0, 0), (1, 0, 0), (0, 1, 0)),
            faces=((1, 1, 2),),
        )


def test_procedural_mesh_counts_must_match_parts() -> None:
    """Reported totals are checksums over the summed parts."""
    part = MeshPart(
        name="body",
        vertices=((0, 0, 0), (1, 0, 0), (0, 1, 0)),
        faces=((0, 1, 2),),
    )
    spec = ProceduralSpec(
        kind=ProceduralKind.BOX,
        body_length_mm=1,
        body_width_mm=1,
        body_height_mm=1,
        pin_count=0,
    )
    ProceduralMesh(
        spec=spec,
        parts=(part,),
        bounds=MeshBounds(min_xyz=(0, 0, 0), max_xyz=(1, 1, 0)),
        vertex_count=3,
        face_count=1,
    )
    with pytest.raises(ValidationError, match="summed parts"):
        ProceduralMesh(
            spec=spec,
            parts=(part,),
            bounds=MeshBounds(min_xyz=(0, 0, 0), max_xyz=(1, 1, 0)),
            vertex_count=99,
            face_count=1,
        )


def test_resolved_asset_payload_matches_level() -> None:
    """Unresolved carries nothing, primitive carries a spec, hits a record."""
    ResolvedAsset(
        level=AssetLevel.UNRESOLVED,
        provenance=AssetProvenance.ILLUSTRATIVE,
        reason="No rung matched.",
    )
    spec = ProceduralSpec(
        kind=ProceduralKind.CYLINDER,
        body_length_mm=4,
        body_width_mm=4,
        body_height_mm=4,
        pin_count=0,
    )
    ResolvedAsset(
        level=AssetLevel.PRIMITIVE,
        provenance=AssetProvenance.ILLUSTRATIVE,
        procedural=spec,
        reason="Generated from package dimensions.",
    )
    ResolvedAsset(
        level=AssetLevel.EXACT,
        provenance=AssetProvenance.MEASURED,
        asset=make_record(9),
        reason="Exact model-key match.",
    )
    with pytest.raises(ValidationError, match="no asset"):
        ResolvedAsset(
            level=AssetLevel.UNRESOLVED,
            provenance=AssetProvenance.ILLUSTRATIVE,
            asset=make_record(10),
            reason="Contradictory payload.",
        )
    with pytest.raises(ValidationError, match="exactly one procedural"):
        ResolvedAsset(
            level=AssetLevel.PRIMITIVE,
            provenance=AssetProvenance.ILLUSTRATIVE,
            reason="Missing spec.",
        )
