
"""Extract plain text from uploaded paper PDFs."""

import hashlib
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

PDF_MAGIC_PREFIX = b"%PDF"
MAX_PDF_PAGES = 120


@dataclass(frozen=True)
class PdfText:
    """Text extracted from a PDF upload."""

    text: str
    page_count: int
    truncated: bool
    sha256: str
    doc_title: str | None
    doc_author: str | None


def _clean_metadata(value: object) -> str | None:
    """Return stripped metadata text, or None when absent or blank."""
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned if cleaned else None


def extract_text_from_pdf(data: bytes, *, max_chars: int) -> PdfText:
    """Extract page-ordered text, rejecting non-PDF or unreadable input.

    Pages are prefixed with [Page N] markers so downstream extraction can
    cite page numbers as evidence.
    """
    if not data.startswith(PDF_MAGIC_PREFIX):
        raise ValueError("The uploaded file is not a PDF document.")
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1.")

    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as exc:
        raise ValueError("The uploaded PDF could not be read.") from exc

    pages = reader.pages[:MAX_PDF_PAGES]
    chunks: list[str] = []
    for number, page in enumerate(pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            # One unreadable page must not fail the whole ingest.
            text = ""
        text = text.strip()
        if text:
            chunks.append(f"[Page {number}]\n{text}")

    full = "\n\n".join(chunks).strip()
    if not full:
        raise ValueError("No readable text was found in the uploaded PDF.")

    try:
        metadata = reader.metadata
    except Exception:
        metadata = None
    doc_title = _clean_metadata(getattr(metadata, "title", None))
    doc_author = _clean_metadata(getattr(metadata, "author", None))

    digest = hashlib.sha256(data).hexdigest()
    truncated = len(reader.pages) > MAX_PDF_PAGES
    if len(full) > max_chars:
        return PdfText(
            text=full[:max_chars],
            page_count=len(reader.pages),
            truncated=True,
            sha256=digest,
            doc_title=doc_title,
            doc_author=doc_author,
        )
    return PdfText(
        text=full,
        page_count=len(reader.pages),
        truncated=truncated,
        sha256=digest,
        doc_title=doc_title,
        doc_author=doc_author,
    )
