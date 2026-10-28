"""3D asset-registry data contracts (Phase 4).

Rule zero applies: model keys, manufacturers, families, and package ids
live in registry data and test fixtures, never in logic. The registry
schema only describes the shape: where the model bytes live, who may
reuse them, how to verify them, and whether the visual is measured
(from a real model of the exact part) or illustrative (a stand-in).

No asset bytes ship in this repo and no download happens here; records
point at URIs whose license and source are recorded so a later fetch
step can verify them before use.
"""

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def normalize_asset_token(value: str) -> str:
    """Normalize one registry lookup token for comparison and storage."""
    return " ".join(value.strip().lower().split())


class AssetProvenance(StrEnum):
    """Whether a 3D visual shows the real part or a stand-in."""

    MEASURED = "measured"
    ILLUSTRATIVE = "illustrative"


class AssetLevel(StrEnum):
    """Resolver-ladder rung, from exact identity down to unresolved."""

    EXACT = "exact"
    FAMILY = "family"
    PACKAGE = "package"
    PRIMITIVE = "primitive"
    UNRESOLVED = "unresolved"


class AssetRecord(BaseModel):
    """One versioned 3D-model entry: bytes pointer plus reuse terms."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_key: str = Field(pattern=_SLUG_PATTERN.pattern, max_length=128)
    uri: str = Field(min_length=1, max_length=1000)
    license: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=500)
    checksum_sha256: str | None = Field(default=None, max_length=64)
    manufacturer: str | None = Field(default=None, max_length=128)
    family: str | None = Field(default=None, max_length=128)
    package: str | None = Field(default=None, max_length=128)
    provenance: AssetProvenance = AssetProvenance.MEASURED

    @field_validator("checksum_sha256", mode="before")
    @classmethod
    def _normalize_checksum(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip().lower()
            return cleaned if cleaned else None
        return value

    @model_validator(mode="after")
    def _check_measured_assets_are_verifiable(self) -> "AssetRecord":
        if self.checksum_sha256 is not None and not _SHA256_PATTERN.match(self.checksum_sha256):
            raise ValueError("checksum_sha256 must be 64 lowercase hex characters.")
        if self.provenance is AssetProvenance.MEASURED and self.checksum_sha256 is None:
            raise ValueError("Measured assets must carry a sha256 checksum.")
        return self


class AssetManifest(BaseModel):
    """One versioned snapshot of the asset registry contents."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    registry_version: str = Field(pattern=r"^\d+\.\d+\.\d+$", max_length=32)
    assets: tuple[AssetRecord, ...] = Field(default=())

    @model_validator(mode="after")
    def _check_keys_unique(self) -> "AssetManifest":
        keys = [asset.model_key for asset in self.assets]
        if len(set(keys)) != len(keys):
            raise ValueError("Asset model_key values must be unique within a manifest.")
        return self


class AssetQuery(BaseModel):
    """What the resolver knows about one part mention needing a visual."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_key: str | None = Field(default=None, max_length=128)
    manufacturer: str | None = Field(default=None, max_length=128)
    family: str | None = Field(default=None, max_length=128)
    package: str | None = Field(default=None, max_length=128)

    @field_validator("model_key", "manufacturer", "family", "package", mode="before")
    @classmethod
    def _normalize_tokens(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = normalize_asset_token(value)
            return cleaned if cleaned else None
        return value


class ProceduralKind(StrEnum):
    """Parametric fallback generator: real geometry, not decoration."""

    BOX = "box"
    CYLINDER = "cylinder"
    PIN_FIELD = "pin_field"


class ProceduralSpec(BaseModel):
    """Parameters for one generated fallback solid, in millimetres."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ProceduralKind
    body_length_mm: float = Field(gt=0, le=500)
    body_width_mm: float = Field(gt=0, le=500)
    body_height_mm: float = Field(gt=0, le=500)
    pin_count: int = Field(ge=0, le=256)
    pin_pitch_mm: float = Field(default=0, ge=0, le=50)
    pin_rows: int = Field(default=1, ge=1, le=16)
    pin_length_mm: float = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def _check_pins_need_pitch(self) -> "ProceduralSpec":
        if self.pin_count > 0 and self.pin_pitch_mm <= 0:
            raise ValueError("Pinned packages must state a positive pin pitch.")
        return self


class MeshPart(BaseModel):
    """One solid inside a generated mesh: flat xyz vertices plus triangles."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    vertices: tuple[tuple[float, float, float], ...] = Field(min_length=1)
    faces: tuple[tuple[int, int, int], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_faces_index_vertices(self) -> "MeshPart":
        count = len(self.vertices)
        for face in self.faces:
            if min(face) < 0 or max(face) >= count:
                raise ValueError(f"Face {face} indexes outside {count} vertices.")
            if len(set(face)) != 3:
                raise ValueError(f"Face {face} is degenerate.")
        return self


class MeshBounds(BaseModel):
    """Axis-aligned bounds of a generated mesh, in millimetres."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_xyz: tuple[float, float, float]
    max_xyz: tuple[float, float, float]

    @model_validator(mode="after")
    def _check_bounds_order(self) -> "MeshBounds":
        for low, high in zip(self.min_xyz, self.max_xyz, strict=True):
            if high < low:
                raise ValueError("Bounds maxima must not sit below minima.")
        return self


class ProceduralMesh(BaseModel):
    """Real generated geometry for one fallback: parts plus bounds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spec: ProceduralSpec
    parts: tuple[MeshPart, ...] = Field(min_length=1)
    bounds: MeshBounds
    vertex_count: int = Field(ge=1)
    face_count: int = Field(ge=1)

    @model_validator(mode="after")
    def _check_counts_match_parts(self) -> "ProceduralMesh":
        vertices = sum(len(part.vertices) for part in self.parts)
        faces = sum(len(part.faces) for part in self.parts)
        if vertices != self.vertex_count or faces != self.face_count:
            raise ValueError("Reported counts must match the summed parts.")
        return self


class ResolvedAsset(BaseModel):
    """The outcome of resolving one asset query down the ladder."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    level: AssetLevel
    provenance: AssetProvenance
    asset: AssetRecord | None = None
    procedural: ProceduralSpec | None = None
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _check_payload_matches_level(self) -> "ResolvedAsset":
        if self.level is AssetLevel.UNRESOLVED:
            if self.asset is not None or self.procedural is not None:
                raise ValueError("Unresolved outcomes carry no asset or procedural spec.")
        elif self.level is AssetLevel.PRIMITIVE:
            if self.procedural is None or self.asset is not None:
                raise ValueError("Primitive outcomes carry exactly one procedural spec.")
        elif self.asset is None:
            raise ValueError("Resolved outcomes carry exactly one asset record.")
        return self
