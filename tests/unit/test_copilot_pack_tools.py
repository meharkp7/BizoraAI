"""Tests for pack-provided copilot tools wired into the LLM loop."""

import asyncio
import json
from typing import Any

from bizora.copilot.service import answer_with_llm
from bizora.copilot.testing import make_eval_context, make_eval_graph
from bizora.copilot.tools import CopilotContext, execute_tool
from bizora.core.copilot_service import answer_copilot_async
from bizora.packs import electronics, iot
from bizora.providers.copilot import (
    CopilotAssistantTurn,
    CopilotMessage,
    CopilotToolSpec,
)


class _CapturingProvider:
    """Fake provider: records offered tools, then answers without grounding."""

    provider_name = "test-capture"

    def __init__(self) -> None:
        self.offered: list[str] = []

    async def chat(
        self,
        messages: list[CopilotMessage],
        tools: list[CopilotToolSpec],
        *,
        response_schema: dict[str, Any] | None = None,
    ) -> CopilotAssistantTurn:
        if response_schema is None:
            self.offered = [spec.name for spec in tools]
            return CopilotAssistantTurn(content="no tools needed")
        return CopilotAssistantTurn(
            content=json.dumps({"reply": "assumed draft", "assumed": True})
        )


def _eval_context_with_pack() -> CopilotContext:
    """Build the fixture context routed to the electronics pack."""
    context = make_eval_context()
    context.pack = electronics.pack
    return context


def test_pack_tool_specs_convert_to_provider_shape() -> None:
    """Pack specs convert 1:1 to provider tools the model may call."""
    from bizora.copilot.pack_tools import pack_tool_specs

    specs = pack_tool_specs(electronics.pack)

    assert {spec.name for spec in specs} == {
        "electronics_search_library",
        "electronics_preflight",
    }
    for spec in specs:
        assert spec.description
        assert spec.parameters.get("type") == "object"


def test_pack_search_library_scopes_to_pack_catalog() -> None:
    """Pack search only returns entries from its own pack library."""
    result = execute_tool(
        _eval_context_with_pack(),
        "electronics_search_library",
        {"query": "NPN transistor", "limit": 3},
    )

    assert "error" not in result
    assert result["matches"][0]["component_id"] == "npn-2n3904"
    owned = {entry.component_id for entry in electronics.pack.catalog_entries}
    assert {match["component_id"] for match in result["matches"]} <= owned


def test_pack_search_library_rejects_empty_query() -> None:
    result = execute_tool(
        _eval_context_with_pack(), "electronics_search_library", {"query": "  "}
    )

    assert "error" in result


def test_pack_preflight_reports_pack_rule_verdict() -> None:
    """Pack preflight validates without writing, like the core tool."""
    context = _eval_context_with_pack()
    before = context.graph.model_dump_json()

    result = execute_tool(
        context,
        "electronics_preflight",
        {"node_id": "sensor", "component_id": "npn-2n3904"},
    )

    assert result["compatible"] is False
    assert result["findings"]
    assert context.graph.model_dump_json() == before


def test_pack_preflight_rejects_foreign_component() -> None:
    """A pack never validates components outside its own library."""
    foreign = iot.pack.catalog_entries[0].component_id

    result = execute_tool(
        _eval_context_with_pack(),
        "electronics_preflight",
        {"node_id": "sensor", "component_id": foreign},
    )

    assert "error" in result


def test_pack_preflight_reports_unknown_node_and_component() -> None:
    context = _eval_context_with_pack()

    assert (
        "error"
        in execute_tool(
            context,
            "electronics_preflight",
            {"node_id": "nope", "component_id": "npn-2n3904"},
        )
    )
    assert (
        "error"
        in execute_tool(
            context,
            "electronics_preflight",
            {"node_id": "sensor", "component_id": "part-nope"},
        )
    )


def test_pack_tool_without_pack_reports_unknown_tool() -> None:
    """Pack tools stay unreachable when no pack is routed."""
    result = execute_tool(
        make_eval_context(), "electronics_search_library", {"query": "transistor"}
    )

    assert "error" in result


def test_answer_with_llm_offers_pack_tools() -> None:
    """The LLM loop sees core tools plus the routed pack's tools."""
    provider = _CapturingProvider()

    asyncio.run(answer_with_llm("why?", _eval_context_with_pack(), provider))

    assert "search_library" in provider.offered
    assert "electronics_search_library" in provider.offered
    assert "electronics_preflight" in provider.offered


def test_answer_copilot_async_routes_pack_for_graph() -> None:
    """Auto mode routes a pack-routed graph's tools without a caller context."""
    provider = _CapturingProvider()
    graph = make_eval_graph(version=1).model_copy(
        update={"title": "NBTI aging in 6T SRAM with leakage compensation"}
    )

    asyncio.run(answer_copilot_async(graph, "why did it fail?", mode="llm", provider=provider))

    assert "electronics_search_library" in provider.offered


def test_answer_copilot_async_skips_pack_tools_for_generic_graph() -> None:
    """Generic graphs keep core tools only; nothing pack-shaped is offered."""
    provider = _CapturingProvider()

    asyncio.run(
        answer_copilot_async(
            make_eval_graph(version=1), "why did it fail?", mode="llm", provider=provider
        )
    )

    assert "search_library" in provider.offered
    assert not [name for name in provider.offered if "electronics" in name]
