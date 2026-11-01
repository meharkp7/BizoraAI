"""What-if evaluation for methodology steps.

A reader picks a methodology node, edits its stated settings (for example
2000 cells instead of the paper's stated count), and asks what would change.
The provider estimates the outcome from the paper's own text and numbers;
every number used must be cited, and the result is always labeled an
estimate, never a measurement.

Results are cached by (paper hash, node id, params) under the platform
cache dir, next to the diagram cache.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from bizora.contracts.diagram_ir import MethodologyNode

# Bumped when the what-if prompt wording changes estimated output.
WHATIF_PROMPT_VERSION = 1

_MAX_PARAMS = 32
_MAX_PARAM_CHARS = 256


class WhatIfBasis(BaseModel):
    """One paper number or statement the estimate rests on."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    quote: str = Field(min_length=1, max_length=1000)
    page: int | None = Field(default=None, ge=1)


class WhatIfResult(BaseModel):
    """Estimated outcome of running one step with modified settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=128)
    node_label: str = Field(min_length=1, max_length=512)
    params_previous: dict[str, str] = Field(default_factory=dict)
    params_applied: dict[str, str] = Field(default_factory=dict)
    outcome: str = Field(min_length=1, max_length=4000)
    basis: tuple[WhatIfBasis, ...] = Field(default_factory=tuple)
    assumptions: tuple[str, ...] = Field(default_factory=tuple)
    confidence: float = Field(ge=0.0, le=1.0)


WHATIF_RESULT_JSON_SCHEMA: dict[str, Any] = WhatIfResult.model_json_schema()


class WhatIfProvider(Protocol):
    """The single provider call what-if evaluation needs."""

    provider_name: str

    async def evaluate_what_if(
        self,
        node: MethodologyNode,
        new_params: dict[str, str],
        paper_text: str,
    ) -> WhatIfResult:
        """Estimate the outcome of a step under modified settings."""
        ...


WHATIF_INSTRUCTIONS = (
    "You estimate what would change if one research-paper methodology step "
    "ran with modified settings. You are given the step (label, detail, "
    "stated settings, supporting evidence), the modified settings, and the "
    "paper text with [Page N] markers. Reason ONLY from numbers and "
    "relationships the paper states: scale stated per-unit figures "
    "arithmetically when the paper supports the scaling, and say plainly "
    "what cannot be predicted without new measurement or simulation "
    "(measured outcomes such as error rates or yields never follow from "
    "arithmetic alone). Flag every modified setting the paper does not "
    "state as ungrounded. Write outcome as 2-4 sentences starting with "
    "the word 'Estimated'. List every paper number or statement used in "
    "basis with its short quote and page number, and every caveat in "
    "assumptions. Set confidence between 0 and 1: high only when the "
    "paper states both the inputs and the scaling. Output ONLY the JSON "
    "object: no markdown, no commentary, no extra keys."
)


def whatif_prompt(
    node: MethodologyNode,
    new_params: dict[str, str],
    paper_text: str,
) -> str:
    """Build the what-if evaluation prompt for one step."""
    stated = "\n".join(f"- {key}: {value}" for key, value in sorted(node.params.items()))
    modified = "\n".join(f"- {key}: {value}" for key, value in sorted(new_params.items()))
    evidence = ""
    if node.evidence is not None:
        page = f" [Page {node.evidence.page}]" if node.evidence.page else ""
        quote = f' "{node.evidence.quote}"' if node.evidence.quote else ""
        evidence = f"\nStep evidence:{page}{quote}"
    detail = f"\nStep detail: {node.detail}" if node.detail else ""
    return (
        f"Step: {node.label} ({node.id}){detail}\n"
        f"Stated settings:\n{stated or '(none stated)'}\n"
        f"Modified settings:\n{modified}{evidence}\n\n"
        f"Paper text:\n{paper_text}"
    )


def check_whatif_params(params: dict[str, str]) -> dict[str, str]:
    """Validate raw what-if params; raises ValueError on any violation."""
    if not params:
        raise ValueError("At least one parameter is required.")
    if len(params) > _MAX_PARAMS:
        raise ValueError(f"At most {_MAX_PARAMS} parameters are allowed.")
    cleaned: dict[str, str] = {}
    for key, value in params.items():
        clean_key = key.strip()
        clean_value = value.strip()
        if not clean_key:
            raise ValueError("Parameter names must be non-empty.")
        if len(clean_key) > 128:
            raise ValueError(f"Parameter name {clean_key!r} is too long.")
        if not clean_value:
            raise ValueError(f"Parameter {clean_key!r} must be non-empty.")
        if len(clean_value) > _MAX_PARAM_CHARS:
            raise ValueError(f"Parameter {clean_key!r} is too long.")
        cleaned[clean_key] = clean_value
    return cleaned


def whatif_cache_dir() -> Path:
    """Return the what-if cache directory, honoring test overrides."""
    override = os.environ.get("BIZORA_CACHE_DIR")
    if override:
        return Path(override) / "whatif"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "bizora" / "whatif"


def whatif_cache_key(paper_hash: str, node_id: str, params: dict[str, str]) -> str:
    """Build a stable cache key for one what-if evaluation."""
    digest = hashlib.sha256()
    for key in sorted(params):
        digest.update(key.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(params[key].encode("utf-8"))
        digest.update(b"\x00")
    safe_node = "".join(
        char if char.isalnum() or char in ("-", "_") else "_" for char in node_id
    )[:64]
    return (
        f"{paper_hash.strip().lower()}-{safe_node}-{digest.hexdigest()[:16]}"
        f"-w{WHATIF_PROMPT_VERSION}"
    )


def load_cached_whatif(key: str) -> WhatIfResult | None:
    """Return the cached what-if result for a key, or None on any miss."""
    try:
        payload = json.loads(
            (whatif_cache_dir() / f"{key}.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("prompt_version") != WHATIF_PROMPT_VERSION
    ):
        return None
    try:
        return WhatIfResult.model_validate(payload.get("result"))
    except ValueError:
        return None


def save_cached_whatif(key: str, result: WhatIfResult) -> None:
    """Persist one what-if result; cache failures never raise."""
    try:
        directory = whatif_cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{key}.json").write_text(
            json.dumps(
                {
                    "prompt_version": WHATIF_PROMPT_VERSION,
                    "result": result.model_dump(mode="json"),
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


async def run_what_if(
    provider: WhatIfProvider,
    paper_hash: str,
    node: MethodologyNode,
    new_params: dict[str, str],
    paper_text: str,
) -> tuple[WhatIfResult, bool]:
    """Evaluate a step under modified settings; returns (result, cached)."""
    params = check_whatif_params(new_params)
    key = whatif_cache_key(paper_hash, node.id, params)
    cached = load_cached_whatif(key)
    if cached is not None:
        return cached, True
    result = await provider.evaluate_what_if(
        node=node, new_params=params, paper_text=paper_text
    )
    save_cached_whatif(key, result)
    return result, False
