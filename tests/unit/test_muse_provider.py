"""Tests for the Muse methodology provider (all API traffic is faked)."""

import asyncio
import json

import httpx
import pytest

from bizora.contracts.figures import (
    FigureAttachment,
    FigureDescription,
    FigureDescriptionRequest,
    FigureKind,
    FigureRegionProposal,
    NodeHint,
    RegionLocalizationRequest,
)
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyProvider,
)
from bizora.providers.muse import (
    FIGURE_OUTPUT_SCHEMA,
    MUSE_API_KEY_ENV_VAR,
    REGION_OUTPUT_SCHEMA,
    MuseMethodologyProvider,
    MuseProviderError,
)

FAKE_API_KEY = "test-muse-key"
FAKE_MODEL = "muse-spark-1.3"


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


def make_fake_responses_envelope(text: str) -> dict[str, object]:
    """Build a FAKE Responses API payload carrying the given output text."""
    return {
        "id": "resp_fake_1",
        "status": "completed",
        "model": FAKE_MODEL,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 120, "output_tokens": 45},
    }


def make_fake_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


def test_extract_methodology_returns_typed_draft() -> None:
    async def run_test() -> None:
        observed_request: dict[str, object] = {}

        def fake_handler(request: httpx.Request) -> httpx.Response:
            observed_request.update(json.loads(request.content))
            assert request.url.path == "/v1/responses"
            assert request.headers["Authorization"] == f"Bearer {FAKE_API_KEY}"
            return httpx.Response(
                200, json=make_fake_responses_envelope(json.dumps(make_graph_payload()))
            )

        async with make_fake_client(httpx.MockTransport(fake_handler)) as client:
            provider = MuseMethodologyProvider(
                api_key=FAKE_API_KEY,
                model_name=FAKE_MODEL,
                client=client,
            )
            result = await provider.extract_methodology(make_request())

        assert result.provider_name == "muse"
        assert result.model_name == FAKE_MODEL
        assert result.draft_graph.project_id == "project-1"
        assert result.draft_graph.graph_id == "graph-1"
        assert result.draft_graph.version == 1
        assert result.draft_graph.parent_version is None
        assert result.draft_graph.created_by == "test-user"
        assert result.draft_graph.title == "Image classification"
        assert result.draft_graph.source_ids == ("paper-2", "paper-1")
        assert observed_request["model"] == FAKE_MODEL
        assert observed_request["store"] is False
        text_format = observed_request["text"]["format"]
        assert text_format["type"] == "json_schema"
        assert text_format["name"] == "MethodologyGraph"
        assert "MethodologyGraph" in json.dumps(text_format["schema"])
        assert provider.last_usage is not None
        assert provider.last_usage.input_tokens == 120
        assert provider.last_usage.output_tokens == 45
        assert provider.last_usage.response_id == "resp_fake_1"

    asyncio.run(run_test())


def test_extract_methodology_with_pdf_sends_input_file() -> None:
    async def run_test() -> None:
        observed_request: dict[str, object] = {}

        def fake_handler(request: httpx.Request) -> httpx.Response:
            observed_request.update(json.loads(request.content))
            return httpx.Response(
                200, json=make_fake_responses_envelope(json.dumps(make_graph_payload()))
            )

        async with make_fake_client(httpx.MockTransport(fake_handler)) as client:
            provider = MuseMethodologyProvider(
                api_key=FAKE_API_KEY, model_name=FAKE_MODEL, client=client
            )
            result = await provider.extract_methodology_with_pdf(
                make_request(), b"%PDF-1.4 fake-bytes", filename="paper.pdf"
            )

        assert result.draft_graph.graph_id == "graph-1"
        content = observed_request["input"][0]["content"]
        block_types = [block["type"] for block in content]
        assert block_types == ["input_text", "input_file"]
        file_block = content[1]
        assert file_block["filename"] == "paper.pdf"
        assert file_block["file_data"].startswith("data:application/pdf;base64,")

    asyncio.run(run_test())


def make_figure_request() -> FigureDescriptionRequest:
    return FigureDescriptionRequest(
        project_id="project-1",
        graph_id="graph-1",
        source_id="paper-1",
        created_by="test-user",
        figures=(
            FigureAttachment(
                figure_id="fig-1",
                page=2,
                image_bytes=b"\x89PNG-fake-bytes",
                mime_type="image/png",
                surrounding_text="Figure 1 shows the device.",
                label_hint="Figure 1",
            ),
        ),
    )


