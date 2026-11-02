"""Tests for streaming copilot turns and their parity with ask_once."""

import asyncio
import json
from typing import Any

from bizora.copilot.service import (
    CopilotDoneEvent,
    CopilotRunReport,
    CopilotStatusEvent,
    answer_with_llm,
    answer_with_llm_stream,
)
from bizora.copilot.testing import EVAL_SOURCE_ID, make_eval_context
from bizora.core.copilot_service import answer_copilot_stream
from bizora.providers.copilot import (
    CopilotAssistantTurn,
    CopilotToolCall,
)
from bizora.providers.fixture_copilot import (
    FailingCopilotProvider,
    RecordedTranscript,
    ScriptedCopilotProvider,
)


def _final_answer_json() -> str:
    return json.dumps(
        {
            "reply": "The filter corner is 4 kHz per the paper.",
            "citations": [
                {"kind": "evidence", "source_id": EVAL_SOURCE_ID, "page": 3}
            ],
            "proposal": None,
            "assumed": False,
        }
    )


def _evidence_script() -> RecordedTranscript:
    return RecordedTranscript(
        turns=(
            CopilotAssistantTurn(
                content="Let me read the evidence.",
                tool_calls=(
                    CopilotToolCall(
                        id="call-1",
                        name="read_evidence",
                        arguments={"target_id": "filter"},
                    ),
                ),
            ),
            CopilotAssistantTurn(content="I have what I need."),
            CopilotAssistantTurn(content=_final_answer_json()),
        )
    )


async def _collect(message: str, provider: Any) -> tuple[
    list[CopilotStatusEvent | CopilotDoneEvent], CopilotRunReport
]:
    events: list[CopilotStatusEvent | CopilotDoneEvent] = []
    report = CopilotRunReport(provider_name="scripted")
    async for event in answer_with_llm_stream(
        message, make_eval_context(), provider, report=report
    ):
        events.append(event)
    return events, report


def test_stream_interleaves_statuses_before_done() -> None:
    async def run_test() -> None:
        events, report = await _collect(
            "What did the paper say about the filter?",
            ScriptedCopilotProvider(_evidence_script()),
        )
        statuses = [e.message for e in events if isinstance(e, CopilotStatusEvent)]
        dones = [e for e in events if isinstance(e, CopilotDoneEvent)]

        assert statuses == [
            "Thinking (round 1)…",
            "Consulting read_evidence…",
            "Thinking (round 2)…",
            "Writing the final answer…",
        ]
        assert len(dones) == 1
        assert events[-1] is dones[0]
        assert "4 kHz" in dones[0].response.reply
        assert report.tool_calls == 1
        assert report.valid_citations == 1

    asyncio.run(run_test())


def test_stream_matches_non_stream_reply() -> None:
    async def run_test() -> None:
        message = "What did the paper say about the filter?"
        streamed, _ = await _collect(
            message, ScriptedCopilotProvider(_evidence_script())
        )
        once = await answer_with_llm(
            message,
            make_eval_context(),
            ScriptedCopilotProvider(_evidence_script()),
        )
        done = streamed[-1]
        assert isinstance(done, CopilotDoneEvent)
        assert done.response.reply == once.reply
        assert done.response.cards == once.cards

    asyncio.run(run_test())


def test_stream_routing_fast_path_without_provider() -> None:
    async def run_test() -> None:
        context = make_eval_context()
        events: list[CopilotStatusEvent | CopilotDoneEvent] = []
        async for event in answer_copilot_stream(
            context.graph, "hello", "filter", provider=None, context=context
        ):
            events.append(event)
        assert [type(e) for e in events] == [CopilotStatusEvent, CopilotDoneEvent]
        assert isinstance(events[0], CopilotStatusEvent)
        assert events[0].message == "Answering from the workspace graph…"
        assert isinstance(events[1], CopilotDoneEvent)
        assert events[1].response.reply

    asyncio.run(run_test())


def test_stream_routing_falls_back_on_provider_failure() -> None:
    async def run_test() -> None:
        context = make_eval_context()
        report = CopilotRunReport(provider_name="failing")
        events: list[CopilotStatusEvent | CopilotDoneEvent] = []
        async for event in answer_copilot_stream(
            context.graph,
            "Why did run-eval-2 fail?",
            "filter",
            provider=FailingCopilotProvider(),
            context=context,
            mode="llm",
            report=report,
        ):
            events.append(event)
        assert report.fallback is True
        assert isinstance(events[-1], CopilotDoneEvent)
        assert events[-1].response.reply
        apology = events[-2]
        assert isinstance(apology, CopilotStatusEvent)
        assert "stumbled" in apology.message

    asyncio.run(run_test())


def test_stream_provider_failure_raises_for_caller_fallback() -> None:
    async def run_test() -> None:
        events: list[CopilotStatusEvent | CopilotDoneEvent] = []
        try:
            async for event in answer_with_llm_stream(
                "hi", make_eval_context(), FailingCopilotProvider()
            ):
                events.append(event)
        except Exception as exc:  # noqa: BLE001 - asserting the raise site
            assert "Scripted provider failure" in str(exc)
        else:  # pragma: no cover - the fixture always fails
            raise AssertionError("expected the provider error to propagate")
        assert all(isinstance(e, CopilotStatusEvent) for e in events)

    asyncio.run(run_test())
