"""Tests for talk-to-diagrams: roster lookups and diagram citations."""

import asyncio
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.unit.test_run_api import (  # noqa: F401
    client_with_db,
    make_graph_payload,
)

__all__ = ["client_with_db"]

from bizora import api
from bizora.contracts.components import CopilotDiagramElement
from bizora.copilot.citations import (
    CopilotAnswer,
    DiagramCitation,
    validate_citations,
)
from bizora.copilot.service import answer_with_llm, build_grounded_response
from bizora.copilot.testing import make_eval_context
from bizora.core.copilot_service import answer_copilot, wants_llm_answer
from bizora.providers.copilot import (
    CopilotAssistantTurn,
    CopilotMessage,
    CopilotToolSpec,
)


def _roster() -> tuple[CopilotDiagramElement, ...]:
    return (
        CopilotDiagramElement(
            view="schematic",
            element_id="N1",
            label="Inverter stage",
            kind="inverter",
            detail="CMOS inverter pair.",
        ),
        CopilotDiagramElement(
            view="schematic", element_id="N2", label="Output driver", kind="buffer"
        ),
    )


def test_show_command_resolves_element_id() -> None:
    """'show N1' answers with a jump-to-viewer card."""
    response = answer_copilot(
        make_eval_context().graph, "show N1", diagram_elements=_roster()
    )

    assert "N1" in response.reply and "Inverter stage" in response.reply
    assert len(response.cards) == 1
    card = response.cards[0]
    assert card.kind == "diagram"
    assert card.diagram_ref is not None
    assert card.diagram_ref.element_id == "N1"
    assert card.diagram_ref.view == "schematic"
    assert card.diagram_ref.label == "Inverter stage"


def test_lookup_matches_unique_labels_and_explains_ambiguity() -> None:
    """Unique label hits resolve; ambiguous ones list candidates."""
    graph = make_eval_context().graph
    unique = answer_copilot(graph, "where is inverter?", diagram_elements=_roster())
    assert unique.cards and unique.cards[0].diagram_ref is not None
    assert unique.cards[0].diagram_ref.element_id == "N1"

    roster = _roster() + (
        CopilotDiagramElement(
            view="schematic", element_id="N3", label="Inverter bias", kind="bias"
        ),
    )
    ambiguous = answer_copilot(graph, "find inverter", diagram_elements=roster)
    assert ambiguous.cards == ()
    assert "N1" in ambiguous.reply and "N3" in ambiguous.reply


def test_lookup_falls_through_to_library_without_a_match() -> None:
    """Unmatched refs keep the old library behavior, roster or not."""
    graph = make_eval_context().graph
    with_roster = answer_copilot(
        graph, "find NPN transistor", diagram_elements=_roster()
    )
    assert "Closest library matches" in with_roster.reply

    without_roster = answer_copilot(graph, "show N1")
    assert with_roster.cards != ()
    assert all(card.kind != "diagram" for card in without_roster.cards)


def test_show_commands_stay_on_the_fast_path() -> None:
    """Locate commands never spend an LLM turn."""
    assert wants_llm_answer("show N1?") is False
    assert wants_llm_answer("where is the inverter?") is False
    assert wants_llm_answer("what does the paper say here?") is True


def test_diagram_citations_validate_against_the_roster() -> None:
    """Roster members validate; invented ids are dropped with a note."""
    context = replace(make_eval_context(), diagram_elements=_roster())
    answer = CopilotAnswer(
        reply="N1 inverts the signal.",
        citations=(
            DiagramCitation(view="schematic", element_id="N1"),
            DiagramCitation(view="schematic", element_id="NX"),
        ),
        assumed=False,
    )

    report = validate_citations(answer, [], context)
    assert len(report.valid) == 1
    assert report.valid[0].kind == "diagram"
    assert len(report.invalid) == 1
    assert "NX" in report.invalid[0].reason

    grounded = build_grounded_response(answer, context, dropped_citations=1)
    assert "1 citation(s) could not be verified" in grounded.reply