def test_describe_figures_returns_merged_set() -> None:
    async def run_test() -> None:
        observed_request: dict[str, object] = {}
        fake_descriptions = {
            "figures": [
                {
                    "figure_id": "fig-1",
                    "label": "Figure 1",
                    "caption": "The device under test.",
                    "kind": "photo",
                    "confidence": 0.9,
                }
            ]
        }

        def fake_handler(request: httpx.Request) -> httpx.Response:
            observed_request.update(json.loads(request.content))
            return httpx.Response(
                200, json=make_fake_responses_envelope(json.dumps(fake_descriptions))
            )

        async with make_fake_client(httpx.MockTransport(fake_handler)) as client:
            provider = MuseMethodologyProvider(
                api_key=FAKE_API_KEY, model_name=FAKE_MODEL, client=client
            )
            result = await provider.describe_figures(make_figure_request())

        assert result.provider_name == "muse"
        assert len(result.draft_figures.figures) == 1
        figure = result.draft_figures.figures[0]
        assert figure.figure_id == "fig-1"
        assert figure.page == 2
        assert figure.label == "Figure 1"
        assert figure.kind.value == "photo"
        assert figure.byte_size == len(b"\x89PNG-fake-bytes")
        assert figure.sha256 is not None and len(figure.sha256) == 64
        assert figure.context == "Figure 1 shows the device."
        assert result.warnings == ()
        assert result.usage is not None
        assert result.usage.input_tokens == 120
        content = observed_request["input"][0]["content"]
        assert [block["type"] for block in content] == ["input_text", "input_image"]
        assert content[1]["image_url"].startswith("data:image/png;base64,")

    asyncio.run(run_test())


def make_region_request() -> RegionLocalizationRequest:
    return RegionLocalizationRequest(
        project_id="project-1",
        graph_id="graph-1",
        source_id="paper-1",
        created_by="test-user",
        figures=(
            FigureAttachment(
                figure_id="fig-1",
                page=2,
                image_bytes=b"\x89PNG-fake-bytes",
                mime_type="image/png",
                surrounding_text="Figure 1 shows the cell.",
                label_hint="Figure 1",
            ),
        ),
        nodes=(
            NodeHint(node_id="bitcell", label="6T SRAM bitcell", kind="component"),
            NodeHint(node_id="sense", label="Sense amplifier", kind="component"),
        ),
    )


def test_localize_regions_returns_merged_set() -> None:
    async def run_test() -> None:
        observed_request: dict[str, object] = {}
        fake_regions = {
            "regions": [
                {
                    "figure_id": "fig-1",
                    "bbox": [0.1, 0.2, 0.3, 0.25],
                    "node_id": "bitcell",
                    "label": "bitcell array",
                    "confidence": 0.8,
                },
                {
                    "figure_id": "fig-1",
                    "bbox": [0.5, 0.5, 0.2, 0.2],
                    "node_id": "ghost-node",
                    "label": "mystery block",
                    "confidence": None,
                },
            ]
        }

        def fake_handler(request: httpx.Request) -> httpx.Response:
            observed_request.update(json.loads(request.content))
            return httpx.Response(
                200, json=make_fake_responses_envelope(json.dumps(fake_regions))
            )

        async with make_fake_client(httpx.MockTransport(fake_handler)) as client:
            provider = MuseMethodologyProvider(
                api_key=FAKE_API_KEY, model_name=FAKE_MODEL, client=client
            )
            result = await provider.localize_regions(make_region_request())

        assert result.provider_name == "muse"
        first, second = result.draft_regions.regions
        assert first.region_id == "fig-1-r1"
        assert first.node_id == "bitcell"
        assert first.bbox == (0.1, 0.2, 0.3, 0.25)
        assert second.region_id == "fig-1-r2"
        assert second.node_id is None
        assert len(result.warnings) == 1
        text_format = observed_request["text"]["format"]
        assert text_format["name"] == "FigureRegions"
        content = observed_request["input"][0]["content"]
        assert [block["type"] for block in content] == [
            "input_text",
            "input_text",
            "input_image",
        ]
        assert "bitcell" in content[0]["text"]

    asyncio.run(run_test())


def test_flat_vision_schemas_match_contracts() -> None:
    """The minimal vision schemas must stay in sync with the contracts."""
    figure_item = FIGURE_OUTPUT_SCHEMA["properties"]["figures"]["items"]
    assert set(figure_item["properties"]) == set(FigureDescription.model_fields)
    assert set(figure_item["required"]) == set(FigureDescription.model_fields)
    assert set(figure_item["properties"]["kind"]["enum"]) == {kind.value for kind in FigureKind}
    assert "$defs" not in FIGURE_OUTPUT_SCHEMA

    region_item = REGION_OUTPUT_SCHEMA["properties"]["regions"]["items"]
    assert set(region_item["properties"]) == set(FigureRegionProposal.model_fields)
    assert set(region_item["required"]) == set(FigureRegionProposal.model_fields)
    assert "$defs" not in REGION_OUTPUT_SCHEMA


