"""Deterministic plain-English parsing for paper what-ifs.

No language model is involved: the parser matches methodology step
labels and setting names literally, so its failures are explainable
and its successes reproducible. Anything it cannot resolve raises
WhatIfParseError with a message that names what it needs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bizora.contracts.diagram_ir import MethodologyNode

#: Verbs and marks that join a setting name to its new value. Bare
#: "of" is excluded: "layers of the encoder" names no value, while the
#: leader pattern still accepts "with dropout of 0.5".
_VALUE_SEPARATORS = (
    "was",
    "were",
    "is",
    "are",
    "be",
    "becomes",
    "become",
    "became",
    "to",
    "=",
    ":",
)

#: Introducers of a bare "setting value" pair: leading verbs plus
#: list continuations ("layers 6 and dropout 0.5").
_PAIR_LEADERS = ("with", "using", "set", "and", ",")

_MAX_VALUE_CHARS = 200


@dataclass(frozen=True)
class ParsedWhatIf:
    """A plain-English question resolved to one step plus settings."""

    node_id: str
    node_label: str
    params: dict[str, str]


class WhatIfParseError(ValueError):
    """A plain-English what-if the parser cannot resolve honestly."""


def parse_whatif_text(
    nodes: list[MethodologyNode],
    text: str,
    *,
    context_node_id: str | None = None,
) -> ParsedWhatIf:
    """Resolve text like "what if the encoder had 6 layers?" to a step plus settings."""
    cleaned = " ".join(text.split())
    if not cleaned:
        raise WhatIfParseError("Describe a change, for example 'what if layers were 6?'.")
    if not nodes:
        raise WhatIfParseError("This paper exposes no methodology steps to vary.")

    node = _resolve_node(nodes, cleaned, context_node_id)
    params = _extract_params(node, cleaned)
    if not params:
        known = ", ".join(
            f"{key} (now {value})" for key, value in sorted(node.params.items())
        )
        raise WhatIfParseError(
            f"I found the {node.label} step but no new setting. "
            + (
                f"It exposes: {known}."
                if known
                else "The paper states no settings for this step."
            )
        )
    return ParsedWhatIf(node_id=node.id, node_label=node.label, params=params)


def _resolve_node(
    nodes: list[MethodologyNode],
    text: str,
    context_node_id: str | None,
) -> MethodologyNode:
    """Pick the mentioned step, falling back to the open step when named."""
    lowered = text.lower()
    matches: list[tuple[int, MethodologyNode]] = []
    for node in nodes:
        for alias in (node.label, node.id):
            if not alias:
                continue
            pattern = r"\b" + re.escape(alias.lower()) + r"\b"
            if re.search(pattern, lowered):
                matches.append((len(alias), node))
                break

    unique = {node.id: (length, node) for length, node in matches}
    if len(unique) > 1:
        labels = sorted(node.label for _, node in unique.values())
        raise WhatIfParseError(
            "That names more than one step ("
            + ", ".join(labels)
            + "). Ask about one step at a time."
        )
    if unique:
        return next(iter(unique.values()))[1]

    if context_node_id is not None:
        context = next((node for node in nodes if node.id == context_node_id), None)
        if context is not None:
            return context

    steps = ", ".join(node.label for node in nodes[:8])
    raise WhatIfParseError(
        "Which step? This paper has: " + steps + (", …" if len(nodes) > 8 else "")
    )


def _extract_params(node: MethodologyNode, text: str) -> dict[str, str]:
    """Pull setting assignments for one step out of free text."""
    params: dict[str, str] = {}
    keys = sorted((str(key) for key in node.params), key=len, reverse=True)
    for key in keys:
        value = (
            _value_after_separator(text, key)
            or _value_after_leader(text, key)
            or _value_before_key(text, key)
        )
        if value is not None:
            params[key] = value
    return params


def _value_after_separator(text: str, key: str) -> str | None:
    """Match "<setting> was|to|=|: <value>"."""
    separators = "|".join(re.escape(item) for item in _VALUE_SEPARATORS)
    pattern = re.compile(
        r"\b" + re.escape(key) + r"\b\s*(?:" + separators + r")\s*",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if match is None:
        return None
    return _clean_value(text[match.end():])


def _value_after_leader(text: str, key: str) -> str | None:
    """Match "with|using|set|and|, <setting> <value>"."""
    leaders = "|".join(re.escape(item) for item in _PAIR_LEADERS)
    separators = "|".join(re.escape(item) for item in ("to", "of", "=", ":"))
    pattern = re.compile(
        r"\b(?:" + leaders + r")\s*\b" + re.escape(key) + r"\b\s*(?:" + separators + r")?\s*",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if match is None:
        return None
    return _clean_value(text[match.end():])


def _value_before_key(text: str, key: str) -> str | None:
    """Match a numeric value ahead of its setting: "6 layers"."""
    pattern = re.compile(r"(\d[\w.%]*)\s+\b" + re.escape(key) + r"\b", re.IGNORECASE)
    match = pattern.search(text)
    if match is None:
        return None
    return _clean_value(match.group(1))


def _clean_value(fragment: str) -> str | None:
    """Cut a raw value at the next clause boundary."""
    cut = re.split(r"\s+and\s+|,|;|\.(?:\s|$)|$", fragment, maxsplit=1)[0]
    value = cut.strip().strip("\"'").strip()
    value = re.sub(r"^(to\s+be|be)\s+", "", value, flags=re.IGNORECASE).strip()
    value = re.sub(r"[.?!]+$", "", value).strip()
    if not value or len(value) > _MAX_VALUE_CHARS:
        return None
    return value

