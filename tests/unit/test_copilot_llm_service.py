"""Tests for the LLM orchestration loop, router, and fallback."""

import asyncio
import json

from bizora.copilot.service import (
    CopilotRunReport,
    answer_with_llm,
    build_grounded_response,
)
from bizora.copilot.testing import EVAL_SOURCE_ID, make_eval_context
from bizora.core.copilot_service import (
    answer_copilot_async,
    wants_llm_answer,
)
from bizora.providers.copilot import (
    CopilotAssistantTurn,
    CopilotProviderError,
    CopilotToolCall,
    CopilotUsage,
)
from bizora.providers.fixture_copilot import (
    FailingCopilotProvider,
    RecordedTranscript,
    ScriptedCopilotProvider,
)


def _final_answer_json(**overrides: object) -> str:
    payload: dict[str, object] = {
        "reply": "The filter corner is 4 kHz per the paper.",
        "citations": [{"kind": "evidence", "source_id": EVAL_SOURCE_ID, "page": 3}],
        "proposal": None,
        "assumed": False,
    }
    payload.update(overrides)
    return json.dumps(payload)


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


def test_orchestrator_grounds_answer_in_tool_results() -> None:
    async def run_test() -> None:
        context = make_eval_context()
        report = CopilotRunReport(provider_name="scripted")

        response = await answer_with_llm(
            "What did the paper say about the filter?",
            context,
            ScriptedCopilotProvider(_evidence_script()),
            report=report,
        )

        assert "4 kHz" in response.reply
        assert report.tool_calls == 1
        assert report.valid_citations == 1
        assert report.invalid_citations == 0
        assert response.proposal is None
        assert any(card.kind == "evidence" for card in response.cards)

    asyncio.run(run_test())


def test_orchestrator_drops_fabricated_citations() -> None:
    async def run_test() -> None:
        final = _final_answer_json(
            citations=[{"kind": "evidence", "source_id": EVAL_SOURCE_ID, "page": 99}]
        )
        transcript = RecordedTranscript(
            turns=(
                CopilotAssistantTurn(
                    content="Reading.",
                    tool_calls=(
                        CopilotToolCall(
                            id="call-1",
                            name="read_evidence",
                            arguments={"target_id": "filter"},
                        ),
                    ),
                ),
                CopilotAssistantTurn(content="Done reading."),
                CopilotAssistantTurn(content=final),
            )
        )

        response = await answer_with_llm(
            "What did the paper say?", make_eval_context(), ScriptedCopilotProvider(transcript)
        )

        assert "could not be verified" in response.reply
        assert "Unverified draft" in response.reply
        assert all(card.kind != "evidence" for card in response.cards)

    asyncio.run(run_test())


def test_orchestrator_returns_proposal_pending_approval() -> None:
    async def run_test() -> None:
        context = make_eval_context()
        before = context.graph.model_dump_json()
        proposal = {
            "node_id": "filter",
            "component_id": None,
            "kind": "operation",
            "label": "Filter stage",
            "description": "The filtering block.",
            "config": {"corner_hz": 8000},
            "rationale": "Widen the corner for the experiment.",
        }
        final = _final_answer_json(
            reply="I propose widening the corner.",
            citations=[],
            proposal=proposal,
            assumed=True,
        )
        transcript = RecordedTranscript(
            turns=(
                CopilotAssistantTurn(
                    content="Proposing.",
                    tool_calls=(
                        CopilotToolCall(
                            id="call-1",
                            name="propose_patch",
                            arguments={
                                "node_id": "filter",
                                "config": {"corner_hz": 8000},
                                "rationale": "Widen the corner for the experiment.",
                            },
                        ),
                    ),
                ),
                CopilotAssistantTurn(content="Proposal ready."),
                CopilotAssistantTurn(content=final),
            )
        )

        response = await answer_with_llm(
            "Should I widen the corner?",
            context,
            ScriptedCopilotProvider(transcript),
        )

        assert response.proposal is not None
        assert response.proposal.config["corner_hz"] == 8000
        assert any(card.kind == "proposal" for card in response.cards)
        assert "nothing was changed" in response.cards[-1].body.lower()
        assert context.graph.model_dump_json() == before

    asyncio.run(run_test())


def test_orchestrator_tracks_token_usage() -> None:
    async def run_test() -> None:
        transcript = RecordedTranscript(
            turns=(
                CopilotAssistantTurn(
                    content="",
                    usage=CopilotUsage(input_tokens=100, output_tokens=20),
                ),
                CopilotAssistantTurn(
                    content=_final_answer_json(),
                    usage=CopilotUsage(input_tokens=200, output_tokens=40),
                ),
            )
        )
        report = CopilotRunReport(provider_name="scripted")

        await answer_with_llm(
            "What did the paper say?",
            make_eval_context(),
            ScriptedCopilotProvider(transcript),
            report=report,
        )

        assert report.total_input_tokens == 300
        assert report.total_output_tokens == 60

    asyncio.run(run_test())


def test_orchestrator_rejects_invalid_final_answer() -> None:
    async def run_test() -> None:
        transcript = RecordedTranscript(
            turns=(CopilotAssistantTurn(content="not json"), CopilotAssistantTurn(content="[]"))
        )

        try:
            await answer_with_llm(
                "Hello?", make_eval_context(), ScriptedCopilotProvider(transcript)
            )
        except CopilotProviderError:
            return
        raise AssertionError("expected CopilotProviderError")

    asyncio.run(run_test())


def test_build_grounded_response_labels_uncited_answers() -> None:
    from bizora.copilot.citations import CopilotAnswer

    response = build_grounded_response(
        CopilotAnswer(reply="A guess.", citations=(), assumed=False),
        make_eval_context(),
    )

    assert response.reply.startswith("Unverified draft")


def test_router_sends_questions_to_llm_and_commands_to_fast_path() -> None:
    assert wants_llm_answer("Why did this run diverge?") is True
    assert wants_llm_answer("What did the paper say about the resistor value?") is True
    assert wants_llm_answer("find NPN transistor") is False
    assert wants_llm_answer("set corner_hz to 8000 on filter") is False
    assert wants_llm_answer("replace sensor with 2N3904") is False


def test_async_entry_falls_back_when_provider_fails() -> None:
    async def run_test() -> None:
        context = make_eval_context()
        report = CopilotRunReport(provider_name="failing")

        response = await answer_copilot_async(
            context.graph,
            "Why did run-eval-2 fail?",
            "filter",
            provider=FailingCopilotProvider(),
            context=context,
            mode="llm",
            report=report,
        )

        assert report.fallback is True
        assert response.reply  # deterministic engine still answers

    asyncio.run(run_test())


def test_async_entry_uses_fast_path_without_provider() -> None:
    async def run_test() -> None:
        context = make_eval_context()

        response = await answer_copilot_async(
            context.graph, "help", "filter", provider=None, mode="auto"
        )

        assert "component library" in response.reply

    asyncio.run(run_test())


def test_async_entry_rejects_bad_mode() -> None:
    async def run_test() -> None:
        context = make_eval_context()
        try:
            await answer_copilot_async(context.graph, "hi", provider=None, mode="ludicrous")
        except ValueError:
            return
        raise AssertionError("expected ValueError")

    asyncio.run(run_test())
