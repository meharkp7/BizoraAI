"""Tests for the Muse Image provider (all API traffic is faked)."""

import asyncio
import base64
import json

import httpx
import pytest

from bizora.providers.muse_image import (
    DEFAULT_IMAGE_MODEL,
    MAX_PROMPT_LENGTH,
    GeneratedImage,
    ImageProviderError,
    MuseImageProvider,
)

FAKE_API_KEY = "test-muse-key"
FAKE_WEBP = b"RIFF\x00\x00\x00\x00WEBP"


def make_provider(handler: object) -> MuseImageProvider:
    assert callable(handler)
    return MuseImageProvider(
        api_key=FAKE_API_KEY,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),  # type: ignore[arg-type]
    )


def make_envelope(
    result: object = base64.b64encode(FAKE_WEBP).decode("ascii"),
) -> dict[str, object]:
    return {
        "id": "resp-1",
        "model": DEFAULT_IMAGE_MODEL,
        "status": "completed",
        "output": [
            {"type": "reasoning", "id": "rs-1"},
            {"type": "message", "id": "msg-1", "content": []},
            {
                "type": "image_generation_call",
                "id": "ig-1",
                "status": "completed",
                "result": result,
            },
        ],
        "usage": {"input_tokens": 9996, "output_tokens": 908},
    }


def test_missing_key_and_bad_config_fail_fast() -> None:
    with pytest.raises(ValueError, match="MUSE_API_KEY"):
        MuseImageProvider(api_key="")
    with pytest.raises(ValueError, match="model name"):
        MuseImageProvider(api_key=FAKE_API_KEY, model_name="  ")
    with pytest.raises(ValueError, match="Timeout"):
        MuseImageProvider(api_key=FAKE_API_KEY, timeout=0)


def test_generate_posts_prompt_and_decodes_the_image() -> None:
    seen: dict[str, object] = {}

    def fake_handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json=make_envelope())

    async def run_test() -> None:
        result = await make_provider(fake_handler).generate("a watercolor fox")

        assert seen["url"] == "https://api.meta.ai/v1/responses"
        assert seen["auth"] == f"Bearer {FAKE_API_KEY}"
        payload = seen["payload"]
        assert isinstance(payload, dict)
        assert payload["model"] == DEFAULT_IMAGE_MODEL
        assert payload["input"] == "a watercolor fox"
        assert payload["store"] is True
        assert "previous_response_id" not in payload
        assert isinstance(result, GeneratedImage)
        assert result.data == FAKE_WEBP
        assert result.response_id == "resp-1"
        assert result.usage is not None
        assert result.usage.input_tokens == 9996
        assert result.usage.output_tokens == 908

    asyncio.run(run_test())


def test_generate_chains_refinements_from_the_prior_turn() -> None:
    seen: dict[str, object] = {}

    def fake_handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json=make_envelope())

    async def run_test() -> None:
        await make_provider(fake_handler).generate("add a red hat", previous_response_id="resp-0")

        payload = seen["payload"]
        assert isinstance(payload, dict)
        assert payload["previous_response_id"] == "resp-0"
        assert payload["input"] == "add a red hat"

    asyncio.run(run_test())


def test_generate_rejects_bad_prompts_before_posting() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should be posted")

    async def run_test() -> None:
        provider = make_provider(boom)
        with pytest.raises(ImageProviderError, match="must not be empty"):
            await provider.generate("   ")
        with pytest.raises(ImageProviderError, match="limit is"):
            await provider.generate("x" * (MAX_PROMPT_LENGTH + 1))

    asyncio.run(run_test())


def test_generate_maps_incomplete_and_imageless_responses() -> None:
    def failed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "resp-2", "status": "failed", "output": []})

    def no_image(request: httpx.Request) -> httpx.Response:
        envelope = make_envelope()
        envelope["output"] = [{"type": "message", "id": "msg-1", "content": []}]
        return httpx.Response(200, json=envelope)

    def bad_image(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=make_envelope(result="!!! not base64 !!!"))

    async def run_test() -> None:
        with pytest.raises(ImageProviderError, match="did not complete"):
            await make_provider(failed).generate("a fox")
        with pytest.raises(ImageProviderError, match="no image"):
            await make_provider(no_image).generate("a fox")
        with pytest.raises(ImageProviderError, match="unreadable image"):
            await make_provider(bad_image).generate("a fox")

    asyncio.run(run_test())


def test_generate_maps_http_and_connection_failures() -> None:
    def denied(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad key")

    def outage(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    async def run_test() -> None:
        with pytest.raises(ImageProviderError, match="HTTP 401"):
            await make_provider(denied).generate("a fox")
        with pytest.raises(ImageProviderError, match="Could not connect"):
            await make_provider(outage).generate("a fox")

    asyncio.run(run_test())
