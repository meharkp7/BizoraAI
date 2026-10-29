"""Figure and diagram ingestion contracts.

Figures are generic visual artifacts (diagrams, schematics, plots, photos,
equations) recovered from paper PDFs. Kinds describe visual form only, never
a research domain: domain labels are produced by extraction, not by this
module.
"""

import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

FIGURE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
MAX_FIGURES_PER_PAPER = 50
MAX_FIGURES_PER_DESCRIBE = 5
MAX_FIGURES_PER_LOCALIZE = 10
MAX_FIGURE_IMAGE_BYTES = 8_000_000
MAX_REGIONS_PER_FIGURE = 40


class FigureKind(StrEnum):
    DIAGRAM = "diagram"
    SCHEMATIC = "schematic"
    PLOT = "plot"
    PHOTO = "photo"
    EQUATION = "equation"
    UNKNOWN = "unknown"


class FigureRecord(BaseModel):
    """One ingested figure with trusted file metadata and model description."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    figure_id: str = Field(pattern=FIGURE_ID_PATTERN)
    page: int | None = Field(default=None, ge=1)
    label: str | None = Field(
        default=None, max_length=128, description="Printed label, e.g. 'Figure 3'."
    )
    caption: str | None = Field(default=None, max_length=4000)
    kind: FigureKind = FigureKind.UNKNOWN
    mime_type: str | None = Field(default=None, max_length=64)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$", max_length=64)
    byte_size: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    context: str | None = Field(
        default=None, max_length=4000, description="Surrounding text excerpt."
    )
    confidence: float | None = Field(default=None, ge=0, le=1)


class FigureSet(BaseModel):
    """All figures recovered from one paper revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    figures: tuple[FigureRecord, ...] = ()

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "FigureSet":
        ids = [figure.figure_id for figure in self.figures]
        if len(ids) != len(set(ids)):
            raise ValueError("figure IDs must be unique")
        return self


class FigureAttachment(BaseModel):
    """One figure image plus its surrounding text, sent for description."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    figure_id: str = Field(pattern=FIGURE_ID_PATTERN)
    page: int | None = Field(default=None, ge=1)
    image_bytes: bytes = Field(min_length=1, max_length=MAX_FIGURE_IMAGE_BYTES)
    mime_type: str = Field(min_length=1, max_length=64, pattern=r"^image/")
    surrounding_text: str | None = Field(default=None, max_length=4000)
    label_hint: str | None = Field(default=None, max_length=512)
    caption_hint: str | None = Field(default=None, max_length=4000)


class FigureDescriptionRequest(BaseModel):
    """Input supplied to a figure-description provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    created_by: str = Field(min_length=1, max_length=128)
    figures: tuple[FigureAttachment, ...] = Field(min_length=1, max_length=MAX_FIGURES_PER_PAPER)


class FigureDescription(BaseModel):
    """Model-produced description of one figure (metadata comes from us)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    figure_id: str = Field(pattern=FIGURE_ID_PATTERN)
    label: str | None = Field(default=None, max_length=64)
    caption: str | None = Field(default=None, max_length=4000)
    kind: FigureKind = FigureKind.UNKNOWN
    confidence: float | None = Field(default=None, ge=0, le=1)


class FigureDescriptionList(BaseModel):
    """Structured-output envelope the model returns for figure description."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    figures: tuple[FigureDescription, ...] = ()


class ResponseUsage(BaseModel):
    """Token usage reported by a model API response, for spend tracking."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    response_id: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)


class FigureDescriptionResult(BaseModel):
    """A provider's proposed figure set, not yet trusted or persisted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    draft_figures: FigureSet
    provider_name: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    warnings: tuple[str, ...] = ()
    usage: ResponseUsage | None = None


def build_figure_set(
    request: FigureDescriptionRequest,
    descriptions: FigureDescriptionList,
) -> tuple[FigureSet, tuple[str, ...]]:
    """Merge model descriptions with trusted attachment metadata.

    File facts (page, mime type, hash, byte size) always come from the
    attachments we sent, never from the model. Descriptions for unknown
    figure IDs are skipped with a warning; attachments without a
    description are kept with kind UNKNOWN and a warning.
    """
    by_id = {figure.figure_id: figure for figure in request.figures}
    seen: set[str] = set()
    records: list[FigureRecord] = []
    warnings: list[str] = []

    for description in descriptions.figures:
        attachment = by_id.get(description.figure_id)
        if attachment is None:
            warnings.append(
                f"Description for unknown figure '{description.figure_id}' was skipped."
            )
            continue
        if description.figure_id in seen:
            warnings.append(
                f"Duplicate description for figure '{description.figure_id}' was skipped."
            )
            continue
        seen.add(description.figure_id)
        records.append(
            FigureRecord(
                figure_id=attachment.figure_id,
                page=attachment.page,
                label=description.label,
                caption=description.caption,
                kind=description.kind,
                mime_type=attachment.mime_type,
                sha256=hashlib.sha256(attachment.image_bytes).hexdigest(),
                byte_size=len(attachment.image_bytes),
                context=attachment.surrounding_text,
                confidence=description.confidence,
            )
        )

    for attachment in request.figures:
        if attachment.figure_id not in seen:
            warnings.append(f"Figure '{attachment.figure_id}' had no description; kept as unknown.")
            records.append(
                FigureRecord(
                    figure_id=attachment.figure_id,
                    page=attachment.page,
                    mime_type=attachment.mime_type,
                    sha256=hashlib.sha256(attachment.image_bytes).hexdigest(),
                    byte_size=len(attachment.image_bytes),
                    context=attachment.surrounding_text,
                )
            )

    figure_set = FigureSet(
        project_id=request.project_id,
        graph_id=request.graph_id,
        source_id=request.source_id,
        figures=tuple(records),
    )
    return figure_set, tuple(warnings)


