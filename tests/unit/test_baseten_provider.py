"""Tests for the Baseten methodology provider (mocked transport)."""

import asyncio
import json

import httpx
import pytest

from bizora.providers.base import MethodologyExtractionRequest
from bizora.providers.baseten import (
    BasetenMethodologyProvider,
    BasetenProviderError,
)
from bizora.providers.tables import TableExtractionRequest


def make_request() -> MethodologyExtractionRequest:
    return MethodologyExtractionRequest(
        paper_text="The authors normalize images before training.",
        project_id="project-1",
        graph_id="graph-1",
        source_id="paper-1",
        created_by="test-user",
        title="Image classification",
    )


def make_graph_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "project_id": "untrusted-project",
        "graph_id": "untrusted-graph",
        "version": 99,
        "title": "Model-generated title",
        "source_ids": ["paper-2"],
        "nodes": [],
        "edges": [],
        "created_by": "untrusted-user",
        "parent_version": 98,
    }


def make_table_request() -> TableExtractionRequest:
    return TableExtractionRequest(
        paper_text="Table 1 shows TM-scores for CASP14 targets.",
        project_id="project-1",
        graph_id="graph-1",
        source_id="paper-1",
        created_by="test-user",
    )


def make_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


def test_uses_baseten_defaults() -> None:
    provider = BasetenMethodologyProvider(
        api_key="test-key",
        model_name="meta-models/muse-spark-open-1026",
    )

    assert provider.provider_name == "baseten"
    assert provider.DEFAULT_BASE_URL == "https://inference.baseten.co/v1"


def test_extract_methodology_returns_typed_draft() -> None:
    async def run_test() -> None:
        graph_payload = make_graph_payload()
        observed_request: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed_request.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(graph_payload),
                            }
                        }
                    ]
                },
            )

        async with make_client(httpx.MockTransport(handler)) as client:
            provider = BasetenMethodologyProvider(
                api_key="test-key",
                model_name="meta-models/muse-spark-open-1026",
                client=client,
            )
            result = await provider.extract_methodology(make_request())

        assert result.provider_name == "baseten"
        assert result.model_name == "meta-models/muse-spark-open-1026"
        assert result.draft_graph.project_id == "project-1"
        assert result.draft_graph.version == 1
        assert result.draft_graph.parent_version is None
        assert result.draft_graph.source_ids == ("paper-2", "paper-1")
        assert observed_request["model"] == "meta-models/muse-spark-open-1026"
        assert observed_request["response_format"] == {"type": "json_object"}

    asyncio.run(run_test())


def test_extract_methodology_rejects_http_error() -> None:
    async def run_test() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "unauthorized"})

        async with make_client(httpx.MockTransport(handler)) as client:
            provider = BasetenMethodologyProvider(
                api_key="test-key",
                model_name="test-model",
                client=client,
            )

            with pytest.raises(BasetenProviderError, match="HTTP 401"):
                await provider.extract_methodology(make_request())

    asyncio.run(run_test())


def test_extract_methodology_rejects_invalid_graph() -> None:
    async def run_test() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "not JSON"}}]},
            )

        async with make_client(httpx.MockTransport(handler)) as client:
            provider = BasetenMethodologyProvider(
                api_key="test-key",
                model_name="test-model",
                client=client,
            )

            with pytest.raises(
                BasetenProviderError,
                match="invalid methodology graph response",
            ):
                await provider.extract_methodology(make_request())

    asyncio.run(run_test())


def test_system_prompt_embeds_graph_schema() -> None:
    async def run_test() -> None:
        observed_request: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed_request.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(make_graph_payload()),
                            }
                        }
                    ]
                },
            )

        async with make_client(httpx.MockTransport(handler)) as client:
            provider = BasetenMethodologyProvider(
                api_key="test-key",
                model_name="test-model",
                client=client,
            )
            await provider.extract_methodology(make_request())

        messages = observed_request["messages"]
        assert isinstance(messages, list)
        system = messages[0]["content"]
        assert isinstance(system, str)
        assert "ResearchBrief" in system
        assert "component" in system
        assert "additionalProperties" in system

    asyncio.run(run_test())


