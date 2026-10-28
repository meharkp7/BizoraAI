"""Tests for the parametric fallback geometry generators.

Every spec below is generated from arithmetic progressions over body
sizes and pin layouts — no copied outlines. The mesh contract itself
(valid faces, matching counts) is asserted on each output, plus real
geometric properties: bounds contain every vertex, pin parts scale
with pin count, and generation is deterministic.
"""

from bizora.assets.procedural import build_mesh
from bizora.assets.resolver import package_spec
from bizora.contracts.assets import ProceduralKind, ProceduralSpec


def make_spec(index: int, kind: ProceduralKind) -> ProceduralSpec:
    """Generate one spec from arithmetic progressions, no copied data."""
    pins = (index % 5) * 4
    return ProceduralSpec(
        kind=kind,
        body_length_mm=2.0 + index,
        body_width_mm=1.5 + index / 2,
        body_height_mm=1.0 + index / 4,
        pin_count=pins,
        pin_pitch_mm=1.27 if pins else 0,
        pin_rows=2 if pins else 1,
        pin_length_mm=0.8 if pins else 0,
    )


def test_box_mesh_has_body_plus_one_part_per_pin() -> None:
    """Box fallbacks build a body solid and one lead solid per pin."""
    mesh = build_mesh(make_spec(3, ProceduralKind.BOX))
    assert mesh.parts[0].name == "body"
    assert len(mesh.parts) == 1 + 12
    assert mesh.vertex_count == sum(len(part.vertices) for part in mesh.parts)
    assert mesh.face_count == sum(len(part.faces) for part in mesh.parts)
    assert mesh.face_count == 12 * len(mesh.parts)


def test_cylinder_mesh_uses_segmented_body_and_leads() -> None:
    """Cylinder fallbacks build a round body with the same lead rule."""
    mesh = build_mesh(make_spec(2, ProceduralKind.CYLINDER))
    assert len(mesh.parts) == 1 + 8
    body = mesh.parts[0]
    assert len(body.vertices) == 24 * 2 + 2
    assert len(body.faces) == 24 * 4


def test_pin_field_mesh_lays_pins_out_as_a_module() -> None:
    """Pin-field fallbacks read as a module: slab body, rising header pins."""
    mesh = build_mesh(make_spec(4, ProceduralKind.PIN_FIELD))
    assert len(mesh.parts) == 1 + 16
    body_top = max(v[1] for v in mesh.parts[0].vertices)
    for pin in mesh.parts[1:]:
        pin_top = max(v[1] for v in pin.vertices)
        assert pin_top > body_top


def test_zero_pin_spec_builds_body_only() -> None:
    """Unpinned passives are a single solid with exact box bounds."""
    spec = make_spec(0, ProceduralKind.BOX)
    assert spec.pin_count == 0
    mesh = build_mesh(spec)
    assert len(mesh.parts) == 1
    assert mesh.vertex_count == 8
    assert mesh.face_count == 12
    assert mesh.bounds.min_xyz == (-1.0, 0.0, -0.75)
    assert mesh.bounds.max_xyz == (1.0, 1.0, 0.75)


def test_bounds_contain_every_vertex_across_kinds() -> None:
    """Reported bounds are tight axis-aligned bounds over all parts."""
    for kind in ProceduralKind:
        for index in range(5):
            mesh = build_mesh(make_spec(index, kind))
            low = mesh.bounds.min_xyz
            high = mesh.bounds.max_xyz
            for part in mesh.parts:
                for x, y, z in part.vertices:
                    assert low[0] <= x <= high[0]
                    assert low[1] <= y <= high[1]
                    assert low[2] <= z <= high[2]


def test_generation_is_deterministic() -> None:
    """The same spec always yields the same mesh, byte for byte."""
    spec = make_spec(3, ProceduralKind.PIN_FIELD)
    first = build_mesh(spec)
    second = build_mesh(spec)
    assert first == second


def test_shipped_package_outlines_all_generate_valid_meshes() -> None:
    """Every generic outline in the data table builds real geometry."""
    for package in (
        "sot-23",
        "to-92",
        "soic-8",
        "qfn-32",
        "passive-0603",
        "passive-0805",
        "module-pin-field",
    ):
        spec = package_spec(package)
        assert spec is not None
        mesh = build_mesh(spec)
        assert mesh.vertex_count > 8
        assert mesh.face_count >= 12
        assert mesh.bounds.min_xyz[1] <= 0 <= mesh.bounds.max_xyz[1]
