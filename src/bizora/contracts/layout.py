"""Visual-only layout contracts; layouts never alter graph semantics."""

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _require_finite(value: Any, *, field_name: str) -> float:
    """Reject NaN and infinite coordinates."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite.")
    return result


class NodePosition(BaseModel):
    """A visual-only position for one graph node."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=128)
    x: float
    y: float
    z: float = 0.0

    @field_validator("x", "y", "z", mode="before")
    @classmethod
    def validate_finite(cls, value: Any, info: Any) -> float:
        return _require_finite(value, field_name=str(info.field_name))


class ViewportState(BaseModel):
    """A visual-only 2D canvas viewport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x: float
    y: float
    zoom: float = Field(gt=0)

    @field_validator("x", "y", "zoom", mode="before")
    @classmethod
    def validate_finite(cls, value: Any, info: Any) -> float:
        return _require_finite(value, field_name=str(info.field_name))


class CameraState(BaseModel):
    """A visual-only 3D explorer camera."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_x: float = 0.0
    target_y: float = 0.0
    target_z: float = 0.0
    distance: float = Field(gt=0)
    azimuth: float = 0.0
    polar: float = Field(default=0.0, ge=0, le=math.pi)

    @field_validator(
        "target_x",
        "target_y",
        "target_z",
        "distance",
        "azimuth",
        "polar",
        mode="before",
    )
    @classmethod
    def validate_finite(cls, value: Any, info: Any) -> float:
        return _require_finite(value, field_name=str(info.field_name))


class GraphLayout(BaseModel):
    """A visual-only layout bound to one exact graph revision.

    Layouts record where nodes are drawn, never what the methodology means.
    Saving or replacing a layout must not create a graph revision.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    positions: tuple[NodePosition, ...] = ()
    viewport: ViewportState | None = None
    camera: CameraState | None = None
    updated_by: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_unique_positions(self) -> "GraphLayout":
        node_ids = [position.node_id for position in self.positions]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("node positions must be unique per node ID")
        return self
