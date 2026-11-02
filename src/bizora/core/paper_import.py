
"""Resolve arXiv/DOI/URL paper references and download their PDFs safely.

Resolution is pure and fully unit-testable: an arXiv ID, DOI, or direct
URL becomes a download URL plus a safe filename. Downloading is bounded
by the caller's byte limit, follows redirects, and only accepts bodies
that start with the PDF magic prefix — a misleading content type never
passes a non-PDF through, and an honest length header aborts oversize
responses before the body is read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import SplitResult, quote, urlsplit, urlunsplit

import httpx

PDF_MAGIC_PREFIX = b"%PDF"
PDF_ACCEPT_HEADER = "application/pdf"
MAX_FILENAME_LENGTH = 128

PaperSourceKind = Literal["arxiv", "doi", "url"]

_ARXIV_IDENTITY = re.compile(r"\d{4}\.\d{4,5}(?:v\d+)?\Z")
_ARXIV_LEGACY = re.compile(r"[a-z][a-z\-]*(?:\.[A-Za-z]{2})?/\d{7}(?:v\d+)?\Z")
_DOI = re.compile(r"10\.\d{4,9}/\S+\Z")
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._\-]+")


class PaperDownloadError(RuntimeError):
    """Raised when a paper PDF cannot be fetched from its source."""


@dataclass(frozen=True)
class PaperDownloadSource:
    """A resolved paper reference: where to fetch and what to call it."""

    kind: PaperSourceKind
    source: str
    url: str
    filename: str


@dataclass(frozen=True)
class DownloadedPaper:
    """A fetched PDF plus the source facts the importer needs."""

    data: bytes
    filename: str
    source_url: str
    content_type: str | None


def _safe_filename(stem: str) -> str:
    """Reduce free text to a safe `.pdf` filename of bounded length."""
    cleaned = _UNSAFE_FILENAME.sub("-", stem).strip("-._")
    if not cleaned:
        cleaned = "paper"
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    if len(cleaned) > MAX_FILENAME_LENGTH:
        cleaned = f"{cleaned[: MAX_FILENAME_LENGTH - 4]}.pdf"
    return cleaned


def _arxiv_filename(arxiv_id: str) -> str:
    """Build a filename for an arXiv ID (legacy IDs contain a slash)."""
    return _safe_filename(arxiv_id.replace("/", "-"))


def _doi_filename(doi: str) -> str:
    """Build a filename for a DOI that survives filesystems and URLs."""
    return _safe_filename(f"doi-{doi.replace('/', '-')}")


def _is_arxiv_id(value: str) -> bool:
    """Return whether a value is a bare new- or legacy-style arXiv ID."""
    return _ARXIV_IDENTITY.match(value) is not None or _ARXIV_LEGACY.match(value) is not None


def _arxiv_url(arxiv_id: str) -> str:
    """Return the direct PDF URL for a validated arXiv ID."""
    return f"https://arxiv.org/pdf/{arxiv_id}"


def _doi_url(doi: str) -> str:
    """Return the resolver URL for a validated DOI, encoding the suffix."""
    prefix, suffix = doi.split("/", 1)
    return f"https://doi.org/{prefix}/{quote(suffix, safe='-._~')}"


def _strip_prefix(value: str, prefix: str) -> str | None:
    """Strip a case-insensitive `prefix:` marker, or return None."""
    lowered = value.lower()
    marker = f"{prefix.lower()}:"
    if lowered.startswith(marker):
        return value[len(marker) :].strip()
    return None


def _arxiv_id_from_url(parts: SplitResult) -> str | None:
    """Extract an arXiv ID from an arXiv abs/pdf path, if present."""
    path = parts.path
    for marker in ("/abs/", "/pdf/"):
        if marker in path:
            candidate = path.split(marker, 1)[1].split("/")[0]
            if candidate.lower().endswith(".pdf"):
                candidate = candidate[: -len(".pdf")]
            if candidate and _is_arxiv_id(candidate):
                return candidate
    return None


def _doi_from_doi_url(parts: SplitResult) -> str | None:
    """Extract a DOI from a doi.org/dx.doi.org path, if present."""
    path = parts.path
    candidate = path.lstrip("/")
    if candidate and _DOI.match(candidate) is not None:
        return candidate
    return None


def resolve_paper_source(source: str) -> PaperDownloadSource:
    """Resolve an arXiv ID, DOI, or URL to a downloadable PDF source."""
    value = source.strip()
    if not value:
        raise ValueError("A paper source must not be empty.")

    arxiv_candidate = _strip_prefix(value, "arxiv")
    if arxiv_candidate is not None:
        if not _is_arxiv_id(arxiv_candidate):
            raise ValueError(f"Invalid arXiv identifier: {source.strip()}.")
        return PaperDownloadSource(
            kind="arxiv",
            source=value,
            url=_arxiv_url(arxiv_candidate),
            filename=_arxiv_filename(arxiv_candidate),
        )

    doi_candidate = _strip_prefix(value, "doi")
    if doi_candidate is not None:
        if _DOI.match(doi_candidate) is None:
            raise ValueError(f"Invalid DOI: {source.strip()}.")
        return PaperDownloadSource(
            kind="doi",
            source=value,
            url=_doi_url(doi_candidate),
            filename=_doi_filename(doi_candidate),
        )

    if _is_arxiv_id(value):
        return PaperDownloadSource(
            kind="arxiv",
            source=value,
            url=_arxiv_url(value),
            filename=_arxiv_filename(value),
        )
    if _DOI.match(value) is not None:
        return PaperDownloadSource(
            kind="doi",
            source=value,
            url=_doi_url(value),
            filename=_doi_filename(value),
        )

    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise ValueError(f"Invalid paper URL: {source.strip()}.") from exc
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Invalid paper source: {source.strip()}. Use an arXiv ID, DOI, or http(s) URL.")
    if not parts.hostname or parts.username or parts.password:
        raise ValueError(f"Invalid paper URL: {source.strip()}.")

    host = parts.hostname.lower()
    if host in ("arxiv.org", "export.arxiv.org"):
        arxiv_id = _arxiv_id_from_url(parts)
        if arxiv_id is None:
            raise ValueError(f"Invalid arXiv URL: {source.strip()}.")
        return PaperDownloadSource(
            kind="arxiv",
            source=value,
            url=_arxiv_url(arxiv_id),
            filename=_arxiv_filename(arxiv_id),
        )
    if host in ("doi.org", "dx.doi.org"):
        doi = _doi_from_doi_url(parts)
        if doi is None:
            raise ValueError(f"Invalid DOI URL: {source.strip()}.")
        return PaperDownloadSource(
            kind="doi",
            source=value,
            url=_doi_url(doi),
            filename=_doi_filename(doi),
        )

    normalized = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    raw_name = parts.path.rsplit("/", 1)[-1] if parts.path else ""
    return PaperDownloadSource(
        kind="url",
        source=value,
        url=normalized,
        filename=_safe_filename(raw_name),
    )


async def _download_with_client(
    client: httpx.AsyncClient,
    resolved: PaperDownloadSource,
    *,
    max_bytes: int,
) -> DownloadedPaper:
    """Fetch one PDF with a caller-owned client, enforcing the byte cap."""
    headers = {"Accept": PDF_ACCEPT_HEADER}
    try:
        async with client.stream(
            "GET", resolved.url, headers=headers, follow_redirects=True
        ) as response:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise PaperDownloadError(
                    f"Paper download failed with HTTP {response.status_code}."
                ) from exc
            declared = response.headers.get("content-length")
            if declared is not None:
                try:
                    declared_bytes = int(declared)
                except ValueError:
                    declared_bytes = None
                if declared_bytes is not None and declared_bytes > max_bytes:
                    raise ValueError(
                        f"The downloaded file exceeds the {max_bytes} byte limit."
                    )
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise ValueError(
                        f"The downloaded file exceeds the {max_bytes} byte limit."
                    )
    except httpx.HTTPError as exc:
        raise PaperDownloadError(f"Paper download failed: {exc}.") from exc
    data = bytes(body)
    if not data.startswith(PDF_MAGIC_PREFIX):
        raise ValueError("The downloaded file is not a PDF document.")
    return DownloadedPaper(
        data=data,
        filename=resolved.filename,
        source_url=resolved.url,
        content_type=response.headers.get("content-type"),
    )


async def download_paper_pdf(
    resolved: PaperDownloadSource,
    *,
    max_bytes: int,
    client: httpx.AsyncClient | None = None,
    timeout: float = 30.0,
) -> DownloadedPaper:
    """Download a resolved paper source, enforcing size and PDF checks."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be at least 1.")
    if client is not None:
        return await _download_with_client(client, resolved, max_bytes=max_bytes)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as owned:
        return await _download_with_client(owned, resolved, max_bytes=max_bytes)
