"""Parametric fallback geometry: real solids, not decoration.

The generators below turn a ProceduralSpec (body dimensions plus pin
layout, in millimetres) into an explicit triangle mesh: a box body with
leads, a cylinder body with leads, or a pin-field module. Dimensions
come from caller data — package tables or per-part parameters — never
from branches in this logic. Output vertices are real geometry the 3D
canvas can build BufferGeometry from directly.
"""

from __future__ import annotations

import math

from bizora.contracts.assets import (
    MeshBounds,
    MeshPart,
    ProceduralKind,
    ProceduralMesh,
    ProceduralSpec,
)

Vertex = tuple[float, float, float]
Face = tuple[int, int, int]

_CYLINDER_SEGMENTS = 24


def _box_vertices(
    cx: float, cy: float, cz: float, lx: float, ly: float, lz: float
) -> tuple[Vertex, ...]:
    hx, hy, hz = lx / 2, ly / 2, lz / 2
    return (
        (cx - hx, cy - hy, cz - hz),
        (cx + hx, cy - hy, cz - hz),
        (cx + hx, cy + hy, cz - hz),
        (cx - hx, cy + hy, cz - hz),
        (cx - hx, cy - hy, cz + hz),
        (cx + hx, cy - hy, cz + hz),
        (cx + hx, cy + hy, cz + hz),
        (cx - hx, cy + hy, cz + hz),
    )


_BOX_FACES: tuple[Face, ...] = (
    (0, 1, 2),
    (0, 2, 3),
    (4, 6, 5),
    (4, 7, 6),
    (0, 4, 5),
    (0, 5, 1),
    (2, 6, 7),
    (2, 7, 3),
    (0, 3, 7),
    (0, 7, 4),
    (1, 5, 6),
    (1, 6, 2),
)


def _box_part(
    name: str, cx: float, cy: float, cz: float, lx: float, ly: float, lz: float
) -> MeshPart:
    return MeshPart(name=name, vertices=_box_vertices(cx, cy, cz, lx, ly, lz), faces=_BOX_FACES)


def _cylinder_part(
    name: str, cx: float, cy: float, cz: float, radius: float, height: float
) -> MeshPart:
    vertices: list[Vertex] = []
    for ring_y in (cy - height / 2, cy + height / 2):
        for step in range(_CYLINDER_SEGMENTS):
            angle = 2 * math.pi * step / _CYLINDER_SEGMENTS
            vertices.append((cx + radius * math.cos(angle), ring_y, cz + radius * math.sin(angle)))
    bottom_center = len(vertices)
    vertices.append((cx, cy - height / 2, cz))
    top_center = len(vertices)
    vertices.append((cx, cy + height / 2, cz))
    faces: list[Face] = []
    for step in range(_CYLINDER_SEGMENTS):
        nxt = (step + 1) % _CYLINDER_SEGMENTS
        lower, lower_next = step, nxt
        upper, upper_next = step + _CYLINDER_SEGMENTS, nxt + _CYLINDER_SEGMENTS
        faces.append((lower, upper_next, upper))
        faces.append((lower, lower_next, upper_next))
        faces.append((bottom_center, lower_next, lower))
        faces.append((top_center, upper, upper_next))
    return MeshPart(name=name, vertices=tuple(vertices), faces=tuple(faces))


def _pin_grid(spec: ProceduralSpec) -> list[tuple[float, float]]:
    """Lay pins out along the body edges (dual rows) or as a grid field."""
    if spec.pin_count == 0:
        return []
    rows = max(spec.pin_rows, 1)
    if spec.kind is ProceduralKind.PIN_FIELD or rows > 2:
        cols = math.ceil(spec.pin_count / rows)
        width = (cols - 1) * spec.pin_pitch_mm
        depth = (rows - 1) * spec.pin_pitch_mm
        positions = []
        for index in range(spec.pin_count):
            row, col = divmod(index, cols)
            positions.append(
                (-width / 2 + col * spec.pin_pitch_mm, -depth / 2 + row * spec.pin_pitch_mm)
            )
        return positions
    per_side = math.ceil(spec.pin_count / 2)
    span = (per_side - 1) * spec.pin_pitch_mm
    positions = []
    for index in range(spec.pin_count):
        side = 1.0 if index % 2 == 0 else -1.0
        slot = index // 2
        along = -span / 2 + slot * spec.pin_pitch_mm if per_side > 1 else 0.0
        positions.append((side * spec.body_width_mm / 2, along))
    return positions


def _lead_parts(spec: ProceduralSpec) -> tuple[MeshPart, ...]:
    """Build one thin box lead per pin position."""
    if spec.pin_count == 0:
        return ()
    lead_width = min(spec.pin_pitch_mm * 0.4, spec.body_height_mm * 0.5, 2.0)
    lead_width = max(lead_width, 0.05)
    lead_height = spec.pin_length_mm if spec.pin_length_mm > 0 else spec.body_height_mm * 0.4
    parts = []
    for index, (px, pz) in enumerate(_pin_grid(spec)):
        if spec.kind is ProceduralKind.PIN_FIELD:
            # Header pins stand on the module top face.
            cy = spec.body_height_mm + lead_height / 2
        else:
            # Edge leads drop from the body midline to the board plane.
            cy = -lead_height / 2
        parts.append(_box_part(f"pin-{index + 1}", px, cy, pz, lead_width, lead_height, lead_width))
    return tuple(parts)


def build_mesh(spec: ProceduralSpec) -> ProceduralMesh:
    """Generate the full fallback mesh for one procedural spec."""
    if spec.kind is ProceduralKind.CYLINDER:
        radius = min(spec.body_length_mm, spec.body_width_mm) / 2
        body = _cylinder_part("body", 0, spec.body_height_mm / 2, 0, radius, spec.body_height_mm)
    else:
        body = _box_part(
            "body",
            0,
            spec.body_height_mm / 2,
            0,
            spec.body_length_mm,
            spec.body_height_mm,
            spec.body_width_mm,
        )
    parts = (body, *_lead_parts(spec))
    xs = [v[0] for part in parts for v in part.vertices]
    ys = [v[1] for part in parts for v in part.vertices]
    zs = [v[2] for part in parts for v in part.vertices]
    return ProceduralMesh(
        spec=spec,
        parts=parts,
        bounds=MeshBounds(
            min_xyz=(min(xs), min(ys), min(zs)),
            max_xyz=(max(xs), max(ys), max(zs)),
        ),
        vertex_count=sum(len(part.vertices) for part in parts),
        face_count=sum(len(part.faces) for part in parts),
    )
