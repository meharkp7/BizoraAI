
"""Tests for the provider-neutral extraction interface."""

import asyncio

import pytest
from pydantic import ValidationError

from bizora.contracts.graph import MethodologyGraph
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyExtractionResult,
    MethodologyProvider,
)


def make_request() -> MethodologyExtractionRequest:
    return MethodologyExtractionRequest(
        paper_text="We normalize the input and train a classifier.",
        project_id="project-1",
        graph_id="graph-1",
        source_id="paper-1",
        created_by="test-user",
        title="Example methodology",
    )


def make_graph() -> MethodologyGraph:
    return MethodologyGraph(
        schema_version="1.0",
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Example methodology",
        source_ids=["paper-1"],
        nodes=[],
        edges=[],
        created_by="test-user",
    )


class FakeMethodologyProvider:
    async def extract_methodology(
        self,
        request: MethodologyExtractionRequest,
    ) -> MethodologyExtractionResult:
        return MethodologyExtractionResult(
            draft_graph=make_graph(),
            provider_name="fake",
            model_name="fake-model",
        )


def test_request_accepts_valid_input() -> None:
    request = make_request()

    assert request.project_id == "project-1"
    assert request.source_id == "paper-1"


def test_request_rejects_empty_paper_text() -> None:
    with pytest.raises(ValidationError):
        MethodologyExtractionRequest(
            paper_text="",
            project_id="project-1",
            graph_id="graph-1",
            source_id="paper-1",
            created_by="test-user",
        )


def test_request_rejects_overlong_identifiers_and_title() -> None:
    base = {
        "paper_text": "We normalize the input and train a classifier.",
        "project_id": "project-1",
        "graph_id": "graph-1",
        "source_id": "paper-1",
        "created_by": "test-user",
    }
    for field, value in [
        ("project_id", "p" * 129),
        ("graph_id", "g" * 129),
        ("created_by", "u" * 129),
        ("title", "T" * 301),
    ]:
        with pytest.raises(ValidationError):
            MethodologyExtractionRequest(**{**base, field: value})


def test_request_accepts_boundary_identifier_lengths() -> None:
    request = MethodologyExtractionRequest(
        paper_text="We normalize the input and train a classifier.",
        project_id="p" * 128,
        graph_id="g" * 128,
        source_id="paper-1",
        created_by="u" * 128,
        title="T" * 300,
    )

    assert request.title is not None and len(request.title) == 300


def test_request_rejects_enormous_paper_text() -> None:
    from bizora.providers.base import MAX_PAPER_TEXT_LENGTH

    with pytest.raises(ValidationError):
        MethodologyExtractionRequest(
            paper_text="x" * (MAX_PAPER_TEXT_LENGTH + 1),
            project_id="project-1",
            graph_id="graph-1",
            source_id="paper-1",
            created_by="test-user",
        )


def test_result_contains_typed_draft_graph() -> None:
    result = MethodologyExtractionResult(
        draft_graph=make_graph(),
        provider_name="fake",
        model_name="fake-model",
        warnings=("Some evidence needs review.",),
    )

    assert isinstance(result.draft_graph, MethodologyGraph)
    assert result.provider_name == "fake"
    assert len(result.warnings) == 1


def test_provider_implementation_conforms_to_protocol() -> None:
    provider = FakeMethodologyProvider()

    assert isinstance(provider, MethodologyProvider)

    result = asyncio.run(provider.extract_methodology(make_request()))

    assert result.provider_name == "fake"
    assert result.draft_graph.graph_id == "graph-1"