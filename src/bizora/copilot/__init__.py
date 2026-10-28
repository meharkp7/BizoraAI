"""Grounded LLM copilot: tools, citations, and orchestration."""

from bizora.copilot.citations import (
    Citation,
    CitationFinding,
    CitationReport,
    ComponentCitation,
    CopilotAnswer,
    EvidenceCitation,
    RunCitation,
    collect_observed_grounding,
    validate_citations,
)
from bizora.copilot.pack_tools import execute_pack_tool, pack_tool_specs
from bizora.copilot.prompts import FINAL_ANSWER_INSTRUCTION, SYSTEM_PROMPT
from bizora.copilot.service import (
    CopilotRunReport,
    answer_with_llm,
    build_grounded_response,
)
from bizora.copilot.tools import (
    TOOL_HANDLERS,
    TOOL_SPECS,
    CopilotContext,
    execute_tool,
)

__all__ = [
    "Citation",
    "CitationFinding",
    "CitationReport",
    "ComponentCitation",
    "CopilotAnswer",
    "EvidenceCitation",
    "RunCitation",
    "collect_observed_grounding",
    "validate_citations",
    "FINAL_ANSWER_INSTRUCTION",
    "SYSTEM_PROMPT",
    "CopilotRunReport",
    "answer_with_llm",
    "build_grounded_response",
    "TOOL_HANDLERS",
    "TOOL_SPECS",
    "CopilotContext",
    "execute_tool",
    "execute_pack_tool",
    "pack_tool_specs",
]
