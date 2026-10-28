"""Tests for copilot chat providers (Muse tool calling + offline doubles)."""

import asyncio
import json

import httpx
import pytest

from bizora.providers.copilot import (
    CopilotAssistantTurn,
    CopilotMessage,
    CopilotProviderError,
    CopilotToolCall,
    CopilotToolSpec,
)
from bizora.providers.fixture_copilot import (
    FailingCopilotProvider,
    RecordedTranscript,
    ScriptedCopilotProvider,
)
from bizora.providers.muse_copilot import MuseCopilotProvider


def _tool() -> CopilotToolSpec:
    return CopilotToolSpec(
        name="query_runs",
        description="Query runs.",
        parameters={"type": "object", "properties": {}},
    )


def _responses_payload(
    output: list[dict[str, object]],
    *,
    usage: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": "resp-1",
        "model": "muse-spark-1.3",
        "status": "completed",
        "output": output,
        "usage": usage or {"input_tokens": 10, "output_tokens": 5},
    }


def _client_for(payload: dict[str, object], seen: list[dict[str, object]]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content.decode()))
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_muse_chat_parses_tool_calls_and_usage() -> None:
    async def run_test() -> None:
        seen: list[dict[str, object]] = []
        payload = _responses_payload(
            [
                {
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "query_runs",
                    "arguments": json.dumps({"run_id": "run-eval-1"}),
                }
            ]
        )
        provider = MuseCopilotProvider(api_key="test-key", client=_client_for(payload, seen))

        turn = await provider.chat(
            [CopilotMessage(role="user", content="Why did it fail?")], [_tool()]
        )

        assert turn.tool_calls == (
            CopilotToolCall(id="call-1", name="query_runs", arguments={"run_id": "run-eval-1"}),
        )
        assert turn.usage is not None
        assert turn.usage.input_tokens == 10
        assert provider.last_usage is not None
        assert seen[0]["tools"][0]["name"] == "query_runs"

    asyncio.run(run_test())


def test_muse_chat_sends_tool_results_as_function_outputs() -> None:
    async def run_test() -> None:
        seen: list[dict[str, object]] = []
        payload = _responses_payload(
            [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Done."}],
                }
            ]
        )
        provider = MuseCopilotProvider(api_key="test-key", client=_client_for(payload, seen))
        history = [
            CopilotMessage(role="system", content="Be brief."),
            CopilotMessage(role="user", content="Status?"),
            CopilotMessage(
                role="assistant",
                content="Checking.",
                tool_calls=(CopilotToolCall(id="call-1", name="query_runs", arguments={}),),
            ),
            CopilotMessage(role="tool", content='{"runs": []}', tool_call_id="call-1"),
        ]

        turn = await provider.chat(history, [_tool()])

        assert turn.content == "Done."
        assert seen[0]["instructions"] == "Be brief."
        input_items = seen[0]["input"]
        assert {"type": "function_call", "call_id": "call-1", "name": "query_runs"}.items() <= next(
            item for item in input_items if item.get("type") == "function_call"
        ).items()
        assert {
            "type": "function_call_output",
            "call_id": "call-1",
            "output": '{"runs": []}',
        } in input_items

    asyncio.run(run_test())


def test_muse_chat_structured_answer_omits_tools() -> None:
    async def run_test() -> None:
        seen: list[dict[str, object]] = []
        payload = _responses_payload(
            [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"reply": "ok"}'}],
                }
            ]
        )
        provider = MuseCopilotProvider(api_key="test-key", client=_client_for(payload, seen))

        turn = await provider.chat(
            [CopilotMessage(role="user", content="Final.")],
            [_tool()],
            response_schema={"type": "object"},
        )

        assert turn.content == '{"reply": "ok"}'
        assert "tools" not in seen[0]
        assert seen[0]["text"]["format"]["name"] == "CopilotAnswer"

    asyncio.run(run_test())


def test_muse_chat_rejects_missing_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        MuseCopilotProvider(api_key="  ")


def test_muse_chat_requires_history() -> None:
    async def run_test() -> None:
        provider = MuseCopilotProvider(api_key="test-key")
        with pytest.raises(CopilotProviderError, match="at least one message"):
            await provider.chat([], [])

    asyncio.run(run_test())


def test_muse_chat_surfaces_http_errors() -> None:
    async def run_test() -> None:
        def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
            return httpx.Response(500, text="boom")

        provider = MuseCopilotProvider(
            api_key="test-key",
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        with pytest.raises(CopilotProviderError, match="HTTP 500"):
            await provider.chat([CopilotMessage(role="user", content="hi")], [])

    asyncio.run(run_test())


def test_scripted_provider_replays_transcript() -> None:
    async def run_test() -> None:
        transcript = RecordedTranscript(
            turns=(
                CopilotAssistantTurn(content="first"),
                CopilotAssistantTurn(content="second"),
            )
        )
        provider = ScriptedCopilotProvider(transcript)

        first = await provider.chat([], [])
        second = await provider.chat([], [])

        assert (first.content, second.content) == ("first", "second")
        assert provider.exhausted is True
        with pytest.raises(CopilotProviderError, match="exhausted"):
            await provider.chat([], [])

    asyncio.run(run_test())


def test_failing_provider_always_raises() -> None:
    async def run_test() -> None:
        with pytest.raises(CopilotProviderError):
            await FailingCopilotProvider().chat([], [])

    asyncio.run(run_test())
