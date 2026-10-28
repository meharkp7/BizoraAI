"""Tests for multi-solid assemblies: offsets, names, QFN, merging."""

import pytest

from bizora.assets.procedural import build_assembly, build_mesh
from bizora.assets.resolver import package_spec
from bizora.contracts.assets import ProceduralKind, ProceduralSpec


def _box(
    length: float = 5.0,
    width: float = 4.0,
    height: float = 2.0,
    **overrides: object,
) -> ProceduralSpec:
    """Build a plain box spec with optional field overrides."""
    fields: dict[str, object] = {
        "kind": ProceduralKind.BOX,
        "body_length_mm": length,
        "body_width_mm": width,
        "body_height_mm": height,
        "pin_count": 0,
    }
    fields.update(overrides)
    return ProceduralSpec(**fields)  # type: ignore[arg-type]


def test_default_spec_output_is_unchanged() -> None:
    """A plain spec still yields body plus pin-N parts at the origin."""
    mesh = build_mesh(
        _box(pin_count=2, pin_pitch_mm=2.54, pin_rows=2, pin_length_mm=2.0)
    )

    assert [part.name for part in mesh.parts] == ["body", "pin-1", "pin-2"]
    assert (2.5, 2.0, 2.0) in mesh.parts[0].vertices


def test_offset_translates_every_part() -> None:
    """Offset shifts body and leads together, keeping their shape."""
    plain = build_mesh(_box(pin_count=2, pin_pitch_mm=2.54, pin_rows=2))
    moved = build_mesh(
        _box(pin_count=2, pin_pitch_mm=2.54, pin_rows=2, offset_mm=(10.0, 20.0, 30.0))
    )

    assert [part.name for part in moved.parts] == [
        part.name for part in plain.parts
    ]
    for before, after in zip(plain.parts, moved.parts, strict=True):
        assert after.vertices == tuple(
            (x + 10.0, y + 20.0, z + 30.0) for x, y, z in before.vertices
        )


def test_dual_row_pins_spread_along_length() -> None:
    """Pin rows sit on the width faces, spreading down the long axis."""
    mesh = build_mesh(
        _box(34.8, 6.35, 4.0, pin_count=28, pin_pitch_mm=2.54, pin_rows=2)
    )

    leads = mesh.parts[1:]
    assert len(leads) == 28
    for part in leads:
        xs = [vertex[0] for vertex in part.vertices]
        zs = [vertex[2] for vertex in part.vertices]
        assert abs(sum(zs) / len(zs)) == pytest.approx(6.35 / 2)
        assert min(xs) >= -34.8 / 2 and max(xs) <= 34.8 / 2


def test_two_pin_end_caps_sit_on_the_length_faces() -> None:
    """Two-pin passives terminate at the body ends, not the sides."""
    mesh = build_mesh(
        _box(1.6, 0.8, 0.8, pin_count=2, pin_pitch_mm=1.6, pin_rows=1)
    )

    centers = sorted(
        sum(vertex[0] for vertex in part.vertices) / len(part.vertices)
        for part in mesh.parts[1:]
    )
    assert centers == pytest.approx([-0.8, 0.8])


def test_body_name_renames_only_the_body_part() -> None:
    """Assemblies label each solid; leads keep pin-N names."""
    mesh = build_mesh(
        _box(body_name="pcb", pin_count=2, pin_pitch_mm=2.54, pin_rows=2)
    )

    assert [part.name for part in mesh.parts] == ["pcb", "pin-1", "pin-2"]


def test_qfn_places_pins_on_four_sides() -> None:
    """QFN pins ring the perimeter instead of two rows."""
    spec = _box(
        6.0,
        6.0,
        0.8,
        kind=ProceduralKind.QFN,
        pin_count=28,
        pin_pitch_mm=0.5,
        pin_rows=4,
    )
    mesh = build_mesh(spec)

    leads = mesh.parts[1:]
    assert len(leads) == 28
    edge_x = 0
    edge_z = 0
    for part in leads:
        xs = [vertex[0] for vertex in part.vertices]
        zs = [vertex[2] for vertex in part.vertices]
        on_x = abs(sum(xs) / len(xs)) == pytest.approx(3.0)
        on_z = abs(sum(zs) / len(zs)) == pytest.approx(3.0)
        assert on_x != on_z
        edge_x += on_x
        edge_z += on_z
    assert edge_x == 14
    assert edge_z == 14


def test_qfn_rejects_counts_not_divisible_by_four() -> None:
    """A perimeter layout needs whole sides."""
    with pytest.raises(ValueError, match="four sides"):
        build_mesh(
            _box(
                6.0,
                6.0,
                0.8,
                kind=ProceduralKind.QFN,
                pin_count=27,
                pin_pitch_mm=0.5,
                pin_rows=4,
            )
        )


def test_build_assembly_merges_solids() -> None:
    """An assembly merges parts, bounds, and counts under the first spec."""
    pcb = _box(18.0, 25.5, 0.8, body_name="pcb")
    can = _box(
        17.0, 18.0, 2.2, body_name="can", offset_mm=(0.0, 0.8, -3.25)
    )

    mesh = build_assembly((pcb, can))

    assert [part.name for part in mesh.parts] == ["pcb", "can"]
    assert mesh.spec is pcb
    assert mesh.bounds.max_xyz[1] == pytest.approx(0.8 + 2.2)
    assert len(mesh.parts) == 2
    assert mesh.vertex_count == sum(len(part.vertices) for part in mesh.parts)
    assert mesh.face_count == sum(len(part.faces) for part in mesh.parts)


def test_build_assembly_renames_colliding_parts() -> None:
    """Duplicate part names gain numeric suffixes in build order."""
    mesh = build_assembly((_box(), _box()))

    assert [part.name for part in mesh.parts] == ["body", "body-2"]


def test_build_assembly_rejects_empty() -> None:
    """An assembly needs at least one solid."""
    with pytest.raises(ValueError, match="at least one"):
        build_assembly(())


def test_package_spec_defaults_stay_assembly_compatible() -> None:
    """Data-built specs carry the default placement for merging."""
    spec = package_spec("soic-8")

    assert spec is not None
    assert spec.offset_mm == (0.0, 0.0, 0.0)
    assert spec.body_name == "body"
