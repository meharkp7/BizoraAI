"""Domain-pack data contracts.

Rule zero applies: domains are free-text labels a model produces per
paper, and part names live in pack data, never in logic. Nothing in this
module enumerates domains, papers, or parts. Packs declare affinity for
labels; the core only routes, and anything unrecognized resolves to
UNRESOLVED with a reason instead of a guess.
"""

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_TOOL_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def normalize_tag_label(label: str) -> str:
    """Normalize one free-text domain label for comparison and storage."""
    return " ".join(label.strip().lower().split())


class DomainTag(BaseModel):
    """One open-vocabulary domain label attached to a graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=128)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("label", mode="before")
    @classmethod
    def _normalize_label(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_tag_label(value)
        return value


class PackComponentKind(BaseModel):
    """One component kind a pack's vocabulary data declares."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind_id: str = Field(pattern=_SLUG_PATTERN.pattern, max_length=128)
    display_label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class PackVocabulary(BaseModel):
    """The data-driven component vocabulary a pack handles."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kinds: tuple[PackComponentKind, ...] = Field(min_length=1)


class PartRef(BaseModel):
    """An unresolved part mention: paper text plus optional identifiers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_text: str = Field(min_length=1, max_length=2000)
    part_number: str | None = Field(default=None, max_length=128)
    package: str | None = Field(default=None, max_length=128)
    parameters: dict[str, str] = Field(default_factory=dict)


class ResolutionLevel(StrEnum):
    """Resolver ladder rung, from exact identity down to unresolved."""

    EXACT = "exact"
    FAMILY = "family"
    CATEGORY = "category"
    UNRESOLVED = "unresolved"


class ResolutionConfidence(StrEnum):
    """How the resolution is grounded."""

    FROM_PAPER = "from_paper"
    MATCHED = "matched"
    ASSUMED = "assumed"


class PartResolution(BaseModel):
    """The outcome of resolving one part mention through a pack."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    level: ResolutionLevel
    confidence: ResolutionConfidence
    pack_id: str = Field(pattern=_SLUG_PATTERN.pattern, max_length=128)
    kind_id: str | None = Field(default=None, pattern=_SLUG_PATTERN.pattern)
    asset_key: str | None = Field(
        default=None,
        max_length=256,
        description="Asset-registry key for the 3D model or footprint.",
    )
    reason: str = Field(min_length=1, max_length=2000)


class RenderSpec(BaseModel):
    """How one resolved part renders in 3D."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=300)
    asset_uri: str | None = Field(default=None, max_length=1000)
    fallback_package: str | None = Field(default=None, max_length=128)
    illustrative: bool = Field(
        description="True when the visual is illustrative rather than measured.",
    )


class PackPreflightSeverity(StrEnum):
    """Whether a pack preflight finding blocks the edit."""

    BLOCK = "block"
    WARN = "warn"


class PackPreflightFinding(BaseModel):
    """One pack-rule verdict on a proposed graph edit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(pattern=_SLUG_PATTERN.pattern, max_length=128)
    severity: PackPreflightSeverity
    message: str = Field(min_length=1, max_length=2000)


class SimulationPreviewSection(BaseModel):
    """One headed block of a pack's simulation preview."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    heading: str = Field(min_length=1, max_length=128)
    lines: tuple[str, ...] = Field(default=(), max_length=400)


class SimulationPreview(BaseModel):
    """A pack's human-readable summary of what it would simulate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pack_id: str = Field(pattern=_SLUG_PATTERN.pattern, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    sections: tuple[SimulationPreviewSection, ...] = Field(default=(), max_length=20)
    warnings: tuple[str, ...] = Field(default=(), max_length=100)


class CopilotToolSpec(BaseModel):
    """One pack-provided tool the copilot may call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str = Field(pattern=_TOOL_PATTERN.pattern, max_length=64)
    description: str = Field(min_length=1, max_length=2000)
    input_schema: dict[str, Any] = Field(default_factory=dict)
