"""Paper-figure overlay pipeline: ingest, describe, localize, persist.

Embedded PDF images plus page-render tiles (for vector-drawn figures)
become viewer figures; a vision provider describes each figure and
localizes graph nodes inside it as normalized regions. Only raster
bytes are read here; interpretation belongs to the provider, and
every persisted link is validated against the live graph.
No domain, paper, or part knowledge lives in this module.
"""

from contextlib import suppress
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from PIL import Image
from sqlalchemy.orm import Session

from bizora.contracts.figures import (
    MAX_FIGURES_PER_DESCRIBE,
    FigureAttachment,
    FigureDescriptionRequest,
    FigureDescriptionResult,
    FigureRecord,
    FigureRegion,
    NodeHint,
    PaperFigure,
    RegionLocalizationRequest,
    RegionLocalizationResult,
    ResponseUsage,
)
from bizora.contracts.graph import MethodologyGraph
from bizora.core.figure_ingest import (
    MAX_FIGURES,
    FigureIngestResult,
    caption_candidates,
    extract_figures_from_pdf,
    find_figure_mentions,
)
from bizora.core.page_render import harvest_page_tiles
from bizora.core.papers import is_valid_figure_id, suggest_figure_id
from bizora.core.pdf import PdfPageText
from bizora.db.repository import (
    delete_paper_figures,
    list_paper_figures,
    paper_figure_from_record,
    save_paper_figure,
    save_paper_text,
)

SURROUNDING_TEXT_CHARS = 4000
# Localization runs one figure per call. Batched localize calls mix up
# which image is which (regions land on the neighboring figure's id);
# a single image per call leaves nothing to confuse. Describe calls
# stay batched: labels and captions match correctly in small batches.
LOCALIZE_FIGURES_PER_CALL = 1


class FigureVisionProvider(Protocol):
    """Vision calls the figure pipeline needs (Muse implements these)."""

    async def describe_figures(
        self, request: FigureDescriptionRequest
    ) -> FigureDescriptionResult: ...

    async def localize_regions(
        self, request: RegionLocalizationRequest
    ) -> RegionLocalizationResult: ...


@dataclass(frozen=True)
class FigureIngestReport:
    """Outcome of one figure-overlay ingest for one graph revision."""

    figures: tuple[PaperFigure, ...]
    warnings: tuple[str, ...]
    truncated: bool
    skipped: int
    usage: tuple[ResponseUsage, ...]


def figure_id_for(source_stem: str, page: int, index: int, short_hash: str) -> str:
    """Assign a stable figure id, falling back to a plain valid id."""
    candidate = suggest_figure_id(source_stem, page, index, short_hash)
    if is_valid_figure_id(candidate):
        return candidate
    return f"fig-p{page}-i{index}-{short_hash}"


def marked_paper_text(page_texts: tuple[PdfPageText, ...]) -> str:
    """Join page texts with [Page N] markers for evidence citations.

    Text-derived diagram extraction reads these markers to cite the
    page behind every node, edge, and block.
    """
    return "\n\n".join(
        f"[Page {page.page_number}]\n{page.text}" for page in page_texts
    ).strip()


def _node_hints(graph: MethodologyGraph) -> tuple[NodeHint, ...]:
    return tuple(
        NodeHint(
            node_id=node.id,
            label=node.label,
            kind=node.kind.value,
            description=(node.description[:500] if node.description else None),
        )
        for node in graph.nodes
    )


def _attachments(
    ingest: FigureIngestResult,
    pages: dict[int, str],
    source_stem: str,
) -> tuple[tuple[FigureAttachment, ...], dict[str, bytes]]:
    attachments: list[FigureAttachment] = []
    image_by_id: dict[str, bytes] = {}
    for raw in ingest.figures:
        figure_id = figure_id_for(source_stem, raw.page, raw.index, raw.sha256[:8])
        page_text = pages.get(raw.page, "")
        mentions = find_figure_mentions(page_text)
        candidates = caption_candidates(page_text)
        attachments.append(
            FigureAttachment(
                figure_id=figure_id,
                page=raw.page,
                image_bytes=raw.image_bytes,
                mime_type=raw.mime_type,
                surrounding_text=page_text[:SURROUNDING_TEXT_CHARS] or None,
                label_hint=", ".join(mentions)[:512] or None,
                caption_hint="\n---\n".join(candidates)[:4000] or None,
            )
        )
        image_by_id[figure_id] = raw.image_bytes
    return tuple(attachments), image_by_id


