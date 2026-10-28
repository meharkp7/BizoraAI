"""Offline copilot providers: scripted turns and recorded fixtures.

The scripted provider replays one recorded transcript per
conversation, so the evaluation harness and unit tests exercise the
real orchestration loop (real tool execution, real citation
validation) with zero API spend. Recorded transcripts double as the
cache format for live answers: a live transcript saved once replays
offline forever.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bizora.providers.copilot import (
    CopilotAssistantTurn,
    CopilotMessage,
    CopilotProviderError,
    CopilotToolSpec,
)


class RecordedTranscript(BaseModel):
    """One cached conversation: scripted turns plus recorded usage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    turns: tuple[CopilotAssistantTurn, ...] = Field(min_length=1)
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None


class ScriptedCopilotProvider:
    """Replay a fixed transcript; never touches the network."""

    provider_name = "scripted"

    def __init__(self, transcript: RecordedTranscript) -> None:
        self._transcript = transcript
        self._index = 0
        self.chat_calls = 0

    @property
    def exhausted(self) -> bool:
        """Return whether every scripted turn has been consumed."""
        return self._index >= len(self._transcript.turns)

    async def chat(
        self,
        messages: list[CopilotMessage],  # noqa: ARG002 - history is scripted, not read
        tools: list[CopilotToolSpec],  # noqa: ARG002 - tools execute in the service
        *,
        response_schema: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> CopilotAssistantTurn:
        """Return the next scripted turn."""
        self.chat_calls += 1
        if self._index >= len(self._transcript.turns):
            raise CopilotProviderError("Scripted transcript is exhausted.")
        turn = self._transcript.turns[self._index]
        self._index += 1
        return turn


class FailingCopilotProvider:
    """Always fail, to prove the deterministic fallback path."""

    provider_name = "failing"

    async def chat(
        self,
        messages: list[CopilotMessage],  # noqa: ARG002
        tools: list[CopilotToolSpec],  # noqa: ARG002
        *,
        response_schema: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> CopilotAssistantTurn:
        """Raise on every call."""
        raise CopilotProviderError("Scripted provider failure.")
