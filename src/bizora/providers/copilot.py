"""Provider-neutral contracts for the LLM copilot.

The copilot converses through any chat-capable model behind this
interface. Tools are declared as JSON schemas and executed locally by
the copilot service; the model only ever requests tool calls and
produces a final structured answer. Nothing here names a domain,
paper, or part: tools operate on graph ids, evidence locators, run
ids, and catalog ids supplied at call time.
"""

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

MAX_COPILOT_MESSAGE_LENGTH = 8000
MAX_TOOL_ROUNDS = 6


class CopilotProviderError(RuntimeError):
    """Raised when a copilot provider cannot return a usable turn."""


class CopilotUsage(BaseModel):
    """Token usage for one copilot provider call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int | None = None
    output_tokens: int | None = None
    response_id: str | None = None
    model: str | None = None

    @property
    def total_tokens(self) -> int | None:
        """Return total tokens when both halves are known."""
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens


class CopilotToolSpec(BaseModel):
    """One function tool the model may call, in JSON-schema form."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1, max_length=2000)
    parameters: dict[str, Any] = Field(default_factory=dict)


class CopilotToolCall(BaseModel):
    """One model-requested tool invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class CopilotMessage(BaseModel):
    """One turn of copilot conversation history."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1, max_length=MAX_COPILOT_MESSAGE_LENGTH)
    tool_call_id: str | None = Field(default=None, max_length=128)
    tool_calls: tuple[CopilotToolCall, ...] = ()


class CopilotAssistantTurn(BaseModel):
    """One assistant turn: prose plus zero or more tool requests."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = Field(default="", max_length=MAX_COPILOT_MESSAGE_LENGTH)
    tool_calls: tuple[CopilotToolCall, ...] = ()
    usage: CopilotUsage | None = None


@runtime_checkable
class CopilotProvider(Protocol):
    """Interface implemented by every copilot chat provider."""

    provider_name: str

    async def chat(
        self,
        messages: list[CopilotMessage],
        tools: list[CopilotToolSpec],
        *,
        response_schema: dict[str, Any] | None = None,
    ) -> CopilotAssistantTurn:
        """Return one assistant turn, optionally constrained to a schema.

        When ``response_schema`` is given, tools are ignored and the
        turn content must be a JSON object matching the schema.
        """
        ...
