
"""Fireworks AI implementation of the methodology provider interface."""

import json
from typing import Any

import httpx
from pydantic import ValidationError

from bizora.contracts.graph import MethodologyGraph
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyExtractionResult,
)


class FireworksProviderError(RuntimeError):
    """Raised when Fireworks cannot return a usable methodology draft."""


class FireworksMethodologyProvider:
    """Extract a draft methodology graph using Fireworks chat completions."""

    DEFAULT_BASE_URL = "https://api.fireworks.ai/inference/v1"

    def __init__(
        self,
        api_key: str,
        model_name: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Fireworks API key must not be empty.")
        if not model_name.strip():
            raise ValueError("Fireworks model name must not be empty.")
        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")

        self._api_key = api_key
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client

    async def extract_methodology(
        self,
        request: MethodologyExtractionRequest,
    ) -> MethodologyExtractionResult:
        """Request JSON output and parse it into a typed draft graph."""

        messages = [
            {
                "role": "system",
                "content": (
                    "You extract research methodology into a structured graph. "
                    "Return only a JSON object representing a MethodologyGraph. "
                    "Include schema_version, project_id, graph_id, version, "
                    "title, source_ids, nodes, edges, created_by, and "
                    "parent_version. Each node must use the supported node "
                    "contract; each edge must reference existing node IDs. "
                    "Represent only relationships supported by the supplied "
                    "paper. Do not invent experimental results, evidence "
                    "locators, or measurements. Use empty arrays when no "
                    "supported nodes or edges can be extracted. The calling "
                    "application will assign authoritative graph metadata."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Project ID: {request.project_id}\n"
                    f"Graph ID: {request.graph_id}\n"
                    f"Source ID: {request.source_id}\n"
                    f"Requested title: {request.title or 'Infer from paper'}\n\n"
                    "Extract the methodology from this paper text:\n"
                    f"{request.paper_text}"
                ),
            },
        ]

        payload = {
            "model": self._model_name,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 8192,
            "response_format": {"type": "json_object"},
        }

        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
            else:
                async with httpx.AsyncClient(
                    timeout=self._timeout
                ) as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self._api_key}"
                        },
                        json=payload,
                    )

            response.raise_for_status()

        except httpx.HTTPStatusError as exc:
            raise FireworksProviderError(
                f"Fireworks returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            raise FireworksProviderError(
                "Could not connect to the Fireworks API."
            ) from exc

        try:
            response_data: dict[str, Any] = response.json()
            content = response_data["choices"][0]["message"]["content"]

            if not isinstance(content, str) or not content.strip():
                raise FireworksProviderError(
                    "Fireworks returned an empty response."
                )

            graph_data = json.loads(content)

            if not isinstance(graph_data, dict):
                raise FireworksProviderError(
                    "Fireworks output must be a JSON object."
                )

            # Metadata comes from the trusted request, not the model.
            graph_data["project_id"] = request.project_id
            graph_data["graph_id"] = request.graph_id
            graph_data["version"] = 1
            graph_data["parent_version"] = None
            graph_data["created_by"] = request.created_by
            graph_data["schema_version"] = graph_data.get(
                "schema_version", "1.0"
            )

            if request.title is not None:
                graph_data["title"] = request.title

            existing_source_ids = graph_data.get("source_ids", [])
            if not isinstance(existing_source_ids, list):
                raise FireworksProviderError(
                    "Fireworks returned invalid source_ids."
                )

            graph_data["source_ids"] = list(
                dict.fromkeys([*existing_source_ids, request.source_id])
            )

            graph = MethodologyGraph.model_validate(graph_data)

        except FireworksProviderError:
            raise
        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            ValidationError,
        ) as exc:
            raise FireworksProviderError(
                "Fireworks returned an invalid methodology graph response."
            ) from exc

        return MethodologyExtractionResult(
            draft_graph=graph,
            provider_name="fireworks",
            model_name=self._model_name,
        )