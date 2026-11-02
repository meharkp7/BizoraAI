"""Recover figures drawn as page vectors via poppler page renders.

IEEE-style PDFs draw schematics as page vectors, so embedded-image
ingest misses them entirely (the SRAM bitcell schematic on page 2 is
one: 17 embedded figures, zero schematics). For pages that mention
figures but yielded no embedded images, this module renders the page
and cuts 2x2 quadrant tiles as figure candidates. Tiles flow through
the existing classify/transcribe pipeline and its cache like any
other figure — no new model, no new cache. When poppler is absent
the harvest yields nothing and the embedded-only path is unchanged.
"""

import hashlib
import io
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from bizora.core.figure_ingest import find_figure_mentions
from bizora.core.pdf import MAX_PDF_PAGES

logger = logging.getLogger(__name__)

#: Render resolution: 150dpi keeps schematic text legible without
#: bloating stored tiles.
TILE_DPI = 150

#: Pages are attempted in order; the harvest stops adding tiles once
#: the caller's budget runs out.
TILE_INDEX_OFFSET = 1000


@dataclass(frozen=True)
class PageTile:
    """One quadrant crop of a rendered page, as figure bytes."""

    page: int
    index: int
    png_bytes: bytes
    sha256: str


def pdftoppm_available() -> bool:
    """Return whether poppler's renderer is on PATH."""
    return shutil.which("pdftoppm") is not None


def cut_tiles(image: Image.Image) -> tuple[bytes, ...]:
    """Cut an image into 2x2 quadrant PNGs, row-major.

    Quadrants isolate one-column figures from surrounding text so
    the classifier sees a schematic crop, not a full text page.
    """
    width, height = image.size
    mid_x, mid_y = width // 2, height // 2
    boxes = (
        (0, 0, mid_x, mid_y),
        (mid_x, 0, width, mid_y),
        (0, mid_y, mid_x, height),
        (mid_x, mid_y, width, height),
    )
    out: list[bytes] = []
    for box in boxes:
        buffer = io.BytesIO()
        image.crop(box).save(buffer, format="PNG")
        out.append(buffer.getvalue())
    return tuple(out)


class PdfRenderError(ValueError):
    """One page render failed; the page contributes no tiles."""


def render_page(pdf_bytes: bytes, page: int, *, dpi: int = TILE_DPI) -> Image.Image:
    """Render one PDF page to a PIL image via poppler.

    Raises PdfRenderError when rendering fails; callers treat a
    failed page as absent (embedded figures still persist).
    """
    with tempfile.TemporaryDirectory(prefix="bizora-page-") as work:
        target = Path(work) / "page.pdf"
        target.write_bytes(pdf_bytes)
        try:
            completed = subprocess.run(
                [
                    "pdftoppm",
                    "-png",
                    "-r",
                    str(dpi),
                    "-f",
                    str(page),
                    "-l",
                    str(page),
                    str(target),
                    str(Path(work) / "out"),
                ],
                capture_output=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PdfRenderError(f"Page {page} did not render: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace")[:200]
            raise PdfRenderError(f"Page {page} did not render: {detail}")
        renders = sorted(Path(work).glob("out-*.png"))
        if not renders:
            raise PdfRenderError(f"Page {page} produced no image.")
        with Image.open(renders[0]) as image:
            return image.convert("RGB")


def harvest_page_tiles(
    pdf_bytes: bytes,
    page_texts: dict[int, str],
    embedded_pages: frozenset[int],
    *,
    budget: int,
) -> tuple[PageTile, ...]:
    """Harvest figure-candidate tiles from vector-drawn pages.

    Only pages that mention figures (per the shared mention pattern)
    but produced no embedded images are rendered, in page order,
    until budget tiles are collected. Poppler missing, render
    failures, and empty budgets all yield no tiles instead of
    raising: figures stay embedded-only.
    """
    if budget < 1 or not pdftoppm_available():
        return ()
    pages = sorted(
        page
        for page, text in page_texts.items()
        if 1 <= page <= MAX_PDF_PAGES
        and page not in embedded_pages
        and find_figure_mentions(text)
    )
    tiles: list[PageTile] = []
    for page in pages:
        if len(tiles) >= budget:
            break
        try:
            image = render_page(pdf_bytes, page)
        except PdfRenderError as exc:
            logger.warning("Skipping page %d tiles: %s", page, exc)
            continue
        for offset, png in enumerate(cut_tiles(image)):
            if len(tiles) >= budget:
                break
            tiles.append(
                PageTile(
                    page=page,
                    index=TILE_INDEX_OFFSET + offset,
                    png_bytes=png,
                    sha256=hashlib.sha256(png).hexdigest(),
                )
            )
    return tuple(tiles)
