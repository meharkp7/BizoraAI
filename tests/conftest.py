"""Shared pytest fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_extraction_cache(tmp_path, monkeypatch):
    """Point the extraction cache at a fresh temp dir per test.

    Extraction tests must neither read the developer's real cache nor
    pollute it, and cache hits must never leak across tests.
    """
    monkeypatch.setenv("BIZORA_CACHE_DIR", str(tmp_path / "cache"))
