"""LLM copilot orchestration: tools, citations, and the approval gate.

The orchestrator runs a bounded tool loop against any
:class:`CopilotProvider`, executes every tool locally through
:class:`CopilotContext`, then requests one schema-constrained final
answer. Citations are validated before the response is built:
invalid citations are dropped with an explicit note, and answers
with no verified grounding are labelled assumed. Proposals are
returned for human approval and never applied here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from bizora.contracts.components import (
    CopilotCard,
    CopilotProposal,
    CopilotResponse,
)
from bizora.copilot.citations import (
    ComponentCitation,
    CopilotAnswer,
    EvidenceCitation,
    RunCitation,
    validate_citations,
)
from bizora.copilot.pack_tools import pack_tool_specs
from bizora.copilot.prompts import FINAL_ANSWER_INSTRUCTION, SYSTEM_PROMPT
from bizora.copilot.tools import TOOL_SPECS, CopilotContext, execute_tool
from bizora.providers.copilot import (
    MAX_TOOL_ROUNDS,
    CopilotAssistantTurn,
    CopilotMessage,
    CopilotProvider,
    CopilotProviderError,
    CopilotUsage,
)

# Minimal flat schema for the final answer. The generated Pydantic
# schema ($defs/$ref, unions) degrades constrained output on this
# model into gibberish; this plain shape elicits clean JSON while
# local validation stays the strict gate.
COPILOT_ANSWER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["evidence", "run", "component"]},
                    "source_id": {"type": ["string", "null"]},
                    "page": {"type": ["number", "null"]},
                    "quote": {"type": ["string", "null"]},
                    "figure_label": {"type": ["string", "null"]},
                    "run_id": {"type": ["string", "null"]},
                    "metric_name": {"type": ["string", "null"]},
                    "component_id": {"type": ["string", "null"]},
                },
                "required": [
                    "kind",
                    "source_id",
                    "page",
                    "quote",
                    "figure_label",
                    "run_id",
                    "metric_name",
                    "component_id",
                ],
                "additionalProperties": False,
            },
        },
        "proposal": {
            "type": ["object", "null"],
            "properties": {
                "node_id": {"type": "string"},
                "component_id": {"type": ["string", "null"]},
                "kind": {"type": "string"},
                "label": {"type": "string"},
                "description": {"type": ["string", "null"]},
                "config": {"type": "object"},
                "rationale": {"type": "string"},
            },
            "required": [
                "node_id",
                "component_id",
                "kind",
                "label",
                "description",
                "config",
                "rationale",
            ],
            "additionalProperties": False,
        },
        "assumed": {"type": "boolean"},
    },
    "required": ["reply", "citations", "proposal", "assumed"],
    "additionalProperties": False,
}

_CITATION_KEYS: dict[str, tuple[str, ...]] = {
    "evidence": ("source_id", "page", "quote", "figure_label"),
    "run": ("run_id", "metric_name"),
    "component": ("component_id",),
}


def _coerce_flat_citation(raw: Any) -> Any:
    """Narrow one flat citation dict to its kind's relevant keys.

    The flat output schema carries every citation field on every
    citation; the typed contracts forbid unknown keys, so coercion
    keeps the kind plus its own non-null fields before validation.
    Already-typed citations pass through untouched.
    """
    if not isinstance(raw, dict):
        return raw
    kind = raw.get("kind")
    if kind not in _CITATION_KEYS:
        return raw
    coerced: dict[str, Any] = {"kind": kind}
    for key in _CITATION_KEYS[kind]:
        value = raw.get(key)
        if value is not None:
            coerced[key] = value
    return coerced


@dataclass
class CopilotRunReport:
    """Diagnostics for one orchestrated answer (spend + grounding)."""

    provider_name: str
    tool_rounds: int = 0
    tool_calls: int = 0
    usage: list[CopilotUsage] = field(default_factory=list)
    valid_citations: int = 0
    invalid_citations: int = 0
    fallback: bool = False
    turns: list[CopilotAssistantTurn] = field(default_factory=list)

    @property
    def total_input_tokens(self) -> int:
        """Sum known input tokens across calls."""
        return sum(u.input_tokens or 0 for u in self.usage)

    @property
    def total_output_tokens(self) -> int:
        """Sum known output tokens across calls."""
        return sum(u.output_tokens or 0 for u in self.usage)


def _tool_result_text(result: dict[str, Any]) -> str:
    text = json.dumps(result, default=str)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        return text[:MAX_TOOL_RESULT_CHARS] + '… (truncated)"'
    return text


MAX_TOOL_RESULT_CHARS = 6000


def _evidence_card(citation: EvidenceCitation) -> CopilotCard:
    locator = f"Source: {citation.source_id}"
    if citation.page is not None:
        locator += f" · Page {citation.page}"
    if citation.figure_label is not None:
        locator += f" · {citation.figure_label}"
    lines = [locator]
    if citation.target_id:
        lines.append(f"Attached to: {citation.target_id}")
    if citation.quote:
        lines.append(f'"{citation.quote}"')
    return CopilotCard(
        kind="evidence",
        title="Paper evidence",
        body="\n".join(lines),
        component_ids=(),
        node_id=citation.target_id,
    )


def _run_card(citation: RunCitation, context: CopilotContext) -> CopilotCard:
    lines = [f"Run: {citation.run_id}"]
    run = context.run(citation.run_id)
    if run is not None:
        lines.append(f"State: {run.state.value}")
        if run.error:
            lines.append(f"Error: {run.error}")
    if citation.metric_name is not None:
        value = next(
            (m.value for m in context.metrics(citation.run_id) if m.name == citation.metric_name),
            None,
        )
        if value is None:
            lines.append(f"Metric: {citation.metric_name} (no recorded value)")
        else:
            lines.append(f"Metric: {citation.metric_name} = {value}")
    return CopilotCard(
        kind="info",
        title="Measured run",
        body="\n".join(lines),
        component_ids=(),
    )


def _component_card(citation: ComponentCitation) -> CopilotCard:
    return CopilotCard(
        kind="component",
        title="Library entry",
        body=f"Catalog entry {citation.component_id} (open in the library for specs).",
        component_ids=(citation.component_id,),
    )


def build_grounded_response(
    answer: CopilotAnswer,
    context: CopilotContext,
    *,
    dropped_citations: int = 0,
) -> CopilotResponse:
    """Build the API response from a validated answer."""
    cards: list[CopilotCard] = []
    for citation in answer.citations:
        if isinstance(citation, EvidenceCitation):
            cards.append(_evidence_card(citation))
        elif isinstance(citation, RunCitation):
            cards.append(_run_card(citation, context))
        elif isinstance(citation, ComponentCitation):
            cards.append(_component_card(citation))
    proposal: CopilotProposal | None = answer.proposal
    reply = answer.reply
    if proposal is not None:
        cards.append(
            CopilotCard(
                kind="proposal",
                title=f"Proposed change on {proposal.label}",
                body=(f"{proposal.rationale}\nAwaiting your approval — nothing was changed yet."),
                component_ids=(proposal.component_id,) if proposal.component_id else (),
                node_id=proposal.node_id,
            )
        )
    if dropped_citations:
        reply += (
            f"\n\nNote: {dropped_citations} citation(s) could not be verified "
            "against the observed evidence and runs, so they were removed."
        )
    if not answer.citations and not answer.assumed:
        reply = "Unverified draft (no confirmed citations — treat as assumed): " + reply
    return CopilotResponse(reply=reply[:6000], cards=tuple(cards), proposal=proposal)


def _proposal_matches_tool(proposal: CopilotProposal, tool_results: list[dict[str, Any]]) -> bool:
    """Return whether a proposal equals one built by propose_patch."""
    for result in tool_results:
        if not isinstance(result, dict) or "proposal" not in result:
            continue
        built = result["proposal"]
        if not isinstance(built, dict):
            continue
        if (
            built.get("node_id") == proposal.node_id
            and built.get("component_id") == proposal.component_id
            and built.get("config") == proposal.config
        ):
            return True
    return False


def _parse_final_answer(content: str) -> CopilotAnswer:
    try:
        data = json.loads(content)
    except ValueError:
        stripped = content.strip()
        if not stripped.startswith("```"):
            raise
        lines = stripped.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        data = json.loads("\n".join(lines))
    if isinstance(data, dict) and isinstance(data.get("citations"), list):
        data = {
            **data,
            "citations": [_coerce_flat_citation(raw) for raw in data["citations"]],
        }
    return CopilotAnswer.model_validate(data)


async def answer_with_llm(
    message: str,
    context: CopilotContext,
    provider: CopilotProvider,
    *,
    max_rounds: int = MAX_TOOL_ROUNDS,
    report: CopilotRunReport | None = None,
) -> CopilotResponse:
    """Answer one message through the provider's tool loop.

    Raises :class:`CopilotProviderError` when the provider cannot
    produce a usable answer; callers fall back to the deterministic
    engine in that case.
    """
    run_report = report if report is not None else CopilotRunReport(provider_name="unknown")
    run_report.provider_name = provider.provider_name
    if max_rounds < 1:
        raise CopilotProviderError("max_rounds must be at least 1.")

    question = message.strip()[:8000] or "(empty question)"
    history: list[CopilotMessage] = [
        CopilotMessage(role="system", content=SYSTEM_PROMPT),
        CopilotMessage(role="user", content=question),
    ]
    tool_results: list[dict[str, Any]] = []
    specs = list(TOOL_SPECS)
    if context.pack is not None:
        specs.extend(pack_tool_specs(context.pack))

    for _ in range(max_rounds):
        turn: CopilotAssistantTurn = await provider.chat(history, specs)
        run_report.turns.append(
            CopilotAssistantTurn(content=turn.content, tool_calls=turn.tool_calls)
        )
        if turn.usage is not None:
            run_report.usage.append(turn.usage)
        if not turn.tool_calls:
            history.append(CopilotMessage(role="assistant", content=turn.content or "(no content)"))
            break
        run_report.tool_rounds += 1
        history.append(
            CopilotMessage(
                role="assistant",
                content=turn.content or "(calling tools)",
                tool_calls=turn.tool_calls,
            )
        )
        for call in turn.tool_calls:
            run_report.tool_calls += 1
            result = execute_tool(context, call.name, call.arguments)
            tool_results.append(result)
            history.append(
                CopilotMessage(
                    role="tool",
                    content=_tool_result_text(result),
                    tool_call_id=call.id,
                )
            )
    else:
        history.append(CopilotMessage(role="assistant", content="(tool budget spent)"))

    history.append(CopilotMessage(role="user", content=FINAL_ANSWER_INSTRUCTION))
    final: CopilotAssistantTurn = await provider.chat(
        history, [], response_schema=COPILOT_ANSWER_OUTPUT_SCHEMA
    )
    run_report.turns.append(CopilotAssistantTurn(content=final.content))
    if final.usage is not None:
        run_report.usage.append(final.usage)
    try:
        answer = _parse_final_answer(final.content)
    except (ValueError, ValidationError) as exc:
        raise CopilotProviderError(f"The model returned an invalid final answer ({exc}).") from exc

    citation_report = validate_citations(answer, tool_results, context)
    run_report.valid_citations = len(citation_report.valid)
    run_report.invalid_citations = len(citation_report.invalid)
    proposal = answer.proposal
    proposal_note = ""
    if proposal is not None and not _proposal_matches_tool(proposal, tool_results):
        proposal = None
        proposal_note = (
            "\n\nNote: the suggested change did not match a verified tool "
            "proposal, so it was removed. Nothing was changed."
        )
    grounded = CopilotAnswer(
        reply=answer.reply + proposal_note,
        citations=citation_report.valid,
        proposal=proposal,
        assumed=answer.assumed,
    )
    return build_grounded_response(
        grounded, context, dropped_citations=len(citation_report.invalid)
    )
