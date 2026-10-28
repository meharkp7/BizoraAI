"""Extract embedded figure/diagram images from paper PDFs.

Only embedded raster images are recovered here; interpretation (labels,
captions, kinds) is left to a vision model fed with the image bytes plus
surrounding page text. No domain, paper, or part knowledge lives here.
"""

import hashlib
import re
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from bizora.core.pdf import MAX_PDF_PAGES, PDF_MAGIC_PREFIX

MAX_FIGURES = 50
MAX_BYTES_PER_IMAGE = 8_000_000

FIGURE_MENTION_PATTERN = re.compile(r"\bFig(?:ure)?\.?\s+\d+[A-Za-z]?")

_EXTENSION_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


@dataclass(frozen=True)
class RawFigure:
    """One embedded image recovered from a PDF page."""

    page: int
    index: int
    image_bytes: bytes
    mime_type: str
    sha256: str


@dataclass(frozen=True)
class FigureIngestResult:
    """Embedded images recovered from a PDF upload."""

    figures: tuple[RawFigure, ...]
    truncated: bool
    skipped: int


def _mime_type_for_name(name: str) -> str:
    """Map a pypdf image name to a MIME type by file extension."""
    lowered = name.lower()
    for extension, mime_type in _EXTENSION_MIME_TYPES.items():
        if lowered.endswith(extension):
            return mime_type
    return "application/octet-stream"


def extract_figures_from_pdf(
    data: bytes,
    *,
    max_figures: int = MAX_FIGURES,
    max_bytes_per_image: int = MAX_BYTES_PER_IMAGE,
) -> FigureIngestResult:
    """Recover embedded raster images in page order.

    Images that are unreadable, oversized, or beyond max_figures are
    skipped or truncate the result rather than failing the ingest.
    """
    if not data.startswith(PDF_MAGIC_PREFIX):
        raise ValueError("The uploaded file is not a PDF document.")
    if max_figures < 1:
        raise ValueError("max_figures must be at least 1.")
    if max_bytes_per_image < 1:
        raise ValueError("max_bytes_per_image must be at least 1.")

    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as exc:
        raise ValueError("The uploaded PDF could not be read.") from exc

    figures: list[RawFigure] = []
    skipped = 0
    truncated = False

    for number, page in enumerate(reader.pages[:MAX_PDF_PAGES], start=1):
        try:
            images = list(page.images)
        except Exception:
            # One unreadable page (or missing image support) must not
            # fail the whole ingest.
            continue
        for position, image in enumerate(images, start=1):
            if len(figures) >= max_figures:
                truncated = True
                break
            try:
                image_bytes = bytes(image.data)
                mime_type = _mime_type_for_name(image.name)
            except Exception:
                skipped += 1
                continue
            if not image_bytes or len(image_bytes) > max_bytes_per_image:
                skipped += 1
                continue
            figures.append(
                RawFigure(
                    page=number,
                    index=position,
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    sha256=hashlib.sha256(image_bytes).hexdigest(),
                )
            )
        if truncated:
            break

    return FigureIngestResult(figures=tuple(figures), truncated=truncated, skipped=skipped)


def find_figure_mentions(text: str) -> tuple[str, ...]:
    """Return generic figure labels (e.g. 'Figure 3') mentioned in text."""
    return tuple(match.group(0) for match in FIGURE_MENTION_PATTERN.finditer(text))
