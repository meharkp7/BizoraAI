"""Tests for vector-figure recovery via page renders."""

import io

import pytest
from PIL import Image

from bizora.core.page_render import (
    TILE_INDEX_OFFSET,
    PdfRenderError,
    cut_tiles,
    harvest_page_tiles,
)


def make_quadrant_image() -> Image.Image:
    """100x80 image with a distinct color per quadrant."""
    image = Image.new("RGB", (100, 80))
    pixels = image.load()
    assert pixels is not None
    for y in range(80):
        for x in range(100):
            pixels[x, y] = (
                (255, 0, 0) if (x < 50) == (y < 40) else (0, 0, 255)
            )
    return image


def test_cut_tiles_returns_four_row_major_quadrants() -> None:
    """Each quadrant keeps its own corner colors at half size."""
    tiles = cut_tiles(make_quadrant_image())

    assert len(tiles) == 4
    for raw in tiles:
        tile = Image.open(io.BytesIO(raw))
        assert tile.size == (50, 40)
    assert Image.open(io.BytesIO(tiles[0])).getpixel((5, 5)) == (255, 0, 0)
    assert Image.open(io.BytesIO(tiles[1])).getpixel((5, 5)) == (0, 0, 255)
    assert Image.open(io.BytesIO(tiles[2])).getpixel((5, 5)) == (0, 0, 255)
    assert Image.open(io.BytesIO(tiles[3])).getpixel((5, 5)) == (255, 0, 0)


def test_harvest_skips_without_poppler(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing poppler yields no tiles (embedded path unchanged)."""
    monkeypatch.setattr(
        "bizora.core.page_render.pdftoppm_available", lambda: False
    )

    assert (
        harvest_page_tiles(b"%PDF", {2: "See Figure 1."}, frozenset(), budget=8)
        == ()
    )


def test_harvest_gates_on_mentions_and_embedded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only mentioning, embedded-free pages render, in page order."""
    rendered: list[int] = []

    def fake_render(pdf_bytes: bytes, page: int, *, dpi: int = 150) -> Image.Image:
        rendered.append(page)
        return make_quadrant_image()

    monkeypatch.setattr("bizora.core.page_render.pdftoppm_available", lambda: True)
    monkeypatch.setattr("bizora.core.page_render.render_page", fake_render)

    tiles = harvest_page_tiles(
        b"%PDF",
        {1: "Title page.", 2: "See Figure 1.", 3: "See Fig. 3.", 5: "See Figure 5."},
        frozenset({5}),
        budget=8,
    )

    assert rendered == [2, 3]
    assert [(tile.page, tile.index) for tile in tiles] == [
        (2, TILE_INDEX_OFFSET),
        (2, TILE_INDEX_OFFSET + 1),
        (2, TILE_INDEX_OFFSET + 2),
        (2, TILE_INDEX_OFFSET + 3),
        (3, TILE_INDEX_OFFSET),
        (3, TILE_INDEX_OFFSET + 1),
        (3, TILE_INDEX_OFFSET + 2),
        (3, TILE_INDEX_OFFSET + 3),
    ]
    assert len({tile.sha256 for tile in tiles}) == 2


def test_harvest_respects_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """The harvest stops once the figure budget runs out."""
    monkeypatch.setattr("bizora.core.page_render.pdftoppm_available", lambda: True)
    monkeypatch.setattr(
        "bizora.core.page_render.render_page",
        lambda pdf_bytes, page, *, dpi=150: make_quadrant_image(),
    )

    tiles = harvest_page_tiles(
        b"%PDF", {2: "See Figure 1."}, frozenset(), budget=2
    )

    assert len(tiles) == 2
    assert harvest_page_tiles(b"%PDF", {2: "See Figure 1."}, frozenset(), budget=0) == ()


def test_harvest_skips_failed_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """One failed render never sinks the other pages."""
    calls: list[int] = []

    def flaky_render(pdf_bytes: bytes, page: int, *, dpi: int = 150) -> Image.Image:
        calls.append(page)
        if page == 2:
            raise PdfRenderError("boom")
        return make_quadrant_image()

    monkeypatch.setattr("bizora.core.page_render.pdftoppm_available", lambda: True)
    monkeypatch.setattr("bizora.core.page_render.render_page", flaky_render)

    tiles = harvest_page_tiles(
        b"%PDF",
        {2: "See Figure 1.", 3: "See Fig. 3."},
        frozenset(),
        budget=8,
    )

    assert calls == [2, 3]
    assert {tile.page for tile in tiles} == {3}
