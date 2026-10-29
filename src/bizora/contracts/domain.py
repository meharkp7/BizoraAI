"""Domain detection and entity resolution contracts.

These types describe what a methodology graph *means* in its research
domain: which domain it belongs to, what kind of real-world entity each
node represents, and which interfaces each entity exposes. Resolution is
evidence-grounded but explicitly marked: anything the paper does not
support resolves to a generic fallback instead of a fabricated part.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

GENERIC_DOMAIN = "generic"


class InterfaceSpec(BaseModel):
    """One named interface an entity exposes (port, protocol, or contract)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)


class EntityResolution(BaseModel):
    """How one graph node resolves to a registry entity type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=128)
    domain: str = Field(min_length=1, max_length=64)
    entity_type: str = Field(min_length=1, max_length=128)
    display_label: str = Field(min_length=1, max_length=300)
    generic: bool = Field(description="True when the paper does not support an exact entity type.")
    category: str = Field(
        min_length=1,
        max_length=64,
        description="Coarse grouping key for display. Shapes never derive from it.",
    )
    physical: bool = Field(description="False for process/data entities, which never map to parts.")
    symbol: str = Field(
        min_length=1,
        max_length=64,
        description="Pack-declared 2D symbol id for legends, process views, and schematics.",
    )
    model_3d: str | None = Field(
        default=None,
        max_length=128,
        description="Representative 3D visual key, or None when only catalog parts render.",
    )
    interfaces: tuple[InterfaceSpec, ...] = ()
    matched_terms: tuple[str, ...] = Field(
        default=(),
        description="Registry vocabulary that grounded this resolution.",
    )
    confidence: float = Field(ge=0.0, le=1.0)


class DomainClassification(BaseModel):
    """The detected research domain for one graph revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: str = Field(min_length=1, max_length=64)
    confidence: float = Field(ge=0.0, le=1.0)
    signals: tuple[str, ...] = Field(
        default=(),
        description="Matched vocabulary grounding the classification.",
    )


class GraphEntities(BaseModel):
    """Domain classification plus per-node entity resolutions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    classification: DomainClassification
    entities: tuple[EntityResolution, ...]


class MissingInterface(BaseModel):
    """One interface kind a replacement drops, blocking the swap."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


class ReplacementCompatibility(BaseModel):
    """Whether a replacement node keeps its predecessor's interfaces."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    compatible: bool
    missing_interfaces: tuple[MissingInterface, ...] = ()
    incident_edge_ids: tuple[str, ...] = Field(
        default=(),
        description="Edges preserved by the swap (same node ID).",
    )
