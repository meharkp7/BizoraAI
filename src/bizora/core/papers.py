
"""Paper-agnostic helpers: metadata shaping and stable identifier suggestions."""

import re

DEFAULT_CREATED_BY = "paper-upload"
SOURCE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
MAX_SLUG_LENGTH = 40


def slugify(text: str) -> str:
    """Reduce free text to a short lowercase identifier stem."""
    stem = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    stem = re.sub(r"-{2,}", "-", stem)
    return stem[:MAX_SLUG_LENGTH].strip("-") or "paper"


def split_authors(author: str | None) -> tuple[str, ...]:
    """Split a document author string conservatively.

    Only unambiguous separators (semicolons, slashes) split names; anything
    else stays one entry rather than risk corrupting a name.
    """
    if author is None:
        return ()
    parts = [part.strip() for part in re.split(r"\s*;\s*|\s+/\s+", author)]
    return tuple(part for part in parts if part)


def suggest_project_id(stem: str, short_hash: str) -> str:
    """Suggest a stable, unique project id for an upload."""
    return f"{slugify(stem)}-{short_hash}"


def suggest_graph_id(stem: str, short_hash: str) -> str:
    """Suggest a stable, unique graph id for an upload."""
    return f"{slugify(stem)}-graph-{short_hash}"


def suggest_source_id(short_hash: str) -> str:
    """Suggest a stable source id that satisfies evidence references."""
    return f"paper-{short_hash}"


def is_valid_source_id(value: str) -> bool:
    """Return whether a source id can appear in evidence references."""
    return len(value) <= 128 and SOURCE_ID_PATTERN.match(value) is not None
