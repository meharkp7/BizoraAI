"""Muse Spark copilot chat through the Meta Model Responses API.

Tool rounds post ``tools`` (function tools) alongside the rebuilt
conversation; the final answer posts ``text.format`` with the caller
supplied JSON schema so the answer validates locally. Usage is read
from every payload for spend reporting.

Credential: pass ``api_key`` explicitly, or leave it unset to read the
``MUSE_API_KEY`` environment variable. This module only reads the
environment and never opens credential files itself.
"""

import json
import os
from typing import Any

import httpx

from bizora.providers.copilot import (
    CopilotAssistantTurn,
    CopilotMessage,
    CopilotProviderError,
    CopilotToolCall,
    CopilotToolSpec,
    CopilotUsage,
)
from bizora.providers.muse import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL_NAME,
    MAX_OUTPUT_TOKENS,
    MUSE_API_KEY_ENV_VAR,
)
from bizora.providers.muse import (
    _extract_usage as _extract_response_usage,
)

_FUNCTION_CALL_LIMIT = 16


def _message_to_input_items(message: CopilotMessage) -> list[dict[str, Any]]:
    """Map one history message to Responses API input items."""
    if message.role == "tool":
        if not message.tool_call_id:
            raise CopilotProviderError("Tool result is missing its tool_call_id.")
        return [
            {
                "type": "function_call_output",
                "call_id": message.tool_call_id,
                "output": message.content,
            }
        ]
    if message.role == "assistant" and message.tool_calls:
        items: list[dict[str, Any]] = []
        if message.content.strip():
            items.append(
                {
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": message.content}],
                }
            )
        for call in message.tool_calls:
            items.append(
                {
                    "type": "function_call",
                    "call_id": call.id,
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                }
            )
        return items
    return [
        {
            "role": message.role,
            "content": [{"type": "input_text", "text": message.content}],
        }
    ]


def _parse_tool_calls(data: dict[str, Any]) -> tuple[str, list[CopilotToolCall]]:
    """Split a Responses payload into prose and function calls."""
    shortcut = data.get("output_text")
    prose = shortcut if isinstance(shortcut, str) else ""
    calls: list[CopilotToolCall] = []
    output = data.get("output")
    if not isinstance(output, list):
        return prose, calls
    parts: list[str] = [prose] if prose.strip() else []
    for item in output:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "message":
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "output_text":
                    continue
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        elif item_type == "function_call":
            call_id = item.get("call_id")
            name = item.get("name")
            raw_arguments = item.get("arguments", "{}")
            if not isinstance(call_id, str) or not isinstance(name, str):
                continue
            try:
                arguments = json.loads(raw_arguments) if raw_arguments else {}
            except ValueError:
                continue
            if not isinstance(arguments, dict):
                continue
            calls.append(CopilotToolCall(id=call_id, name=name, arguments=arguments))
            if len(calls) >= _FUNCTION_CALL_LIMIT:
                break
    return "\n".join(parts), calls


def _coerce_usage(raw: Any) -> CopilotUsage | None:
    """Convert a Responses usage payload to copilot usage."""
    usage = _extract_response_usage(raw if isinstance(raw, dict) else {})
    if (
        usage.input_tokens is None
        and usage.output_tokens is None
        and usage.response_id is None
        and usage.model is None
    ):
        return None
    return CopilotUsage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        response_id=usage.response_id,
        model=usage.model,
    )


class MuseCopilotProvider:
    """Copilot chat with tool calling through the Responses API."""

    provider_name = "muse-copilot"

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = DEFAULT_MODEL_NAME,
        *,
        base_url: str | None = None,
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        resolved_key = api_key if api_key is not None else os.getenv(MUSE_API_KEY_ENV_VAR)
        if resolved_key is None or not resolved_key.strip():
            raise ValueError(
                "A Muse API key is required: pass api_key or set "
                f"{MUSE_API_KEY_ENV_VAR} in the environment."
            )
        if not model_name.strip():
            raise ValueError("Muse model name must not be empty.")
        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")
        self._api_key = resolved_key
        self._model_name = model_name
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout
        self._client = client
        self.last_usage: CopilotUsage | None = None

    async def chat(
        self,
        messages: list[CopilotMessage],
        tools: list[CopilotToolSpec],
        *,
        response_schema: dict[str, Any] | None = None,
    ) -> CopilotAssistantTurn:
        """Return one assistant turn from the Responses API."""
        if not messages:
            raise CopilotProviderError("Copilot chat needs at least one message.")
        system_parts = [m.content for m in messages if m.role == "system"]
        input_items: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "system":
                continue
            input_items.extend(_message_to_input_items(message))
        if not input_items:
            raise CopilotProviderError("Copilot chat needs a non-system message.")

        payload: dict[str, Any] = {
            "model": self._model_name,
            "store": False,
            "input": input_items,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        }
        if system_parts:
            payload["instructions"] = "\n\n".join(system_parts)
        if response_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "CopilotAnswer",
                    "schema": response_schema,
                    "strict": False,
                }
            }
        elif tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters or {"type": "object", "properties": {}},
                }
                for tool in tools
            ]

        data = await self._post(payload)
        prose, calls = _parse_tool_calls(data)
        usage = _coerce_usage(data)
        self.last_usage = usage
        if response_schema is not None and not prose.strip():
            raise CopilotProviderError("Muse returned an empty structured answer.")
        return CopilotAssistantTurn(content=prose, tool_calls=tuple(calls), usage=usage)

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST one payload and return the decoded response."""
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._base_url}/responses",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        f"{self._base_url}/responses",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json=payload,
                    )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300]
            raise CopilotProviderError(
                f"Muse returned HTTP {exc.response.status_code} ({body})."
            ) from exc
        except httpx.RequestError as exc:
            raise CopilotProviderError("Could not connect to the Muse API.") from exc
        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise CopilotProviderError("Muse returned an unreadable response.") from exc
        status = data.get("status")
        if status is not None and status != "completed":
            detail = data.get("error", status)
            raise CopilotProviderError(f"Muse did not complete the response ({detail}).")
        return data
