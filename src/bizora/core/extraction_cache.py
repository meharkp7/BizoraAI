"""File cache for methodology extraction drafts, keyed by paper hash.

Extraction calls are the credit burner, so a draft is written once per
(paper text, provider, cache version) and replayed on repeat uploads.
The cache lives outside the repository under the platform cache dir and
never touches the database. Bump CACHE_VERSION whenever the extraction
prompt or graph schema changes meaningfully.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from bizora.contracts.graph import MethodologyGraph
from bizora.providers.base import MethodologyExtractionRequest, MethodologyProvider

CACHE_VERSION = 1


def cache_dir() -> Path:
    """Return the extraction cache directory, honoring test overrides."""
    override = os.environ.get("BIZORA_CACHE_DIR")
    if override:
        return Path(override) / "bizora" / "extraction"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "bizora" / "extraction"


def draft_key(paper_text: str, provider: MethodologyProvider) -> str:
    """Build a stable cache key for one extraction request."""
    digest = hashlib.sha256(paper_text.encode("utf-8")).hexdigest()[:32]
    provider_name = getattr(provider, "provider_name", type(provider).__name__)
    safe_provider = "".join(char if char.isalnum() or char in "-_." else "_" for char in provider_name)
    return f"{digest}-{safe_provider}-v{CACHE_VERSION}"


def load_draft(key: str) -> MethodologyGraph | None:
    """Return the cached draft for a key, or None on any miss."""
    path = cache_dir() / f"{key}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        return MethodologyGraph.model_validate(payload)
    except ValueError:
        return None


def save_draft(key: str, graph: MethodologyGraph) -> None:
    """Persist one draft; a failed write never fails the extraction."""
    try:
        directory = cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{key}.json").write_text(
            graph.model_dump_json(), encoding="utf-8"
        )
    except OSError:
        pass


def rekey_draft(graph: MethodologyGraph, request: MethodologyExtractionRequest) -> MethodologyGraph:
    """Re-key a cached draft onto a new request's trusted identifiers."""
    source_ids = list(dict.fromkeys([*graph.source_ids, request.source_id]))
    return graph.model_copy(
        update={
            "project_id": request.project_id,
            "graph_id": request.graph_id,
            "version": 1,
            "parent_version": None,
            "created_by": request.created_by,
            "title": request.title or graph.title,
            "source_ids": tuple(source_ids),
        }
    )
