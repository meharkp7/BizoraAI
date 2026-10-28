"""Component library contracts.

The catalog describes identifiable replacement components: exact part
numbers with manufacturers and verified references, and correctly
identified generics where no exact part applies. Every entry links to a
registry entity type so the library, the 3D explorer, the replacement
validator, and the copilot all operate on the same identities.

Specification values are nominal catalog values for comparison and
filtering; the UI labels them as such and points at the datasheet or
reference for authoritative limits.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from bizora.contracts.domain import EntityResolution, InterfaceSpec, MissingInterface

ConfigFieldType = Literal["string", "number", "boolean", "enum"]


class ComponentSpec(BaseModel):
    """One nominal specification value for display and comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=128)
    unit: str | None = Field(default=None, max_length=32)
    typical: bool = Field(
        default=True,
        description="True for nominal catalog values; False for guaranteed limits.",
    )


class ComponentPin(BaseModel):
    """One pin or terminal of a component package."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    designator: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    function: str | None = Field(default=None, max_length=300)


class ConfigField(BaseModel):
    """One user-configurable configuration key for a component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=128)
    type: ConfigFieldType
    default: Any = None
    options: tuple[str, ...] = Field(
        default=(),
        description="Allowed values when type is 'enum'.",
    )
    unit: str | None = Field(default=None, max_length=32)
    required: bool = False
    description: str | None = Field(default=None, max_length=500)


class ComponentEvidence(BaseModel):
    """One grounding reference for a catalog entry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, max_length=300)
    note: str | None = Field(default=None, max_length=500)


class ComponentSummary(BaseModel):
    """Searchable identity card for one catalog component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component_id: str = Field(min_length=1, max_length=128)
    domain: str = Field(min_length=1, max_length=64)
    entity_type: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    kind: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=300)
    generic: bool = Field(
        description="True for correctly identified generics; False for exact part numbers.",
    )
    manufacturer: str | None = Field(default=None, max_length=128)
    part_number: str | None = Field(default=None, max_length=128)
    headline: str = Field(min_length=1, max_length=300)


class ComponentDetail(ComponentSummary):
    """Full catalog entry: specs, pinout, interfaces, and configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str = Field(min_length=1, max_length=2000)
    datasheet_url: str | None = Field(default=None, max_length=500)
    reference_url: str | None = Field(default=None, max_length=500)
    specs: tuple[ComponentSpec, ...] = ()
    pinout: tuple[ComponentPin, ...] = ()
    interfaces: tuple[InterfaceSpec, ...] = ()
    constraints: dict[str, str] = Field(
        default_factory=dict,
        description="Machine-checkable limits, e.g. supply_min_V, supply_max_V.",
    )
    config_schema: tuple[ConfigField, ...] = ()
    default_config: dict[str, Any] = Field(default_factory=dict)
    evidence: tuple[ComponentEvidence, ...] = ()


class ConstraintWarning(BaseModel):
    """One non-blocking concern about a candidate replacement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=500)


class CompatibilityPreflight(BaseModel):
    """Full validation preview for replacing one node with a catalog component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    compatible: bool
    target_node_id: str = Field(min_length=1, max_length=128)
    component_id: str = Field(min_length=1, max_length=128)
    missing_interfaces: tuple[MissingInterface, ...] = ()
    preserved_edge_ids: tuple[str, ...] = Field(
        default=(),
        description="Incident edges that survive the swap (same node ID).",
    )
    warnings: tuple[ConstraintWarning, ...] = ()
    candidate: EntityResolution
    candidate_label: str = Field(min_length=1, max_length=300)


class CopilotProposal(BaseModel):
    """A copilot-suggested replacement awaiting explicit user approval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=128)
    component_id: str | None = Field(
        default=None,
        max_length=128,
        description="Catalog component for replacements; null for config-only proposals.",
    )
    kind: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    config: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=1, max_length=1000)


class CopilotCard(BaseModel):
    """One structured attachment on a copilot reply."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["component", "comparison", "proposal", "evidence", "info"]
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=4000)
    component_ids: tuple[str, ...] = ()
    node_id: str | None = Field(default=None, max_length=128)


class PreflightRequest(BaseModel):
    """Request a replacement validation preview (no writes)."""

    model_config = ConfigDict(extra="forbid")

    component_id: str = Field(min_length=1, max_length=128)
    config: dict[str, Any] = Field(default_factory=dict)


class CopilotRequest(BaseModel):
    """A conversational request scoped to one graph revision."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    selected_node_id: str | None = Field(default=None, max_length=128)


class CopilotResponse(BaseModel):
    """Copilot reply: prose plus cards plus at most one pending proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reply: str = Field(min_length=1, max_length=6000)
    cards: tuple[CopilotCard, ...] = ()
    proposal: CopilotProposal | None = None
