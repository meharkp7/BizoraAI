"""Tests for paper-import source resolution and bounded PDF download."""

import asyncio

import httpx
import pytest
from tests.unit.test_papers_api import make_pdf_bytes

from bizora.core.paper_import import (
    PaperDownloadError,
    download_paper_pdf,
    resolve_paper_source,
)


def test_resolve_arxiv_identifier_forms() -> None:
    bare = resolve_paper_source("1706.03762v7")
    prefixed = resolve_paper_source("arxiv:1706.03762v7")
    landing = resolve_paper_source("https://arxiv.org/abs/1706.03762v7")
    pdf_url = resolve_paper_source("https://arxiv.org/pdf/1706.03762v7.pdf?download=1")

    for resolved in (bare, prefixed, landing, pdf_url):
        assert resolved.kind == "arxiv"
        assert resolved.url == "https://arxiv.org/pdf/1706.03762v7"
        assert resolved.filename == "1706.03762v7.pdf"


def test_resolve_legacy_arxiv_identifier() -> None:
    resolved = resolve_paper_source("hep-th/9901001")

    assert resolved.kind == "arxiv"
    assert resolved.url == "https://arxiv.org/pdf/hep-th/9901001"
    assert resolved.filename == "hep-th-9901001.pdf"


def test_resolve_doi_forms() -> None:
    bare = resolve_paper_source("10.1038/s41586-020-2649-2")
    prefixed = resolve_paper_source("doi:10.1038/s41586-020-2649-2")
    url = resolve_paper_source("https://doi.org/10.1038/s41586-020-2649-2")

    for resolved in (bare, prefixed, url):
        assert resolved.kind == "doi"
        assert resolved.url == "https://doi.org/10.1038/s41586-020-2649-2"
        assert resolved.filename == "doi-10.1038-s41586-020-2649-2.pdf"


def test_resolve_direct_pdf_url() -> None:
    resolved = resolve_paper_source("https://example.com/papers/study.pdf?download=1#page=2")

    assert resolved.kind == "url"
    assert resolved.url == "https://example.com/papers/study.pdf?download=1"
    assert resolved.filename == "study.pdf"


def test_resolve_direct_url_without_filename() -> None:
    resolved = resolve_paper_source("https://example.com/?id=123")

    assert resolved.kind == "url"
    assert resolved.url == "https://example.com/?id=123"
    assert resolved.filename == "paper.pdf"


@pytest.mark.parametrize(
    "source",
    [
        "",
        "   ",
        "not a paper",
        "ftp://example.com/paper.pdf",
        "https://",
        "https:///paper.pdf",
        "https://user:pass@example.com/paper.pdf",
        "10.1234",
        "arxiv:9999",
    ],
)
def test_resolve_rejects_invalid_sources(source: str) -> None:
    with pytest.raises(ValueError):
        resolve_paper_source(source)


def test_download_accepts_pdf_magic_with_generic_content_type() -> None:
    pdf_bytes = make_pdf_bytes("Downloaded methods.")
    resolved = resolve_paper_source("https://example.com/paper.pdf")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Accept"] == "application/pdf"
        return httpx.Response(
            200,
            content=pdf_bytes,
            headers={"Content-Type": "application/octet-stream"},
        )

    async def run_test() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            downloaded = await download_paper_pdf(resolved, max_bytes=1024 * 1024, client=client)

        assert downloaded.data == pdf_bytes
        assert downloaded.filename == "paper.pdf"
        assert downloaded.source_url == "https://example.com/paper.pdf"

    asyncio.run(run_test())


def test_download_rejects_oversize_content_length_without_body() -> None:
    resolved = resolve_paper_source("https://example.com/paper.pdf")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200,
            content=b"too large",
            headers={"Content-Length": str(1024 * 1024 + 1)},
        )

    async def run_test() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError, match="exceeds"):
                await download_paper_pdf(resolved, max_bytes=1024 * 1024, client=client)

    asyncio.run(run_test())
    assert seen == ["https://example.com/paper.pdf"]


def test_download_rejects_non_pdf_body() -> None:
    resolved = resolve_paper_source("https://example.com/paper.pdf")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html>not a pdf</html>",
            headers={"Content-Type": "text/html"},
        )

    async def run_test() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError, match="not a PDF"):
                await download_paper_pdf(resolved, max_bytes=1024 * 1024, client=client)

    asyncio.run(run_test())


def test_download_maps_http_failures_to_download_error() -> None:
    resolved = resolve_paper_source("https://example.com/paper.pdf")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"missing")

    async def run_test() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(PaperDownloadError, match="HTTP 404"):
                await download_paper_pdf(resolved, max_bytes=1024 * 1024, client=client)

    asyncio.run(run_test())
