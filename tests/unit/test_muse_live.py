"""LIVE Muse test: makes one real billable Responses API call.

Skipped unless BOTH are set: MUSE_API_KEY and BIZORA_LIVE_TESTS=1. Normal
gate runs (pytest, CI) never set BIZORA_LIVE_TESTS, so this module stays
silent there. The Phase 3a live experiment runs separately under /tmp.
"""

import asyncio
import os

import pytest

from bizora.providers.base import MethodologyExtractionRequest
from bizora.providers.muse import MuseMethodologyProvider

LIVE_ENABLED = bool(os.getenv("MUSE_API_KEY")) and os.getenv("BIZORA_LIVE_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE_ENABLED,
    reason="live Muse test: needs MUSE_API_KEY and BIZORA_LIVE_TESTS=1",
)


def test_live_extract_tiny_text() -> None:
    async def run_test() -> None:
        provider = MuseMethodologyProvider()
        result = await provider.extract_methodology(
            MethodologyExtractionRequest(
                paper_text=(
                    "[Page 1]\nWe normalize input images, then train a small "
                    "classifier with cross-entropy loss."
                ),
                project_id="live-probe",
                graph_id="live-probe-graph",
                source_id="live-probe-paper",
                created_by="live-test",
                title="Live probe",
            )
        )
        assert result.provider_name == "muse"
        assert result.draft_graph.graph_id == "live-probe-graph"
        assert provider.last_usage is not None

    asyncio.run(run_test())
