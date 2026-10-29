"""Muse Spark methodology extraction through the Meta Model Responses API.

The provider posts to ``POST {base_url}/responses`` with typed ``input``
content blocks (``input_text``, ``input_image``, ``input_file``) and asks
for structured output via ``text.format`` using the existing Pydantic
extraction contracts. Responses are validated locally before use.

Credential: pass ``api_key`` explicitly, or leave it unset to read the
``MUSE_API_KEY`` environment variable. For local development that variable
is supplied by ``/Users/meharkapoor7/BizoraAI/.env`` (load it with
python-dotenv before constructing the provider). This module only reads
the environment and never opens credential files itself.
"""

import base64
import json
import os
from typing import Any

import httpx
from pydantic import ValidationError

from bizora.contracts.figures import (
    FigureDescriptionList,
    FigureDescriptionRequest,
    FigureDescriptionResult,
    FigureRegionList,
    RegionLocalizationRequest,
    RegionLocalizationResult,
    ResponseUsage,
    build_figure_set,
    build_region_set,
)
from bizora.contracts.graph import MethodologyGraph
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyExtractionResult,
    MethodologyProviderError,
)

MUSE_API_KEY_ENV_VAR = "MUSE_API_KEY"
DEFAULT_MODEL_NAME = "muse-spark-1.3"
DEFAULT_BASE_URL = "https://api.meta.ai/v1"
MAX_OUTPUT_TOKENS = 16384
INLINE_FILE_LIMIT_BYTES = 50_000_000

GRAPH_SCHEMA_NAME = "MethodologyGraph"
FIGURES_SCHEMA_NAME = "FigureDescriptions"
REGIONS_SCHEMA_NAME = "FigureRegions"

# Minimal flat schemas for the vision calls. The generated Pydantic
# schemas ($defs/$ref, anyOf unions, patterns) degrade constrained
# vision output on this model; these plain shapes elicit clean JSON
# while local Pydantic validation stays the strict gate.
FIGURE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "figures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "figure_id": {"type": "string"},
                    "label": {"type": ["string", "null"]},
                    "caption": {"type": ["string", "null"]},
                    "kind": {
                        "type": "string",
                        "enum": ["diagram", "schematic", "plot", "photo", "equation", "unknown"],
                    },
                    "confidence": {"type": ["number", "null"]},
                },
                "required": ["figure_id", "label", "caption", "kind", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["figures"],
    "additionalProperties": False,
}

REGION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "regions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "figure_id": {"type": "string"},
                    "bbox": {"type": "array", "items": {"type": "number"}},
                    "node_id": {"type": ["string", "null"]},
                    "label": {"type": "string"},
                    "confidence": {"type": ["number", "null"]},
                },
                "required": ["figure_id", "bbox", "node_id", "label", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["regions"],
    "additionalProperties": False,
}


class MuseProviderError(MethodologyProviderError):
    """Raised when Muse cannot return a usable methodology draft."""


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


