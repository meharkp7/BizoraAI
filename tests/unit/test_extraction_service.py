
"""Tests for methodology extraction orchestration."""

import asyncio

import pytest

from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
    RelationKind,
)
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.extraction_service import MethodologyExtractionService
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyExtractionResult,
)


class FakeMethodologyProvider:
    """Provider fake that returns a predetermined extraction result."""

    def __init__(self, graph: MethodologyGraph) -> None:
        self.graph = graph

    async def extract_methodology(
        self,
        request: MethodologyExtractionRequest,
    ) -> MethodologyExtractionResult:
        return MethodologyExtractionResult(
            draft_graph=self.graph,
            provider_name="fake",
            model_name="test-model",
        )


def make_request() -> MethodologyExtractionRequest:
    return MethodologyExtractionRequest(
        paper_text="The authors normalize the input before processing.",
        project_id="project-1",
        graph_id="graph-1",
        source_id="paper-1",
        created_by="test-user",
        title="Test methodology",
    )


def make_graph(
    *,
    project_id: str = "project-1",
    graph_id: str = "graph-1",
    edges: tuple[GraphEdge, ...] = (),
) -> MethodologyGraph:
    return MethodologyGraph(
        schema_version="1.0",
        project_id=project_id,
        graph_id=graph_id,
        version=1,
        title="Test methodology",
        source_ids=("paper-1",),
        nodes=(
            GraphNode(
                id="input",
                kind=NodeKind.INPUT,
                label="Input data",
            ),
            GraphNode(
                id="preprocess",
                kind=NodeKind.PREPROCESSING,
                label="Normalize input",
            ),
        ),
        edges=edges,
        created_by="test-user",
    )


def test_extract_draft_returns_valid_graph() -> None:
    async def run_test() -> None:
        request = make_request()
        graph = make_graph()
        provider = FakeMethodologyProvider(graph)

        result = await MethodologyExtractionService.extract_draft(
            provider,
            request,
        )

        assert result == graph
        assert result.project_id == request.project_id
        assert result.graph_id == request.graph_id
        assert result.version == 1

    asyncio.run(run_test())


def test_extract_draft_rejects_mismatched_project_id() -> None:
    async def run_test() -> None:
        provider = FakeMethodologyProvider(
            make_graph(project_id="different-project")
        )

        with pytest.raises(BizoraError) as exc_info:
            await MethodologyExtractionService.extract_draft(
                provider,
                make_request(),
            )

        assert exc_info.value.code == ErrorCode.INVALID_GRAPH

    asyncio.run(run_test())


def test_extract_draft_rejects_mismatched_graph_id() -> None:
    async def run_test() -> None:
        provider = FakeMethodologyProvider(
            make_graph(graph_id="different-graph")
        )

        with pytest.raises(BizoraError) as exc_info:
            await MethodologyExtractionService.extract_draft(
                provider,
                make_request(),
            )

        assert exc_info.value.code == ErrorCode.INVALID_GRAPH

    asyncio.run(run_test())


def test_extract_draft_rejects_invalid_edge_endpoint() -> None:
    async def run_test() -> None:
        invalid_edge = GraphEdge(
            id="edge-invalid",
            source="input",
            target="missing-node",
            relation=RelationKind.DATA_FLOW,
        )
        provider = FakeMethodologyProvider(
            make_graph(edges=(invalid_edge,))
        )

        with pytest.raises(BizoraError) as exc_info:
            await MethodologyExtractionService.extract_draft(
                provider,
                make_request(),
            )

        assert exc_info.value.code == ErrorCode.INVALID_GRAPH
        assert "failed validation" in str(exc_info.value).lower()

    asyncio.run(run_test())