def test_diagram_card_carries_roster_label_and_detail() -> None:
    """Grounded diagram cards keep the ref the viewer needs."""
    context = replace(make_eval_context(), diagram_elements=_roster())
    grounded = build_grounded_response(
        CopilotAnswer(
            reply="See N1.",
            citations=(DiagramCitation(view="schematic", element_id="N1"),),
            assumed=False,
        ),
        context,
    )

    assert len(grounded.cards) == 1
    card = grounded.cards[0]
    assert card.kind == "diagram"
    assert card.diagram_ref is not None
    assert card.diagram_ref.label == "Inverter stage"
    assert "CMOS inverter pair." in card.body


def test_orchestrator_sends_roster_to_provider() -> None:
    """The visible element ids reach the provider as a context line."""

    class RecordingProvider:
        provider_name = "recording"

        def __init__(self) -> None:
            self.seen: list[list[CopilotMessage]] = []

        async def chat(
            self,
            messages: list[CopilotMessage],
            tools: list[CopilotToolSpec],  # noqa: ARG002 - recorded, not read
            *,
            response_schema: dict[str, Any] | None = None,
        ) -> CopilotAssistantTurn:
            self.seen.append(list(messages))
            if response_schema is not None:
                return CopilotAssistantTurn(
                    content=(
                        '{"reply": "N1 inverts.", "citations": [{"kind": "diagram", '
                        '"view": "schematic", "element_id": "N1"}], '
                        '"proposal": null, "assumed": false}'
                    )
                )
            return CopilotAssistantTurn(content="No tools needed.")

    async def run_test() -> None:
        provider = RecordingProvider()
        context = replace(make_eval_context(), diagram_elements=_roster())

        response = await answer_with_llm("What does N1 do?", context, provider)

        first_user = next(m for m in provider.seen[0] if m.role == "user")
        assert "Visible diagram elements — schematic: N1 (Inverter stage)" in (
            first_user.content
        )
        assert response.cards and response.cards[0].kind == "diagram"

    asyncio.run(run_test())


def test_ask_answers_locate_commands_from_the_roster(
    client_with_db: tuple[TestClient, Callable[[], Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The roster rides the request and grounds show commands."""
    client, _ = client_with_db
    created = client.post("/api/v1/graphs", json=make_graph_payload())
    assert created.status_code == 201
    monkeypatch.setattr(api, "_copilot_provider_or_none", lambda: None)

    response = client.post(
        "/api/v1/graphs/project-api/graph-api/revisions/1/copilot",
        json={
            "message": "show N1",
            "diagram_context": "viewing schematic tab",
            "diagram_elements": [
                {
                    "view": "schematic",
                    "element_id": "N1",
                    "label": "Inverter stage",
                    "kind": "inverter",
                    "detail": None,
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cards"][0]["kind"] == "diagram"
    assert body["cards"][0]["diagram_ref"]["element_id"] == "N1"


def test_ask_rejects_oversized_rosters(
    client_with_db: tuple[TestClient, Callable[[], Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rosters cap at 40 elements per request."""
    client, _ = client_with_db
    created = client.post("/api/v1/graphs", json=make_graph_payload())
    assert created.status_code == 201
    monkeypatch.setattr(api, "_copilot_provider_or_none", lambda: None)

    response = client.post(
        "/api/v1/graphs/project-api/graph-api/revisions/1/copilot",
        json={
            "message": "show N1",
            "diagram_elements": [
                {"view": "schematic", "element_id": f"N{i}", "label": f"Stage {i}"}
                for i in range(41)
            ],
        },
    )

    assert response.status_code == 422


def test_final_answer_parse_accepts_flat_diagram_citations() -> None:
    """Flat diagram citations coerce through the final-answer parse."""
    from bizora.copilot.service import _parse_final_answer

    answer = _parse_final_answer(
        '{"reply": "See it.", "citations": [{"kind": "diagram", "view": null, '
        '"element_id": "N1", "source_id": null, "page": null, "quote": null, '
        '"figure_label": null, "run_id": null, "metric_name": null, '
        '"component_id": null}], "proposal": null, "assumed": false}'
    )

    assert answer.citations[0].kind == "diagram"
