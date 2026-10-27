
"""Fireworks AI implementation of the methodology provider interface."""

import json
from typing import Any

import httpx
from pydantic import ValidationError

from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.table import ExtractedTable
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyExtractionResult,
    MethodologyProviderError,
)
from bizora.providers.tables import (
    TableExtractionRequest,
    TableExtractionResult,
)


class FireworksProviderError(MethodologyProviderError):
    """Raised when Fireworks cannot return a usable methodology draft."""


GRAPH_JSON_SCHEMA = json.dumps(
    MethodologyGraph.model_json_schema(), separators=(",", ":")
)


def _parse_json_object(content: str) -> Any:
    """Parse model JSON, tolerating markdown fences around the object."""
    try:
        return json.loads(content)
    except ValueError:
        stripped = content.strip()
        if not stripped.startswith("```"):
            raise
        lines = stripped.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return json.loads("\n".join(lines))


class FireworksMethodologyProvider:
    """Extract drafts using an OpenAI-compatible chat completions API."""

    DEFAULT_BASE_URL = "https://api.fireworks.ai/inference/v1"

    provider_name = "fireworks"
    error_label = "Fireworks"
    error_type: type[MethodologyProviderError] = FireworksProviderError

    def __init__(
        self,
        api_key: str,
        model_name: str,
        *,
        base_url: str | None = None,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError(f"{self.error_label} API key must not be empty.")
        if not model_name.strip():
            raise ValueError(f"{self.error_label} model name must not be empty.")
        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")

        self._api_key = api_key
        self._model_name = model_name
        self._base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
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
                    "You extract a research paper from any field into a "
                    "structured methodology graph. Return only a JSON object "
                    "representing a MethodologyGraph with schema_version, "
                    "project_id, graph_id, version, title, source_ids, nodes, "
                    "edges, created_by, parent_version, and brief. "
                    "Nodes cover the paper's components, workflow steps, "
                    "datasets, baselines, and experiments. Node kind must be "
                    "one of: input, preprocessing, model, operation, loss, "
                    "optimizer, evaluation, output, dataset, component. Use "
                    "component for physical or architectural parts outside "
                    "machine-learning vocabulary, such as circuit blocks or "
                    "instruments. Edge relation must be one of: data_flow, "
                    "control_flow, optimizes, evaluates, depends_on. Every "
                    "edge must reference existing node IDs and must not "
                    "connect a node to itself; feedback cycles between "
                    "distinct nodes are allowed. "
                    "Ground every node and edge in evidence: attach evidence "
                    "entries with the given source ID, the page number from "
                    "the [Page N] markers, and a short supporting quote from "
                    "the paper text, with status supported or partial. Omit "
                    "evidence you cannot support; never invent page numbers, "
                    "quotes, results, or measurements. Set provenance to "
                    "extracted for directly stated content and inferred for "
                    "reasonable implications, with confidence between 0 and 1. "
                    "Keep internal reasoning brief and output the JSON object "
                    "immediately. "
                    "Fill brief with the paper's research problem, "
                    "objectives, findings, and limitations; use null or empty "
                    "arrays for anything the paper does not state. Use empty "
                    "arrays when no supported nodes or edges can be "
                    "extracted. The calling application will assign "
                    "authoritative graph metadata. The JSON object MUST "
                    "validate against this JSON Schema (required fields, "
                    "enums, patterns, no additional properties): "
                    f"{GRAPH_JSON_SCHEMA}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Project ID: {request.project_id}\n"
                    f"Graph ID: {request.graph_id}\n"
                    f"Source ID: {request.source_id}\n"
                    f"Requested title: {request.title or 'Infer from paper'}\n\n"
                    "Extract the methodology from this paper text. Page "
                    "boundaries are marked like [Page N]:\n"
                    f"{request.paper_text}"
                ),
            },
        ]

        response = await self._chat_completion(messages, max_tokens=16384)

        try:
            response_data: dict[str, Any] = response.json()
            content = response_data["choices"][0]["message"]["content"]

            if not isinstance(content, str) or not content.strip():
                raise self.error_type(
                    f"{self.error_label} returned an empty response."
                )

            graph_data = _parse_json_object(content)

            if not isinstance(graph_data, dict):
                raise self.error_type(
                    f"{self.error_label} output must be a JSON object."
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
                raise self.error_type(
                    f"{self.error_label} returned invalid source_ids."
                )

            graph_data["source_ids"] = list(
                dict.fromkeys([*existing_source_ids, request.source_id])
            )

            graph = MethodologyGraph.model_validate(graph_data)

        except MethodologyProviderError:
            raise
        except ValidationError as exc:
            errors = exc.errors()
            first = errors[0]
            location = ".".join(str(part) for part in first["loc"])
            summary = f"{len(errors)} errors; first at {location}: {first['msg']}"
            raise self.error_type(
                f"{self.error_label} returned an invalid methodology graph "
                f"response ({summary[:300]})."
            ) from exc
        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as exc:
            raise self.error_type(
                f"{self.error_label} returned an invalid methodology graph response."
            ) from exc

        return MethodologyExtractionResult(
            draft_graph=graph,
            provider_name=self.provider_name,
            model_name=self._model_name,
        )

    async def _chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
    ) -> httpx.Response:
        """POST one chat-completion request and return the response."""
        payload = {
            "model": self._model_name,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
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
            raise self.error_type(
                f"{self.error_label} returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            raise self.error_type(
                f"Could not connect to the {self.error_label} API."
            ) from exc

        return response

    async def extract_tables(
        self,
        request: TableExtractionRequest,
    ) -> TableExtractionResult:
        """Request JSON tables and parse them into typed drafts."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You extract results tables from a research paper in any "
                    "field. Return only a JSON object shaped "
                    '{"tables": [{"table_id": str, "caption": str, '
                    '"columns": [str], "rows": [[str]], "page": int | null, '
                    '"quote": str | null}]}. '
                    f"Include at most {request.max_tables} tables, in paper "
                    "order. Cover results, benchmark, ablation, comparison, "
                    "measurement, and specification tables; skip references "
                    "and author lists. Preserve each table's headings, units, "
                    "and footnotes exactly as printed, keeping units inside "
                    "cells or headers rather than dropping them. Every row "
                    "must have exactly one cell per column. Transcribe cell "
                    "values exactly as printed; never invent numbers, "
                    "captions, or tables. Set page from the [Page N] markers "
                    "and quote to a short supporting excerpt; use null when "
                    "unknown. Keep internal reasoning brief and output the "
                    "JSON object immediately. Use an empty tables array when "
                    "no results tables are present."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Source ID: {request.source_id}\n\n"
                    "Extract the results tables from this paper text. Page "
                    "boundaries are marked like [Page N]:\n"
                    f"{request.paper_text}"
                ),
            },
        ]

        response = await self._chat_completion(messages, max_tokens=16384)

        try:
            response_data: dict[str, Any] = response.json()
            content = response_data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise self.error_type(
                    f"{self.error_label} returned an empty response."
                )
            table_data = _parse_json_object(content)
            if not isinstance(table_data, dict):
                raise self.error_type(
                    f"{self.error_label} output must be a JSON object."
                )
            raw_tables = table_data.get("tables", [])
            if not isinstance(raw_tables, list):
                raise self.error_type(
                    f"{self.error_label} returned an invalid tables array."
                )
        except MethodologyProviderError:
            raise
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise self.error_type(
                f"{self.error_label} returned an invalid tables response."
            ) from exc

        tables: list[ExtractedTable] = []
        warnings: list[str] = []
        for index, raw in enumerate(raw_tables[: request.max_tables]):
            if not isinstance(raw, dict):
                warnings.append(f"Table {index + 1} was skipped: not an object.")
                continue
            candidate = {
                **raw,
                "project_id": request.project_id,
                "graph_id": request.graph_id,
                "source_id": request.source_id,
                "created_by": request.created_by,
            }
            try:
                tables.append(ExtractedTable.model_validate(candidate))
            except ValidationError as exc:
                warnings.append(
                    f"Table {index + 1} was skipped: {exc.errors()[0]['msg']}."
                )

        return TableExtractionResult(
            draft_tables=tuple(tables),
            provider_name=self.provider_name,
            model_name=self._model_name,
            warnings=tuple(warnings),
        )