def test_localize_regions_rejects_invalid_response() -> None:
    async def run_test() -> None:
        def fake_handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=make_fake_responses_envelope("not JSON"))

        async with make_fake_client(httpx.MockTransport(fake_handler)) as client:
            provider = MuseMethodologyProvider(
                api_key=FAKE_API_KEY, model_name=FAKE_MODEL, client=client
            )
            with pytest.raises(MuseProviderError, match="invalid figure region response"):
                await provider.localize_regions(make_region_request())

    asyncio.run(run_test())


def test_extract_methodology_rejects_http_error() -> None:
    async def run_test() -> None:
        def fake_handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "unauthorized"})

        async with make_fake_client(httpx.MockTransport(fake_handler)) as client:
            provider = MuseMethodologyProvider(
                api_key=FAKE_API_KEY, model_name=FAKE_MODEL, client=client
            )
            with pytest.raises(MuseProviderError, match="HTTP 401"):
                await provider.extract_methodology(make_request())

    asyncio.run(run_test())


def test_extract_methodology_rejects_invalid_json_content() -> None:
    async def run_test() -> None:
        def fake_handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=make_fake_responses_envelope("not JSON"))

        async with make_fake_client(httpx.MockTransport(fake_handler)) as client:
            provider = MuseMethodologyProvider(
                api_key=FAKE_API_KEY, model_name=FAKE_MODEL, client=client
            )
            with pytest.raises(MuseProviderError, match="invalid methodology graph response"):
                await provider.extract_methodology(make_request())

    asyncio.run(run_test())


def test_extract_methodology_rejects_incomplete_status() -> None:
    async def run_test() -> None:
        def fake_handler(_: httpx.Request) -> httpx.Response:
            envelope = make_fake_responses_envelope("{}")
            envelope["status"] = "incomplete"
            return httpx.Response(200, json=envelope)

        async with make_fake_client(httpx.MockTransport(fake_handler)) as client:
            provider = MuseMethodologyProvider(
                api_key=FAKE_API_KEY, model_name=FAKE_MODEL, client=client
            )
            with pytest.raises(MuseProviderError, match="did not complete"):
                await provider.extract_methodology(make_request())

    asyncio.run(run_test())


def test_structured_output_failure_retries_without_schema() -> None:
    async def run_test() -> None:
        calls: list[dict[str, object]] = []

        def fake_handler(request: httpx.Request) -> httpx.Response:
            calls.append(json.loads(request.content))
            if len(calls) == 1:
                return httpx.Response(400, json={"error": "unsupported text.format schema"})
            return httpx.Response(
                200, json=make_fake_responses_envelope(json.dumps(make_graph_payload()))
            )

        async with make_fake_client(httpx.MockTransport(fake_handler)) as client:
            provider = MuseMethodologyProvider(
                api_key=FAKE_API_KEY, model_name=FAKE_MODEL, client=client
            )
            result = await provider.extract_methodology(make_request())

        assert result.draft_graph.graph_id == "graph-1"
        assert len(calls) == 2
        assert "text" in calls[0]
        assert "text" not in calls[1]

    asyncio.run(run_test())


def test_non_schema_http_error_does_not_retry() -> None:
    async def run_test() -> None:
        calls = 0

        def fake_handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(429, json={"error": "rate limited"})

        async with make_fake_client(httpx.MockTransport(fake_handler)) as client:
            provider = MuseMethodologyProvider(
                api_key=FAKE_API_KEY, model_name=FAKE_MODEL, client=client
            )
            with pytest.raises(MuseProviderError, match="HTTP 429"):
                await provider.extract_methodology(make_request())

        assert calls == 1

    asyncio.run(run_test())


def test_pdf_size_limit_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    import bizora.providers.muse as muse_module

    monkeypatch.setattr(muse_module, "INLINE_FILE_LIMIT_BYTES", 4)
    provider = MuseMethodologyProvider(api_key=FAKE_API_KEY, model_name=FAKE_MODEL)
    with pytest.raises(MuseProviderError, match="inline file limit"):
        asyncio.run(provider.extract_methodology_with_pdf(make_request(), b"12345"))


def test_provider_reads_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MUSE_API_KEY_ENV_VAR, "env-key")
    provider = MuseMethodologyProvider(model_name=FAKE_MODEL)
    assert isinstance(provider, MethodologyProvider)


def test_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(MUSE_API_KEY_ENV_VAR, raising=False)
    with pytest.raises(ValueError, match="API key"):
        MuseMethodologyProvider(model_name=FAKE_MODEL)
    with pytest.raises(ValueError, match="API key"):
        MuseMethodologyProvider(api_key=" ", model_name=FAKE_MODEL)


def test_provider_conforms_to_protocol() -> None:
    provider = MuseMethodologyProvider(api_key=FAKE_API_KEY, model_name=FAKE_MODEL)
    assert isinstance(provider, MethodologyProvider)
