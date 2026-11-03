"""Muse Image generation through the Meta Model Responses API.

The provider posts to ``POST {base_url}/responses`` with the
``muse-image-1.0`` model and a text prompt. The model reasons before it
renders, so the response ``output`` list interleaves reasoning, message,
and ``image_generation_call`` items: the image is the base64 ``result``
on the ``image_generation_call`` (WebP bytes). Refining chains turns
with ``previous_response_id`` so only the change is sent.

Credential: ``MUSE_API_KEY``, shared with the other Muse clients.
"""

from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass
from typing import Any

import httpx

from bizora.contracts.figures import ResponseUsage
from bizora.providers.muse import DEFAULT_BASE_URL, MUSE_API_KEY_ENV_VAR

DEFAULT_IMAGE_MODEL = "muse-image-1.0"

#: Prompts past this are rejected client-side, not billed.
MAX_PROMPT_LENGTH = 4000


class ImageProviderError(RuntimeError):
    """Raised when the image provider cannot return an image."""


@dataclass(frozen=True)
class GeneratedImage:
    """One rendered image plus its turn identity."""

    data: bytes
    response_id: str | None = None
    usage: ResponseUsage | None = None


def _usage_of(data: dict[str, Any]) -> ResponseUsage | None:
    """Read token usage fields from a Responses API payload, if present."""
    usage = data.get("usage")
    values = usage if isinstance(usage, dict) else {}
    input_tokens = values.get("input_tokens")
    output_tokens = values.get("output_tokens")
    response_id = data.get("id")
    model = data.get("model")
    return ResponseUsage(
        input_tokens=input_tokens if isinstance(input_tokens, int) else None,
        output_tokens=output_tokens if isinstance(output_tokens, int) else None,
        response_id=response_id if isinstance(response_id, str) else None,
        model=model if isinstance(model, str) else None,
    )


class MuseImageProvider:
    """Generate images using Muse Image."""

    provider_name = "muse-image"

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = DEFAULT_IMAGE_MODEL,
        *,
        base_url: str | None = None,
        timeout: float = 180.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        resolved_key = api_key if api_key is not None else os.getenv(MUSE_API_KEY_ENV_VAR)
        if resolved_key is None or not resolved_key.strip():
            raise ValueError(
                "A Muse API key is required: pass api_key or set "
                f"{MUSE_API_KEY_ENV_VAR} in the environment."
            )
        if not model_name.strip():
            raise ValueError("Muse image model name must not be empty.")
        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")

        self._api_key = resolved_key
        self._model_name = model_name
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout
        self._client = client

    async def generate(
        self, prompt: str, *, previous_response_id: str | None = None
    ) -> GeneratedImage:
        """Render one image from a text prompt.

        Pass a prior turn's response id to refine its render with only
        the change described: the server carries the image forward.
        """
        if not prompt.strip():
            raise ImageProviderError("The image prompt must not be empty.")
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ImageProviderError(
                f"The image prompt is {len(prompt)} characters; the limit is {MAX_PROMPT_LENGTH}."
            )

        payload: dict[str, Any] = {
            "model": self._model_name,
            # The server keeps turn state so refinements chain from it.
            "store": True,
            "input": prompt,
        }
        if previous_response_id is not None:
            payload["previous_response_id"] = previous_response_id
        data = await self._create_response(payload)

        status = data.get("status")
        if status is not None and status != "completed":
            detail = data.get("error", status)
            raise ImageProviderError(f"Muse did not complete the render ({detail}).")

        output = data.get("output")
        items = output if isinstance(output, list) else []
        encoded: str | None = None
        for item in items:
            if not isinstance(item, dict) or item.get("type") != "image_generation_call":
                continue
            if item.get("status") is not None and item.get("status") != "completed":
                detail = item.get("error", item.get("status"))
                raise ImageProviderError(f"Muse did not complete the render ({detail}).")
            result = item.get("result")
            if isinstance(result, str) and result:
                encoded = result
                break
        if encoded is None:
            raise ImageProviderError("Muse returned no image.")
        try:
            image = base64.b64decode(encoded)
        except (binascii.Error, ValueError) as exc:
            raise ImageProviderError("Muse returned an unreadable image.") from exc
        response_id = data.get("id")
        return GeneratedImage(
            data=image,
            response_id=response_id if isinstance(response_id, str) else None,
            usage=_usage_of(data),
        )

    async def _create_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST one Responses request and return the decoded payload."""
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
            raise ImageProviderError(
                f"Muse returned HTTP {exc.response.status_code} ({body})."
            ) from exc
        except httpx.RequestError as exc:
            raise ImageProviderError("Could not connect to the Muse API.") from exc
        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise ImageProviderError("Muse returned an unreadable response.") from exc
        return data
