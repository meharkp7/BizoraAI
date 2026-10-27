"""Tests for PDF text ingestion."""

from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter

from bizora.core.pdf import MAX_PDF_PAGES, extract_text_from_pdf


def make_pdf_bytes(text: str) -> bytes:
    """Assemble a minimal one-page PDF with computed xref offsets."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length "
        + str(len(stream)).encode("latin-1")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")
    return out


def make_blank_pdf_bytes() -> bytes:
    """Assemble a one-page PDF whose content stream has no text."""
    return make_pdf_bytes("").replace(b"() Tj", b"")


def test_extracts_page_text_with_markers() -> None:
    pdf = extract_text_from_pdf(
        make_pdf_bytes("Hello AlphaFold extraction"), max_chars=1000
    )

    assert pdf.text == "[Page 1]\nHello AlphaFold extraction"
    assert pdf.page_count == 1
    assert pdf.truncated is False
    assert len(pdf.sha256) == 64
    assert pdf.doc_title is None
    assert pdf.doc_author is None


def test_extracts_document_metadata() -> None:
    reader = PdfReader(BytesIO(make_pdf_bytes("Some body text.")))
    writer = PdfWriter()
    writer.add_page(reader.pages[0])
    writer.add_metadata({"/Title": "SRAM Study", "/Author": "  Jane Doe  "})
    buffer = BytesIO()
    writer.write(buffer)

    pdf = extract_text_from_pdf(buffer.getvalue(), max_chars=1000)

    assert pdf.doc_title == "SRAM Study"
    assert pdf.doc_author == "Jane Doe"
    assert "[Page 1]" in pdf.text


def test_long_text_truncates() -> None:
    pdf = extract_text_from_pdf(make_pdf_bytes("Hello AlphaFold"), max_chars=5)

    assert pdf.text == "[Page"
    assert pdf.truncated is True


def test_non_pdf_rejected() -> None:
    with pytest.raises(ValueError, match="not a PDF"):
        extract_text_from_pdf(b"not a pdf", max_chars=1000)


def test_truncated_pdf_rejected() -> None:
    with pytest.raises(ValueError, match="could not be read"):
        extract_text_from_pdf(b"%PDF-1.4 truncated", max_chars=1000)


def test_blank_pdf_rejected() -> None:
    with pytest.raises(ValueError, match="No readable text"):
        extract_text_from_pdf(make_blank_pdf_bytes(), max_chars=1000)


def test_page_cap_documented() -> None:
    assert MAX_PDF_PAGES == 120