class NodeHint(BaseModel):
    """One graph node the model may link a figure region to."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=512)
    kind: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=500)


class RegionLocalizationRequest(BaseModel):
    """Input supplied to a figure-region localization provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    created_by: str = Field(min_length=1, max_length=128)
    figures: tuple[FigureAttachment, ...] = Field(
        min_length=1, max_length=MAX_FIGURES_PER_LOCALIZE
    )
    nodes: tuple[NodeHint, ...] = Field(min_length=1, max_length=500)


NormalizedBBox = tuple[float, float, float, float]


class FigureRegionProposal(BaseModel):
    """One model-proposed region: normalized x, y, width, height in 0..1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    figure_id: str = Field(pattern=FIGURE_ID_PATTERN)
    bbox: NormalizedBBox
    node_id: str | None = Field(default=None, max_length=128)
    label: str = Field(min_length=1, max_length=256)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_bbox(self) -> "FigureRegionProposal":
        x, y, width, height = self.bbox
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError("bbox origin must sit inside the unit square")
        if not (width > 0 and height > 0):
            raise ValueError("bbox width and height must be positive")
        if x + width > 1 or y + height > 1:
            raise ValueError("bbox must not overflow the unit square")
        return self


class FigureRegion(FigureRegionProposal):
    """A trusted region with a server-assigned stable id."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    region_id: str = Field(pattern=FIGURE_ID_PATTERN)


class FigureRegionList(BaseModel):
    """Structured-output envelope the model returns for localization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    regions: tuple[FigureRegionProposal, ...] = ()


class FigureRegionSet(BaseModel):
    """All trusted regions localized for one paper revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    regions: tuple[FigureRegion, ...] = ()


class PaperFigure(BaseModel):
    """One persisted figure served to the UI: metadata plus regions.

    Image bytes travel separately through the figure-image endpoint,
    never inside this payload.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    figure_id: str = Field(pattern=FIGURE_ID_PATTERN)
    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    created_by: str = Field(min_length=1, max_length=128)
    page: int | None = Field(default=None, ge=1)
    label: str | None = Field(default=None, max_length=512)
    caption: str | None = Field(default=None, max_length=4000)
    kind: FigureKind = FigureKind.UNKNOWN
    mime_type: str | None = Field(default=None, max_length=64)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$", max_length=64)
    byte_size: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    regions: tuple[FigureRegion, ...] = ()


class RegionLocalizationResult(BaseModel):
    """A provider's proposed region set, not yet trusted or persisted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    draft_regions: FigureRegionSet
    provider_name: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    warnings: tuple[str, ...] = ()
    usage: ResponseUsage | None = None


def _region_id(figure_id: str, index: int) -> str:
    """Assign a stable id: figure order decides, never the model."""
    return f"{figure_id}-r{index}"


def build_region_set(
    request: RegionLocalizationRequest,
    proposals: FigureRegionList,
) -> tuple[FigureRegionSet, tuple[str, ...]]:
    """Merge model region proposals with trusted request metadata.

    Region IDs are assigned by figure order. Proposals for unknown
    figures, boxes outside the unit square, and figures past the
    per-figure cap are skipped with a warning. A proposal naming an
    unknown node is kept but unlinked (node_id None) with a warning:
    the region exists in the figure even when its graph link does not.
    """
    known_figures = {figure.figure_id for figure in request.figures}
    known_nodes = {node.node_id for node in request.nodes}
    counts: dict[str, int] = {}
    regions: list[FigureRegion] = []
    warnings: list[str] = []

    for proposal in proposals.regions:
        if proposal.figure_id not in known_figures:
            warnings.append(
                f"Region for unknown figure '{proposal.figure_id}' was skipped."
            )
            continue
        count = counts.get(proposal.figure_id, 0)
        if count >= MAX_REGIONS_PER_FIGURE:
            warnings.append(
                f"Figure '{proposal.figure_id}' exceeds "
                f"{MAX_REGIONS_PER_FIGURE} regions; extras were skipped."
            )
            continue
        node_id = proposal.node_id
        if node_id is not None and node_id not in known_nodes:
            warnings.append(
                f"Region '{proposal.label}' names unknown node "
                f"'{node_id}'; kept unlinked."
            )
            node_id = None
        counts[proposal.figure_id] = count + 1
        regions.append(
            FigureRegion(
                region_id=_region_id(proposal.figure_id, count + 1),
                figure_id=proposal.figure_id,
                bbox=proposal.bbox,
                node_id=node_id,
                label=proposal.label,
                confidence=proposal.confidence,
            )
        )

    region_set = FigureRegionSet(
        project_id=request.project_id,
        graph_id=request.graph_id,
        source_id=request.source_id,
        regions=tuple(regions),
    )
    return region_set, tuple(warnings)