def persist_paper_figures(
    session: Session,
    *,
    project_id: str,
    graph_id: str,
    pdf_bytes: bytes,
    page_texts: tuple[PdfPageText, ...],
    source_id: str,
    created_by: str,
) -> tuple[int, bool, int]:
    """Persist embedded figures and paper text without vision calls.

    Runs at extract time so the diagrams endpoint works immediately
    after upload for any paper: figures land as UNKNOWN-kind records
    with file metadata and caption hints, and the marked text feeds
    the text-derived diagrams. Vision describe/localize stays in
    :func:`ingest_paper_figures`, which replaces these rows with
    enriched ones on re-ingest. Returns (figure count, truncated,
    skipped).
    """
    ingest = extract_figures_from_pdf(pdf_bytes)
    marked_text = marked_paper_text(page_texts)
    delete_paper_figures(session, project_id=project_id, graph_id=graph_id)
    save_paper_text(
        session,
        project_id=project_id,
        graph_id=graph_id,
        source_id=source_id,
        created_by=created_by,
        text=marked_text,
        page_count=len(page_texts) or None,
    )
    pages = {page.page_number: page.text for page in page_texts}
    embedded_pages = frozenset(raw.page for raw in ingest.figures)
    tiles = harvest_page_tiles(
        pdf_bytes,
        pages,
        embedded_pages,
        budget=max(0, MAX_FIGURES - len(ingest.figures)),
    )
    if not ingest.figures and not tiles:
        session.commit()
        return (0, ingest.truncated, ingest.skipped)
    for raw in ingest.figures:
        figure_id = figure_id_for(source_id, raw.page, raw.index, raw.sha256[:8])
        page_text = pages.get(raw.page, "")
        mentions = find_figure_mentions(page_text)
        candidates = caption_candidates(page_text)
        save_paper_figure(
            session,
            project_id=project_id,
            graph_id=graph_id,
            source_id=source_id,
            created_by=created_by,
            figure=FigureRecord(
                figure_id=figure_id,
                page=raw.page,
                label=", ".join(mentions)[:128] or None,
                caption="\n---\n".join(candidates)[:4000] or None,
                mime_type=raw.mime_type,
                sha256=raw.sha256,
                byte_size=len(raw.image_bytes),
                context=page_text[:SURROUNDING_TEXT_CHARS] or None,
            ),
            regions=(),
            image_bytes=raw.image_bytes,
        )
    for tile in tiles:
        figure_id = figure_id_for(source_id, tile.page, tile.index, tile.sha256[:8])
        page_text = pages.get(tile.page, "")
        mentions = find_figure_mentions(page_text)
        candidates = caption_candidates(page_text)
        save_paper_figure(
            session,
            project_id=project_id,
            graph_id=graph_id,
            source_id=source_id,
            created_by=created_by,
            figure=FigureRecord(
                figure_id=figure_id,
                page=tile.page,
                label=", ".join(mentions)[:128] or None,
                caption="\n---\n".join(candidates)[:4000] or None,
                mime_type="image/png",
                sha256=tile.sha256,
                byte_size=len(tile.png_bytes),
                context=page_text[:SURROUNDING_TEXT_CHARS] or None,
            ),
            regions=(),
            image_bytes=tile.png_bytes,
        )
    session.commit()
    return (len(ingest.figures) + len(tiles), ingest.truncated, ingest.skipped)


