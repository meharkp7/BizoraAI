"""Citation contracts and validation for grounded answers.

The model returns its final answer as a structured
:class:`CopilotAnswer` whose citations point at tool results from the
same conversation. The validator re-checks every citation against
what the tools actually returned (and against the live context for
evidence), so a fabricated page number, run id, or part id is
caught before the answer reaches the user.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from bizora.contracts.components import CopilotProposal
from bizora.copilot.tools import CopilotContext


class EvidenceCitation(BaseModel):
    """One citation to paper evidence observed through read_evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["evidence"] = "evidence"
    source_id: str = Field(min_length=1, max_length=128)
    page: int | None = Field(default=None, ge=1)
    quote: str | None = Field(default=None, min_length=1, max_length=2000)
    figure_label: str | None = Field(default=None, max_length=128)
    target_id: str | None = Field(
        default=None, max_length=128, description="Node or edge the evidence came from."
    )


class RunCitation(BaseModel):
    """One citation to an experiment run observed through query_runs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["run"] = "run"
    run_id: str = Field(min_length=1, max_length=128)
    metric_name: str | None = Field(default=None, max_length=128)


class ComponentCitation(BaseModel):
    """One citation to a catalog entry observed through search_library."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["component"] = "component"
    component_id: str = Field(min_length=1, max_length=128)


Citation = EvidenceCitation | RunCitation | ComponentCitation


class CopilotAnswer(BaseModel):
    """The model's structured final answer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reply: str = Field(min_length=1, max_length=6000)
    citations: tuple[Citation, ...] = ()
    proposal: CopilotProposal | None = None
    assumed: bool = False


class CitationFinding(BaseModel):
    """One invalid citation plus the reason it failed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)


class CitationReport(BaseModel):
    """The verdict on every citation in one answer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: tuple[Citation, ...] = ()
    invalid: tuple[CitationFinding, ...] = ()

    @property
    def all_valid(self) -> bool:
        """Return whether every citation checked out."""
        return len(self.invalid) == 0


def _normalize_quote(quote: str) -> str:
    return " ".join(quote.strip().lower().split())


def collect_observed_grounding(tool_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Collect citable facts from tool results in one conversation."""
    evidence: list[dict[str, Any]] = []
    run_ids: set[str] = set()
    metric_names: dict[str, set[str]] = {}
    component_ids: set[str] = set()
    for result in tool_results:
        if not isinstance(result, dict) or "error" in result:
            continue
        target = result.get("target")
        if isinstance(target, dict) and isinstance(target.get("evidence"), list):
            for ref in target["evidence"]:
                if isinstance(ref, dict) and isinstance(ref.get("source_id"), str):
                    evidence.append(ref)
        for run in result.get("runs", []) or []:
            if not isinstance(run, dict) or not isinstance(run.get("run_id"), str):
                continue
            run_ids.add(run["run_id"])
            names = metric_names.setdefault(run["run_id"], set())
            for metric in run.get("metrics", []) or []:
                if isinstance(metric, dict) and isinstance(metric.get("name"), str):
                    names.add(metric["name"])
        for match in result.get("matches", []) or []:
            if isinstance(match, dict) and isinstance(match.get("component_id"), str):
                component_ids.add(match["component_id"])
        candidate = result.get("component_id")
        if isinstance(candidate, str) and candidate:
            component_ids.add(candidate)
        proposal = result.get("proposal")
        if isinstance(proposal, dict) and isinstance(proposal.get("component_id"), str):
            component_ids.add(proposal["component_id"])
    return {
        "evidence": evidence,
        "run_ids": run_ids,
        "metric_names": metric_names,
        "component_ids": component_ids,
    }


def _evidence_matches(ref: dict[str, Any], citation: EvidenceCitation) -> bool:
    if ref.get("source_id") != citation.source_id:
        return False
    if citation.page is not None and ref.get("page") != citation.page:
        return False
    if citation.figure_label is not None and ref.get("figure_label") != citation.figure_label:
        return False
    if citation.quote is not None:
        observed = ref.get("quote")
        if not isinstance(observed, str):
            return False
        wanted = _normalize_quote(citation.quote)
        seen = _normalize_quote(observed)
        if not wanted or wanted not in seen:
            return False
    return True


def validate_citations(
    answer: CopilotAnswer,
    tool_results: list[dict[str, Any]],
    context: CopilotContext,
) -> CitationReport:
    """Check every citation against observed tool output and live state."""
    observed = collect_observed_grounding(tool_results)
    evidence_refs: list[dict[str, Any]] = observed["evidence"]
    run_ids: set[str] = observed["run_ids"]
    metric_names: dict[str, set[str]] = observed["metric_names"]
    component_ids: set[str] = observed["component_ids"]

    valid: list[Citation] = []
    invalid: list[CitationFinding] = []
    for index, citation in enumerate(answer.citations):
        if isinstance(citation, EvidenceCitation):
            if citation.page is None and citation.quote is None and citation.figure_label is None:
                invalid.append(
                    CitationFinding(
                        index=index,
                        reason="Evidence citation needs a page, quote, or figure label.",
                    )
                )
                continue
            if any(_evidence_matches(ref, citation) for ref in evidence_refs):
                valid.append(citation)
            else:
                # Fall back to live graph state so citations stay valid
                # even when the evidence arrived via an older tool call.
                live = _live_evidence(context)
                if any(_evidence_matches(ref, citation) for ref in live):
                    valid.append(citation)
                else:
                    invalid.append(
                        CitationFinding(
                            index=index,
                            reason=(f"No observed evidence matches source {citation.source_id!r}."),
                        )
                    )
        elif isinstance(citation, RunCitation):
            run = context.run(citation.run_id)
            if citation.run_id not in run_ids and run is None:
                invalid.append(
                    CitationFinding(
                        index=index,
                        reason=f"Run {citation.run_id!r} was not observed in this conversation.",
                    )
                )
            elif citation.metric_name is not None:
                observed_names = set(metric_names.get(citation.run_id, set()))
                live_names = {m.name for m in context.metrics(citation.run_id)}
                if citation.metric_name not in observed_names | live_names:
                    invalid.append(
                        CitationFinding(
                            index=index,
                            reason=(
                                f"Metric {citation.metric_name!r} was not observed "
                                f"for run {citation.run_id!r}."
                            ),
                        )
                    )
                else:
                    valid.append(citation)
            else:
                valid.append(citation)
        else:
            if citation.component_id in component_ids:
                valid.append(citation)
            else:
                invalid.append(
                    CitationFinding(
                        index=index,
                        reason=(
                            f"Component {citation.component_id!r} was not observed "
                            "in this conversation."
                        ),
                    )
                )
    return CitationReport(valid=tuple(valid), invalid=tuple(invalid))


def _live_evidence(context: CopilotContext) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for node in context.graph.nodes:
        refs.extend(ref.model_dump(mode="json") for ref in node.evidence)
    for edge in context.graph.edges:
        refs.extend(ref.model_dump(mode="json") for ref in edge.evidence)
    return refs