def _text_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Build the Responses API structured-output parameter."""
    return {
        "format": {
            "type": "json_schema",
            "name": name,
            "schema": schema,
            "strict": False,
        }
    }


def _extract_output_text(data: dict[str, Any]) -> str:
    """Concatenate output_text blocks from a Responses API payload."""
    shortcut = data.get("output_text")
    if isinstance(shortcut, str) and shortcut.strip():
        return shortcut
    output = data.get("output")
    if not isinstance(output, list):
        return ""
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "output_text":
                continue
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
    return "\n".join(parts)


def _extract_usage(data: dict[str, Any]) -> ResponseUsage:
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


_METHODOLOGY_INSTRUCTIONS = (
    "You extract a research paper from any field into a structured "
    "methodology graph. Return only a JSON object representing a "
    "MethodologyGraph with schema_version, project_id, graph_id, version, "
    "title, source_ids, nodes, edges, created_by, parent_version, brief, "
    "and domain_hint. Set domain_hint to the paper's system domain as a "
    "short lowercase label, preferring one of: electronics, deep-learning, "
    "signal-processing, quantization, distributed-systems, iot; use your "
    "best short label when none fits, or null when the domain is unclear. "
    "Nodes cover the paper's components, workflow steps, datasets, "
    "baselines, and experiments. Node kind must be one of: input, "
    "preprocessing, model, operation, loss, optimizer, evaluation, output, "
    "dataset, component. Use component for physical or architectural parts "
    "outside machine-learning vocabulary, such as circuit blocks or "
    "instruments. Edge relation must be one of: data_flow, control_flow, "
    "optimizes, evaluates, depends_on. Every edge must reference existing "
    "node IDs and must not connect a node to itself; feedback cycles "
    "between distinct nodes are allowed. Ground every node and edge in "
    "evidence: attach evidence entries with the given source ID, the page "
    "number from the [Page N] markers, and a short supporting quote from "
    "the paper text, with status supported or partial. Omit evidence you "
    "cannot support; never invent page numbers, quotes, results, or "
    "measurements. Set provenance to extracted for directly stated content "
    "and inferred for reasonable implications, with confidence between 0 "
    "and 1. Fill brief with the paper's research problem, objectives, "
    "findings, and limitations; use null or empty arrays for anything the "
    "paper does not state. Use empty arrays when no supported nodes or "
    "edges can be extracted."
)

_FIGURE_INSTRUCTIONS = (
    "You describe figures and diagrams from a research paper in any field. "
    "Each user message carries one figure image plus its surrounding text. "
    "Return only a JSON object shaped "
    '{"figures": [{"figure_id": str, "label": str | null, '
    '"caption": str | null, "kind": str, "confidence": float | null}]}. '
    "Echo each figure_id exactly as given, one entry per figure. "
    "Output ONLY the JSON object: no markdown, no commentary, no extra "
    "keys. Decide from the image pixels first, then ground words in the "
    "hints. Set kind to the ONE visual form that fits this image: photo "
    "for camera, microscope, or die shots; plot for charts, graphs, and "
    "histograms; schematic for circuit diagrams; diagram for block and "
    "flow diagrams; equation for math; unknown only when the image "
    "matches none of these. Set caption to the full caption-candidate "
    "text whose words describe visible content in this image; when no "
    "candidate matches, null. Set label to the figure mention at the "
    "start of the chosen caption candidate (for example 'Figure 3'); "
    "when caption is null, label is null too. Never invent, shorten, "
    "or reword labels and captions: transcribe exactly or use null."
)

_REGION_INSTRUCTIONS = (
    "You locate methodology components inside research-paper figures, in any "
    "research field. Each request lists graph nodes (id, kind, label) and "
    "carries figure images. Return only a JSON object shaped "
    '{"regions": [{"figure_id": str, "bbox": [x, y, width, height], '
    '"node_id": str | null, "label": str, "confidence": float | null}]}. '
    "Echo each figure_id exactly as given. Output ONLY the JSON "
    "object: no markdown, no commentary, no extra keys. Bboxes use "
    "normalized 0..1 coordinates: x and y mark the top-left corner as "
    "fractions of the image width and height, width and height are "
    "fractions of the image size. Localize every distinct labeled "
    "component, sub-panel, and legended feature: typical figures yield "
    "several regions, not one. Set node_id to a listed node id whenever "
    "the region clearly depicts that component; otherwise null. Label "
    "each region with its visible caption or a short neutral "
    "description. Never invent regions, boxes, or node links that are "
    "not visible in the image."
)


class MuseMethodologyProvider:
    """Extract drafts using Muse Spark through the Responses API."""

    provider_name = "muse"

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
        self.last_usage: ResponseUsage | None = None

    async def extract_methodology(
        self,
        request: MethodologyExtractionRequest,
    ) -> MethodologyExtractionResult:
        """Request a schema-constrained graph and parse it into a draft."""
        content: list[dict[str, str]] = [
            {
                "type": "input_text",
                "text": (
                    f"Project ID: {request.project_id}\n"
                    f"Graph ID: {request.graph_id}\n"
                    f"Source ID: {request.source_id}\n"
                    f"Requested title: {request.title or 'Infer from paper'}\n\n"
                    "Extract the methodology from this paper text. Page "
                    "boundaries are marked like [Page N]:\n"
                    f"{request.paper_text}"
                ),
            }
        ]
        data = await self._create_response(
            instructions=_METHODOLOGY_INSTRUCTIONS,
            content=content,
            schema_name=GRAPH_SCHEMA_NAME,
            schema=MethodologyGraph.model_json_schema(),
        )
        return self._methodology_result(request, data)

    async def extract_methodology_with_pdf(
        self,
        request: MethodologyExtractionRequest,
        pdf_bytes: bytes,
        filename: str = "paper.pdf",
    ) -> MethodologyExtractionResult:
        """Extract a draft from paper text plus the original PDF bytes.

        The PDF travels inline as base64 (Responses API ``input_file``);
        files at or under the documented inline limit are accepted.
        """
        if not pdf_bytes:
            raise MuseProviderError("Muse PDF input must not be empty.")
        if len(pdf_bytes) > INLINE_FILE_LIMIT_BYTES:
            raise MuseProviderError(
                f"Muse PDF input exceeds the inline file limit ({INLINE_FILE_LIMIT_BYTES} bytes)."
            )
        if not filename.strip():
            raise MuseProviderError("Muse PDF input needs a filename.")

        encoded = base64.b64encode(pdf_bytes).decode("ascii")
        content: list[dict[str, str]] = [
            {
                "type": "input_text",
                "text": (
                    f"Project ID: {request.project_id}\n"
                    f"Graph ID: {request.graph_id}\n"
                    f"Source ID: {request.source_id}\n"
                    f"Requested title: {request.title or 'Infer from paper'}\n\n"
                    "Extract the methodology from the attached PDF and this "
                    "paper text. Page boundaries are marked like [Page N]:\n"
                    f"{request.paper_text}"
                ),
            },
            {
                "type": "input_file",
                "filename": filename,
                "file_data": f"data:application/pdf;base64,{encoded}",
            },
        ]
        data = await self._create_response(
            instructions=_METHODOLOGY_INSTRUCTIONS,
            content=content,
            schema_name=GRAPH_SCHEMA_NAME,
            schema=MethodologyGraph.model_json_schema(),
        )
        return self._methodology_result(request, data)

    def _methodology_result(
        self,
        request: MethodologyExtractionRequest,
        data: dict[str, Any],
    ) -> MethodologyExtractionResult:
        """Parse a response payload into a trusted draft graph."""
        graph_data = self._response_json_object(data, what="methodology graph")

        if not isinstance(graph_data, dict):
            raise MuseProviderError("Muse output must be a JSON object.")

        # Metadata comes from the trusted request, not the model.
        graph_data["project_id"] = request.project_id
        graph_data["graph_id"] = request.graph_id
        graph_data["version"] = 1
        graph_data["parent_version"] = None
        graph_data["created_by"] = request.created_by
        graph_data["schema_version"] = graph_data.get("schema_version", "1.0")

        if request.title is not None:
            graph_data["title"] = request.title

        existing_source_ids = graph_data.get("source_ids", [])
        if not isinstance(existing_source_ids, list):
            raise MuseProviderError("Muse returned invalid source_ids.")

        graph_data["source_ids"] = list(dict.fromkeys([*existing_source_ids, request.source_id]))

        try:
            graph = MethodologyGraph.model_validate(graph_data)
        except ValidationError as exc:
            errors = exc.errors()
            first = errors[0]
            location = ".".join(str(part) for part in first["loc"])
            summary = f"{len(errors)} errors; first at {location}: {first['msg']}"
            raise MuseProviderError(
                f"Muse returned an invalid methodology graph response ({summary[:300]})."
            ) from exc

        return MethodologyExtractionResult(
            draft_graph=graph,
            provider_name=self.provider_name,
            model_name=self._model_name,
        )

    async def describe_figures(
        self,
        request: FigureDescriptionRequest,
    ) -> FigureDescriptionResult:
        """Describe figure images, merged with trusted attachment metadata."""
        content: list[dict[str, str]] = []
        for figure in request.figures:
            encoded = base64.b64encode(figure.image_bytes).decode("ascii")
            hint_lines = [
                f"Figure ID: {figure.figure_id}",
                f"Page: {figure.page if figure.page is not None else 'unknown'}",
            ]
            if figure.label_hint:
                hint_lines.append(
                    "Label hints (printed labels found on this page; "
                    f"use one only if it belongs to this image): {figure.label_hint}"
                )
            if figure.caption_hint:
                hint_lines.append(
                    "Caption candidates (transcribe the one that captions "
                    f"this image):\n{figure.caption_hint}"
                )
            if figure.surrounding_text:
                hint_lines.append(f"Surrounding text:\n{figure.surrounding_text}")
            content.append({"type": "input_text", "text": "\n".join(hint_lines)})
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{figure.mime_type};base64,{encoded}",
                }
            )

        data = await self._create_response(
            instructions=_FIGURE_INSTRUCTIONS,
            content=content,
            schema_name=FIGURES_SCHEMA_NAME,
            schema=FIGURE_OUTPUT_SCHEMA,
        )
        raw = self._response_json_object(data, what="figure description")

        if not isinstance(raw, dict):
            raise MuseProviderError("Muse output must be a JSON object.")
        try:
            descriptions = FigureDescriptionList.model_validate(raw)
        except ValidationError as exc:
            raise MuseProviderError(
                "Muse returned an invalid figure description response."
            ) from exc

        figure_set, warnings = build_figure_set(request, descriptions)
        return FigureDescriptionResult(
            draft_figures=figure_set,
            provider_name=self.provider_name,
            model_name=self._model_name,
            warnings=warnings,
            usage=self.last_usage,
        )

    async def localize_regions(
        self,
        request: RegionLocalizationRequest,
    ) -> RegionLocalizationResult:
        """Locate graph nodes inside figure images, merged with trusted IDs."""
        node_lines = ["Graph nodes (link a region only to these ids):"]
        for node in request.nodes:
            line = f"- {node.node_id} [{node.kind}] {node.label}"
            if node.description:
                line += f": {node.description}"
            node_lines.append(line)
        content: list[dict[str, str]] = [
            {"type": "input_text", "text": "\n".join(node_lines)}
        ]
        for figure in request.figures:
            encoded = base64.b64encode(figure.image_bytes).decode("ascii")
            hint_lines = [
                f"Figure ID: {figure.figure_id}",
                f"Page: {figure.page if figure.page is not None else 'unknown'}",
            ]
            if figure.label_hint:
                hint_lines.append(
                    "Label hints (printed labels found on this page; "
                    f"use one only if it belongs to this image): {figure.label_hint}"
                )
            if figure.caption_hint:
                hint_lines.append(
                    "Caption candidates (the one that captions "
                    f"this image):\n{figure.caption_hint}"
                )
            if figure.surrounding_text:
                hint_lines.append(f"Surrounding text:\n{figure.surrounding_text}")
            content.append({"type": "input_text", "text": "\n".join(hint_lines)})
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{figure.mime_type};base64,{encoded}",
                }
            )

        data = await self._create_response(
            instructions=_REGION_INSTRUCTIONS,
            content=content,
            schema_name=REGIONS_SCHEMA_NAME,
            schema=REGION_OUTPUT_SCHEMA,
        )
        raw = self._response_json_object(data, what="figure region")

        if not isinstance(raw, dict):
            raise MuseProviderError("Muse output must be a JSON object.")
        try:
            proposals = FigureRegionList.model_validate(raw)
        except ValidationError as exc:
            raise MuseProviderError(
                "Muse returned an invalid figure region response."
            ) from exc

        region_set, warnings = build_region_set(request, proposals)
        return RegionLocalizationResult(
            draft_regions=region_set,
            provider_name=self.provider_name,
            model_name=self._model_name,
            warnings=warnings,
            usage=self.last_usage,
        )

    def _response_json_object(self, data: dict[str, Any], *, what: str) -> Any:
        """Parse the concatenated output text of a response payload."""
        try:
            content = _extract_output_text(data)
            if not content.strip():
                raise MuseProviderError("Muse returned an empty response.")
            return _parse_json_object(content)
        except MuseProviderError:
            raise
        except (TypeError, ValueError) as exc:
            raise MuseProviderError(f"Muse returned an invalid {what} response.") from exc

    async def _create_response(
        self,
        *,
        instructions: str,
        content: list[dict[str, str]],
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """POST one Responses request and return the decoded payload."""
        payload: dict[str, Any] = {
            "model": self._model_name,
            "store": False,
            "instructions": instructions,
            "input": [{"role": "user", "content": content}],
            "text": _text_format(schema_name, schema),
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        }
        try:
            response = await self._post(payload)
        except MuseProviderError as exc:
            if "text.format" not in str(exc).lower() and "schema" not in str(exc).lower():
                raise
            fallback = {key: value for key, value in payload.items() if key != "text"}
            response = await self._post(fallback)

        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise MuseProviderError("Muse returned an unreadable response.") from exc

        status = data.get("status")
        if status is not None and status != "completed":
            detail = data.get("error", status)
            raise MuseProviderError(f"Muse did not complete the response ({detail}).")

        self.last_usage = _extract_usage(data)
        return data

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        """POST one payload to the Responses endpoint."""
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
            raise MuseProviderError(
                f"Muse returned HTTP {exc.response.status_code} ({body})."
            ) from exc
        except httpx.RequestError as exc:
            raise MuseProviderError("Could not connect to the Muse API.") from exc
        return response