async def ingest_paper_figures(
    session: Session,
    *,
    graph: MethodologyGraph,
    pdf_bytes: bytes,
    page_texts: tuple[PdfPageText, ...],
    source_id: str,
    created_by: str,
    provider: FigureVisionProvider,
) -> FigureIngestReport:
    """Ingest one PDF's figures for one graph revision and persist them.

    Describes every recovered figure, localizes graph nodes inside the
    figures in bounded batches, and stores figures with their image
    bytes. A PDF with no embedded images yields an empty report, never
    invented figures.
    """
    ingest = extract_figures_from_pdf(pdf_bytes)
    marked_text = marked_paper_text(page_texts)
    if not ingest.figures:
        # No figures, but the text still feeds text-derived diagrams.
        save_paper_text(
            session,
            project_id=graph.project_id,
            graph_id=graph.graph_id,
            source_id=source_id,
            created_by=created_by,
            text=marked_text,
            page_count=len(page_texts) or None,
        )
        session.commit()
        return FigureIngestReport(
            figures=(), warnings=(), truncated=ingest.truncated, skipped=ingest.skipped,
            usage=(),
        )
    pages = {page.page_number: page.text for page in page_texts}
    attachments, image_by_id = _attachments(ingest, pages, source_id)

    warnings: list[str] = []
    usage: list[ResponseUsage] = []
    records: list[FigureRecord] = []
    for start in range(0, len(attachments), MAX_FIGURES_PER_DESCRIBE):
        batch = attachments[start : start + MAX_FIGURES_PER_DESCRIBE]
        described = await provider.describe_figures(
            FigureDescriptionRequest(
                project_id=graph.project_id,
                graph_id=graph.graph_id,
                source_id=source_id,
                created_by=created_by,
                figures=batch,
            )
        )
        warnings.extend(described.warnings)
        if described.usage is not None:
            usage.append(described.usage)
        records.extend(described.draft_figures.figures)

    regions_by_figure: dict[str, list[FigureRegion]] = {
        figure.figure_id: [] for figure in attachments
    }
    nodes = _node_hints(graph)
    for start in range(0, len(attachments), LOCALIZE_FIGURES_PER_CALL):
        batch = attachments[start : start + LOCALIZE_FIGURES_PER_CALL]
        localized = await provider.localize_regions(
            RegionLocalizationRequest(
                project_id=graph.project_id,
                graph_id=graph.graph_id,
                source_id=source_id,
                created_by=created_by,
                figures=batch,
                nodes=nodes,
            )
        )
        warnings.extend(localized.warnings)
        if localized.usage is not None:
            usage.append(localized.usage)
        for region in localized.draft_regions.regions:
            regions_by_figure.setdefault(region.figure_id, []).append(region)

    # Re-ingest replaces the graph's figures: regions always reflect
    # the current graph. Old rows go only after every provider call
    # succeeded, so a failure keeps the previous overlay intact. The
    # paper text refreshes in the same commit.
    delete_paper_figures(session, project_id=graph.project_id, graph_id=graph.graph_id)
    save_paper_text(
        session,
        project_id=graph.project_id,
        graph_id=graph.graph_id,
        source_id=source_id,
        created_by=created_by,
        text=marked_text,
        page_count=len(page_texts) or None,
    )
    figures: list[PaperFigure] = []
    for record_meta in records:
        stored = save_paper_figure(
            session,
            project_id=graph.project_id,
            graph_id=graph.graph_id,
            source_id=source_id,
            created_by=created_by,
            figure=record_meta,
            regions=tuple(regions_by_figure.get(record_meta.figure_id, [])),
            image_bytes=image_by_id[record_meta.figure_id],
        )
        figures.append(paper_figure_from_record(stored))
    session.commit()
    return FigureIngestReport(
        figures=tuple(figures),
        warnings=tuple(warnings),
        truncated=ingest.truncated,
        skipped=ingest.skipped,
        usage=tuple(usage),
    )


def list_graph_figures(
    session: Session, *, project_id: str, graph_id: str
) -> tuple[PaperFigure, ...]:
    """List one graph's persisted figures with their regions."""
    return tuple(
        paper_figure_from_record(record)
        for record in list_paper_figures(
            session, project_id=project_id, graph_id=graph_id
        )
    )


#: JPEG 2000 signature box (bytes 4..12): some PDFs embed JP2 rasters,
#: which browsers cannot render in an <img>.
_JP2_SIGNATURE = b"jP  \r\n\x87\n"

#: Raw JPEG 2000 codestream magic (no container box).
_JP2_CODESTREAM = b"\xff\x4f\xff\x51"


def browser_safe_figure_bytes(
    image_bytes: bytes, mime_type: str | None
) -> tuple[bytes, str]:
    """Return figure bytes a browser can render, plus their mime type.

    JPEG 2000 rasters (common in PDF extraction) convert to PNG at serve
    time; everything else passes through untouched. Detection sniffs
    magic bytes, never the stored mime type, so mislabeled rows heal too.
    """
    is_jp2 = image_bytes[4:12] == _JP2_SIGNATURE or image_bytes[:4] == _JP2_CODESTREAM
    if is_jp2:
        # A corrupt JP2 serves as-is (the viewer shows its broken-image
        # state) rather than failing the whole figure request.
        with suppress(Exception), Image.open(BytesIO(image_bytes)) as image:
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue(), "image/png"
    return image_bytes, mime_type or "image/png"
