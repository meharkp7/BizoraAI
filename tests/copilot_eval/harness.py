"""Offline-first evaluation harness for the grounded copilot (R9).

Each question in ``questions.json`` carries a recorded transcript
(scripted assistant turns plus a final structured answer). The
offline run replays those transcripts through the REAL orchestration
loop: tools execute for real against the fixture world, citations
are validated for real, and the score measures citation accuracy.
Zero API spend.

Live mode (:func:`run_live_subset`) answers a small subset with a
real provider and caches each transcript under ``.cache/answers/``;
a later offline run replays the cached live transcript instead of
the authored script when ``prefer_live`` is set. Token usage is
summed from provider usage on every path and reported exactly.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bizora.copilot.citations import CopilotAnswer, validate_citations
from bizora.copilot.service import CopilotRunReport, answer_with_llm
from bizora.copilot.testing import make_eval_context
from bizora.copilot.tools import CopilotContext, execute_tool
from bizora.providers.copilot import (
    CopilotAssistantTurn,
    CopilotProvider,
    CopilotToolCall,
)
from bizora.providers.fixture_copilot import RecordedTranscript, ScriptedCopilotProvider

EVAL_DIR = Path(__file__).parent
QUESTIONS_PATH = EVAL_DIR / "questions.json"
CACHE_DIR = EVAL_DIR / ".cache" / "answers"
RESULTS_PATH = EVAL_DIR / ".cache" / "results" / "latest.json"


class ExpectedProposal(BaseModel):
    """The proposal a question requires (subset match on config)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=128)
    config: dict[str, Any] = Field(default_factory=dict)


class ExpectedAnswer(BaseModel):
    """The scoreable expectations for one eval question."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    citations: tuple[dict[str, Any], ...] = ()
    proposal: ExpectedProposal | None = None
    assumed: bool = False
    reply_contains: tuple[str, ...] = ()


class EvalQuestion(BaseModel):
    """One eval question with its recorded transcript."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=32)
    category: str = Field(min_length=1, max_length=32)
    message: str = Field(min_length=1, max_length=2000)
    selected_node_id: str | None = Field(default=None, max_length=128)
    expected: ExpectedAnswer
    script: tuple[dict[str, Any], ...] = Field(min_length=1)


class QuestionResult(BaseModel):
    """The scored outcome for one question."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    category: str
    passed: bool
    expected_citations: int = 0
    matched_citations: int = 0
    proposal_ok: bool = True
    assumed_ok: bool = True
    notes: tuple[str, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0


class EvalReport(BaseModel):
    """The scored outcome for the whole eval set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int = 0
    passed: int = 0
    citation_accuracy: float = 0.0
    citation_recall: float = 0.0
    writes_detected: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    results: tuple[QuestionResult, ...] = ()

    @property
    def accuracy(self) -> float:
        """Return the share of questions that passed."""
        return self.passed / self.total if self.total else 0.0