def test_validation_failure_names_first_error() -> None:
    async def run_test() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            payload = dict(make_graph_payload())
            payload["nodes"] = [
                {"id": "bad node!", "kind": "model", "label": "Bad"}
            ]
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(payload)}}]},
            )

        async with make_client(httpx.MockTransport(handler)) as client:
            provider = BasetenMethodologyProvider(
                api_key="test-key",
                model_name="test-model",
                client=client,
            )

            with pytest.raises(
                BasetenProviderError,
                match=r"nodes\.0\.id",
            ):
                await provider.extract_methodology(make_request())

    asyncio.run(run_test())


def test_extract_methodology_tolerates_fenced_json() -> None:
    async def run_test() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            fenced = "```json\n" + json.dumps(make_graph_payload()) + "\n```"
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": fenced}}]},
            )

        async with make_client(httpx.MockTransport(handler)) as client:
            provider = BasetenMethodologyProvider(
                api_key="test-key",
                model_name="test-model",
                client=client,
            )
            result = await provider.extract_methodology(make_request())

        assert result.draft_graph.project_id == "project-1"
        assert result.provider_name == "baseten"

    asyncio.run(run_test())


def test_extract_tables_returns_typed_drafts() -> None:
    async def run_test() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "tables": [
                                            {
                                                "table_id": "table-1",
                                                "caption": "CASP14 results.",
                                                "columns": ["Method", "TM-score"],
                                                "rows": [["AlphaFold2", "0.92"]],
                                            },
                                            {
                                                "table_id": "table-2",
                                                "caption": "Ragged.",
                                                "columns": ["Method", "TM-score"],
                                                "rows": [["AlphaFold2"]],
                                            },
                                        ]
                                    }
                                ),
                            }
                        }
                    ]
                },
            )

        async with make_client(httpx.MockTransport(handler)) as client:
            provider = BasetenMethodologyProvider(
                api_key="test-key",
                model_name="test-model",
                client=client,
            )
            result = await provider.extract_tables(make_table_request())

        assert [table.table_id for table in result.draft_tables] == ["table-1"]
        assert result.draft_tables[0].source_id == "paper-1"
        assert result.provider_name == "baseten"
        assert len(result.warnings) == 1

    asyncio.run(run_test())


def test_extract_tables_tolerates_fenced_json() -> None:
    async def run_test() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            payload = {
                "tables": [
                    {
                        "table_id": "table-1",
                        "caption": "Results.",
                        "columns": ["A"],
                        "rows": [["1"]],
                    }
                ]
            }
            fenced = "```json\n" + json.dumps(payload) + "\n```"
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": fenced}}]},
            )

        async with make_client(httpx.MockTransport(handler)) as client:
            provider = BasetenMethodologyProvider(
                api_key="test-key",
                model_name="test-model",
                client=client,
            )
            result = await provider.extract_tables(make_table_request())

        assert [table.table_id for table in result.draft_tables] == ["table-1"]

    asyncio.run(run_test())


def test_extract_tables_rejects_invalid_envelope() -> None:
    async def run_test() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": []})

        async with make_client(httpx.MockTransport(handler)) as client:
            provider = BasetenMethodologyProvider(
                api_key="test-key",
                model_name="test-model",
                client=client,
            )

            with pytest.raises(
                BasetenProviderError,
                match="invalid tables response",
            ):
                await provider.extract_tables(make_table_request())

    asyncio.run(run_test())


def test_provider_requires_api_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        BasetenMethodologyProvider(
            api_key=" ",
            model_name="test-model",
        )


def test_provider_requires_model_name() -> None:
    with pytest.raises(ValueError, match="model name"):
        BasetenMethodologyProvider(
            api_key="test-key",
            model_name=" ",
        )


def test_provider_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="Timeout"):
        BasetenMethodologyProvider(
            api_key="test-key",
            model_name="test-model",
            timeout=0,
        )
