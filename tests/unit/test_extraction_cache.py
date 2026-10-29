"""Unit tests for the extraction draft cache."""

import asyncio

from bizora.contracts.graph import (
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.core.extraction_cache import cache_dir, draft_key
from bizora.core.extraction_service import MethodologyExtractionService
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyExtractionResult,
)


class CountingProvider:
    """Provider fake that counts extraction calls."""

    provider_name = "counting-fake"

    def __init__(self, graph: MethodologyGraph) -> None:
        self.graph = graph
        self.calls = 0

    async def extract_methodology(
        self,
        request: MethodologyExtractionRequest,
    ) -> MethodologyExtractionResult:
        self.calls += 1
        return MethodologyExtractionResult(
            draft_graph=self.graph,
            provider_name="counting-fake",
            model_name="test-model",
        )


def make_request(**overrides) -> MethodologyExtractionRequest:
    values = {
        "paper_text": "The authors cool the chip before measuring.",
        "project_id": "project-1",
        "graph_id": "graph-1",
        "source_id": "paper-1",
        "created_by": "test-user",
        "title": "Cached methodology",
    }
    values.update(overrides)
    return MethodologyExtractionRequest(**values)


def make_graph() -> MethodologyGraph:
    return MethodologyGraph(
        schema_version="1.0",
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Cached methodology",
        source_ids=("paper-1",),
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, label="Input data"),
        ),
        created_by="test-user",
    )


def run(coro):
    return asyncio.run(coro)


def test_second_extract_with_same_text_skips_provider() -> None:
    """A repeat upload replays the cached draft without calling the model."""
    provider = CountingProvider(make_graph())
    first = run(MethodologyExtractionService.extract_draft(provider, make_request()))
    second = run(MethodologyExtractionService.extract_draft(provider, make_request()))

    assert provider.calls == 1
    assert second.nodes == first.nodes
    assert list(cache_dir().glob("*.json")) != []


def test_cached_draft_rekeys_to_new_identifiers() -> None:
    """Cache hits carry the new request's ids, not the original upload's."""
    provider = CountingProvider(make_graph())
    run(MethodologyExtractionService.extract_draft(provider, make_request()))
    replayed = run(
        MethodologyExtractionService.extract_draft(
            provider,
            make_request(project_id="project-2", graph_id="graph-2", created_by="other"),
        )
    )

    assert provider.calls == 1
    assert replayed.project_id == "project-2"
    assert replayed.graph_id == "graph-2"
    assert replayed.created_by == "other"
    assert replayed.version == 1


def test_changed_text_misses_and_different_keys() -> None:
    """Different paper text hashes to a different key and calls the model."""
    provider = CountingProvider(make_graph())
    run(MethodologyExtractionService.extract_draft(provider, make_request()))
    assert (
        draft_key("other text", provider)
        != draft_key("The authors cool the chip before measuring.", provider)
    )
    run(
        MethodologyExtractionService.extract_draft(
            provider, make_request(paper_text="other text")
        )
    )
    assert provider.calls == 2


def test_corrupt_cache_entry_falls_back_to_provider() -> None:
    """An unreadable cache file behaves as a miss, not a crash."""
    provider = CountingProvider(make_graph())
    key = draft_key("The authors cool the chip before measuring.", provider)
    cache_dir().mkdir(parents=True, exist_ok=True)
    (cache_dir() / f"{key}.json").write_text("not json", encoding="utf-8")

    graph = run(MethodologyExtractionService.extract_draft(provider, make_request()))

    assert provider.calls == 1
    assert graph.nodes[0].id == "input"
