"""Tests for figure/diagram image ingestion from PDFs."""

from bizora.core.figure_ingest import (
    extract_figures_from_pdf,
    find_figure_mentions,
)
from bizora.core.papers import is_valid_figure_id, suggest_figure_id
from bizora.core.pdf import extract_page_texts


def make_fake_pdf_with_images(image_count: int, text: str = "") -> bytes:
    """Assemble a FAKE one-page PDF with raw RGB image XObjects."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content_stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("latin-1")
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"",
        b"<< /Length "
        + str(len(content_stream)).encode("latin-1")
        + b" >>\nstream\n"
        + content_stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    xobject_refs = []
    for position in range(image_count):
        raw = bytes([10 + position, 20, 30, 40, 50, 60 + position])
        objects.append(
            b"<< /Type /XObject /Subtype /Image /Width 2 /Height 1 "
            b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Length "
            + str(len(raw)).encode("latin-1")
            + b" >>\nstream\n"
            + raw
            + b"\nendstream"
        )
        xobject_refs.append(f"/Im{position + 1} {len(objects)} 0 R")
    objects[2] = (
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> "
        b"/XObject << " + " ".join(xobject_refs).encode("latin-1") + b" >> >> >>"
    )
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
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")
    return out


def test_extracts_embedded_images_in_page_order() -> None:
    result = extract_figures_from_pdf(
        make_fake_pdf_with_images(2, text="See Figure 1 and Figure 2.")
    )

    assert len(result.figures) == 2
    assert result.truncated is False
    assert result.skipped == 0
    first, second = result.figures
    assert (first.page, first.index) == (1, 1)
    assert (second.page, second.index) == (1, 2)
    assert first.mime_type == "image/png"
    assert first.image_bytes.startswith(b"\x89PNG")
    assert len(first.sha256) == 64
    assert first.sha256 != second.sha256


def test_pdf_without_images_returns_empty() -> None:
    result = extract_figures_from_pdf(make_fake_pdf_with_images(0, text="No art."))

    assert result.figures == ()
    assert result.truncated is False
    assert result.skipped == 0


def test_max_figures_truncates() -> None:
    result = extract_figures_from_pdf(make_fake_pdf_with_images(2), max_figures=1)

    assert len(result.figures) == 1
    assert result.truncated is True


def test_oversized_images_are_skipped() -> None:
    result = extract_figures_from_pdf(make_fake_pdf_with_images(2), max_bytes_per_image=1)

    assert result.figures == ()
    assert result.skipped == 2
    assert result.truncated is False


def test_non_pdf_rejected() -> None:
    try:
        extract_figures_from_pdf(b"not a pdf")
    except ValueError as exc:
        assert "not a PDF" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_invalid_limits_rejected() -> None:
    pdf = make_fake_pdf_with_images(1)
    for kwargs in ({"max_figures": 0}, {"max_bytes_per_image": 0}):
        try:
            extract_figures_from_pdf(pdf, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {kwargs}")


def test_find_figure_mentions() -> None:
    assert find_figure_mentions("See Figure 3 and Fig. 2a for detail.") == (
        "Figure 3",
        "Fig. 2a",
    )
    assert find_figure_mentions("No labels here.") == ()


def test_page_texts_support_surrounding_text() -> None:
    pages = extract_page_texts(make_fake_pdf_with_images(1, text="Caption words."))

    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert pages[0].text == "Caption words."


def test_figure_id_helpers() -> None:
    figure_id = suggest_figure_id("Some Paper Title!", page=3, index=2, short_hash="abc123")

    assert figure_id == "some-paper-title-p3-f2-abc123"
    assert is_valid_figure_id(figure_id) is True
    assert is_valid_figure_id("bad id!") is False
