"""Source evidence and provenance contracts."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Provenance(StrEnum):
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    VERIFIED = "verified"
    UNRESOLVED = "unresolved"


class EvidenceStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    CONFLICTING = "conflicting"
    UNVERIFIED = "unverified"


class EvidenceRef(BaseModel):
    """A precise pointer from a graph claim to a source artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    page: int | None = Field(default=None, ge=1)
    quote: str | None = Field(default=None, min_length=1, max_length=2000)
    figure_label: str | None = Field(default=None, max_length=128)
    bbox: tuple[float, float, float, float] | None = None
    locator: HttpUrl | None = None
    status: EvidenceStatus = EvidenceStatus.UNVERIFIED

    @model_validator(mode="after")
    def validate_bbox(self) -> "EvidenceRef":
        if self.bbox is not None:
            x1, y1, x2, y2 = self.bbox
            if not (0 <= x1 <= x2 <= 1 and 0 <= y1 <= y2 <= 1):
                raise ValueError("bbox must be normalized to [0, 1] and ordered as (x1, y1, x2, y2)")
        if self.page is None and self.quote is None and self.figure_label is None and self.locator is None:
            raise ValueError("evidence must include at least one locator: page, quote, figure_label, or URL")
        return self
