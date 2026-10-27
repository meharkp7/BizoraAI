import math

import pytest
from pydantic import ValidationError

from bizora.contracts.layout import (
    CameraState,
    GraphLayout,
    NodePosition,
    ViewportState,
)


def make_layout(**overrides: object) -> GraphLayout:
    values: dict[str, object] = {
        "project_id": "project-1",
        "graph_id": "graph-1",
        "version": 1,
        "positions": (
            NodePosition(node_id="input", x=10.0, y=20.0),
            NodePosition(node_id="encoder", x=30.0, y=40.0, z=5.0),
        ),
        "viewport": ViewportState(x=0.0, y=0.0, zoom=1.0),
        "camera": CameraState(distance=10.0),
        "updated_by": "test",
    }
    values.update(overrides)
    return GraphLayout(**values)


def test_valid_layout_passes() -> None:
    layout = make_layout()
    assert layout.version == 1
    assert len(layout.positions) == 2


def test_empty_positions_allowed_for_unpositioned_graph() -> None:
    layout = make_layout(positions=(), viewport=None, camera=None)
    assert layout.positions == ()


def test_duplicate_node_positions_rejected() -> None:
    with pytest.raises(ValidationError, match="unique per node ID"):
        make_layout(
            positions=(
                NodePosition(node_id="input", x=1.0, y=2.0),
                NodePosition(node_id="input", x=3.0, y=4.0),
            )
        )


@pytest.mark.parametrize("field", ["x", "y", "z"])
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_position_rejected(field: str, bad: float) -> None:
    values: dict[str, object] = {"node_id": "n", "x": 0.0, "y": 0.0}
    values[field] = bad
    with pytest.raises(ValidationError, match="must be finite"):
        NodePosition(**values)


def test_non_positive_zoom_rejected() -> None:
    with pytest.raises(ValidationError):
        ViewportState(x=0.0, y=0.0, zoom=0.0)


def test_non_positive_distance_rejected() -> None:
    with pytest.raises(ValidationError):
        CameraState(distance=0.0)


def test_polar_angle_bounded() -> None:
    with pytest.raises(ValidationError):
        CameraState(distance=1.0, polar=math.pi + 0.1)


def test_layout_ignores_no_extra_fields() -> None:
    with pytest.raises(ValidationError):
        GraphLayout(
            project_id="p",
            graph_id="g",
            version=1,
            updated_by="test",
            semantic_hint="must not exist",  # type: ignore[call-arg]
        )