def load_questions(path: Path = QUESTIONS_PATH) -> list[EvalQuestion]:
    """Load and validate the eval question set."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("questions.json must be a non-empty list.")
    questions = [EvalQuestion.model_validate(item) for item in raw]
    ids = [q.id for q in questions]
    if len(set(ids)) != len(ids):
        raise ValueError("Eval question ids must be unique.")
    return questions


def script_to_transcript(script: tuple[dict[str, Any], ...]) -> RecordedTranscript:
    """Convert authored script turns to a replayable transcript.

    A turn is either ``{"content": str, "tool_calls": [...]}`` or
    ``{"answer": {...}}`` for the final structured answer.
    """
    turns: list[CopilotAssistantTurn] = []
    for raw in script:
        if "answer" in raw:
            content = json.dumps(raw["answer"])
            CopilotAnswer.model_validate(raw["answer"])
            turns.append(CopilotAssistantTurn(content=content))
        else:
            calls = tuple(
                CopilotToolCall(
                    id=call["id"],
                    name=call["name"],
                    arguments=dict(call.get("arguments", {})),
                )
                for call in raw.get("tool_calls", [])
            )
            turns.append(CopilotAssistantTurn(content=raw.get("content", ""), tool_calls=calls))
    return RecordedTranscript(turns=tuple(turns))


def cached_transcript_path(question_id: str, cache_dir: Path = CACHE_DIR) -> Path:
    """Return the cache file for one live transcript."""
    return cache_dir / f"{question_id}.json"


def save_live_transcript(
    question_id: str,
    transcript: RecordedTranscript,
    report: CopilotRunReport,
    cache_dir: Path = CACHE_DIR,
) -> Path:
    """Cache one live transcript plus its spend for offline replay."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "question_id": question_id,
        "provider": report.provider_name,
        "recorded_at": datetime.now(UTC).isoformat(),
        "input_tokens": report.total_input_tokens,
        "output_tokens": report.total_output_tokens,
        "transcript": transcript.model_dump(mode="json"),
    }
    path = cached_transcript_path(question_id, cache_dir)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_cached_transcript(
    question_id: str, cache_dir: Path = CACHE_DIR
) -> RecordedTranscript | None:
    """Load a cached live transcript, or None when absent/invalid."""
    path = cached_transcript_path(question_id, cache_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return RecordedTranscript.model_validate(payload["transcript"])
    except (ValueError, KeyError):
        return None


def _citation_matches(expected: dict[str, Any], valid: tuple[Any, ...]) -> bool:
    for citation in valid:
        data = citation.model_dump(mode="json")
        if all(data.get(key) == value for key, value in expected.items()):
            return True
    return False


def _replay_tool_results(
    transcript: RecordedTranscript, context: CopilotContext
) -> list[dict[str, Any]]:
    """Re-execute recorded tool calls deterministically (read-only)."""
    results: list[dict[str, Any]] = []
    for turn in transcript.turns:
        for call in turn.tool_calls:
            results.append(execute_tool(context, call.name, call.arguments))
    return results


def score_question(
    question: EvalQuestion,
    transcript: RecordedTranscript,
    response_reply: str,
    response_proposal_node: str | None,
    response_proposal_config: dict[str, Any],
    context: CopilotContext,
) -> QuestionResult:
    """Score one answered question against its expectations."""
    notes: list[str] = []
    final_answer = CopilotAnswer.model_validate_json(transcript.turns[-1].content)
    tool_results = _replay_tool_results(transcript, make_eval_context())
    citation_report = validate_citations(final_answer, tool_results, context)

    matched = 0
    for expected in question.expected.citations:
        if _citation_matches(expected, citation_report.valid):
            matched += 1
        else:
            notes.append(f"missing citation {expected}")

    proposal_ok = True
    if question.expected.proposal is not None:
        wanted = question.expected.proposal
        if response_proposal_node != wanted.node_id:
            proposal_ok = False
            notes.append("proposal node mismatch")
        elif not all(
            response_proposal_config.get(key) == value for key, value in wanted.config.items()
        ):
            proposal_ok = False
            notes.append("proposal config mismatch")
    elif response_proposal_node is not None:
        proposal_ok = False
        notes.append("unexpected proposal")

    assumed_ok = True
    if question.expected.assumed and not final_answer.assumed:
        assumed_ok = False
        notes.append("expected an assumed answer")

    clean_reply = "could not be verified" not in response_reply
    clean_reply = clean_reply and "Unverified draft" not in response_reply
    if not clean_reply:
        notes.append("reply carries an unverified marker")

    lowered_reply = response_reply.lower()
    reply_ok = True
    for snippet in question.expected.reply_contains:
        if snippet.lower() not in lowered_reply:
            reply_ok = False
            notes.append(f"reply is missing {snippet!r}")

    passed = (
        matched == len(question.expected.citations)
        and proposal_ok
        and assumed_ok
        and clean_reply
        and reply_ok
    )
    return QuestionResult(
        id=question.id,
        category=question.category,
        passed=passed,
        expected_citations=len(question.expected.citations),
        matched_citations=matched,
        proposal_ok=proposal_ok,
        assumed_ok=assumed_ok,
        notes=tuple(notes),
    )


async def _answer_one(
    question: EvalQuestion,
    transcript: RecordedTranscript,
    *,
    provider: CopilotProvider | None = None,
) -> tuple[QuestionResult, CopilotRunReport, bool]:
    context = make_eval_context()
    if question.selected_node_id is not None:
        context.selected_node_id = question.selected_node_id
    before = context.graph.model_dump_json()
    report = CopilotRunReport(provider_name="scripted")
    active_provider: CopilotProvider = (
        provider if provider is not None else ScriptedCopilotProvider(transcript)
    )
    response = await answer_with_llm(question.message, context, active_provider, report=report)
    mutated = context.graph.model_dump_json() != before or bool(context.write_log)
    result = score_question(
        question,
        transcript,
        response.reply,
        response.proposal.node_id if response.proposal else None,
        dict(response.proposal.config) if response.proposal else {},
        context,
    )
    return (
        result.model_copy(
            update={
                "input_tokens": report.total_input_tokens,
                "output_tokens": report.total_output_tokens,
            }
        ),
        report,
        mutated,
    )


def run_offline_eval(
    questions: list[EvalQuestion] | None = None,
    *,
    prefer_live: bool = False,
    cache_dir: Path = CACHE_DIR,
) -> EvalReport:
    """Replay the eval set offline and score citation accuracy.

    When ``prefer_live`` is set, cached live transcripts replace the
    authored scripts wherever they exist.
    """
    active = questions if questions is not None else load_questions()

    async def run_all() -> list[tuple[QuestionResult, CopilotRunReport, bool]]:
        outcomes: list[tuple[QuestionResult, CopilotRunReport, bool]] = []
        for question in active:
            transcript = script_to_transcript(question.script)
            if prefer_live:
                cached = load_cached_transcript(question.id, cache_dir)
                if cached is not None:
                    transcript = cached
            outcomes.append(await _answer_one(question, transcript))
        return outcomes

    outcomes = asyncio.run(run_all())

    results = tuple(result for result, _, _ in outcomes)
    expected_total = sum(r.expected_citations for r in results)
    matched_total = sum(r.matched_citations for r in results)
    return EvalReport(
        total=len(results),
        passed=sum(1 for r in results if r.passed),
        citation_accuracy=(sum(1 for r in results if r.passed) / len(results) if results else 0.0),
        citation_recall=(matched_total / expected_total if expected_total else 1.0),
        writes_detected=any(mutated for _, _, mutated in outcomes),
        input_tokens=sum(r.input_tokens for r in results),
        output_tokens=sum(r.output_tokens for r in results),
        results=results,
    )


async def run_live_subset(
    question_ids: list[str],
    provider_factory: Callable[[], CopilotProvider],
    *,
    questions: list[EvalQuestion] | None = None,
    cache_dir: Path = CACHE_DIR,
) -> EvalReport:
    """Answer a small live subset and cache every transcript.

    Each answer is scored like the offline run; the transcripts land
    in ``cache_dir`` for free offline replay afterwards.
    """
    active = [q for q in (questions or load_questions()) if q.id in set(question_ids)]
    missing = set(question_ids) - {q.id for q in active}
    if missing:
        raise ValueError(f"Unknown eval question ids: {sorted(missing)}")

    results: list[QuestionResult] = []
    writes = False
    for question in active:
        context = make_eval_context()
        if question.selected_node_id is not None:
            context.selected_node_id = question.selected_node_id
        before = context.graph.model_dump_json()
        report = CopilotRunReport(provider_name="live")
        response = await answer_with_llm(
            question.message, context, provider_factory(), report=report
        )
        writes = writes or context.graph.model_dump_json() != before
        transcript = RecordedTranscript(turns=tuple(report.turns))
        save_live_transcript(question.id, transcript, report, cache_dir)
        scored = score_question(
            question,
            transcript,
            response.reply,
            response.proposal.node_id if response.proposal else None,
            dict(response.proposal.config) if response.proposal else {},
            context,
        )
        results.append(
            scored.model_copy(
                update={
                    "input_tokens": report.total_input_tokens,
                    "output_tokens": report.total_output_tokens,
                }
            )
        )
    expected_total = sum(r.expected_citations for r in results)
    matched_total = sum(r.matched_citations for r in results)
    return EvalReport(
        total=len(results),
        passed=sum(1 for r in results if r.passed),
        citation_accuracy=(sum(1 for r in results if r.passed) / len(results) if results else 0.0),
        citation_recall=(matched_total / expected_total if expected_total else 1.0),
        writes_detected=writes,
        input_tokens=sum(r.input_tokens for r in results),
        output_tokens=sum(r.output_tokens for r in results),
        results=tuple(results),
    )


def write_results(report: EvalReport, path: Path = RESULTS_PATH) -> Path:
    """Persist one eval report for the checkpoint record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path
