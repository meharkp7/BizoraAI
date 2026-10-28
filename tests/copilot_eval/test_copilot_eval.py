"""R9 copilot evaluation: 30 questions, citation accuracy, zero writes.

Runs fully offline with the recorded fixtures in ``questions.json``
(zero API spend). Live-model citation accuracy stays unverified
until the owner runs :func:`run_live_subset` with a real provider;
cached live transcripts then replay here via ``prefer_live``.
"""

from tests.copilot_eval.harness import (
    load_questions,
    run_offline_eval,
    write_results,
)

CITATION_TARGET = 0.85


def test_eval_set_has_thirty_questions() -> None:
    questions = load_questions()

    assert len(questions) == 30
    categories = {question.category for question in questions}
    assert {"evidence", "runs", "library", "preflight", "proposal", "diff"} <= categories


def test_offline_citation_accuracy_meets_r9() -> None:
    report = run_offline_eval()
    write_results(report)

    failures = [result for result in report.results if not result.passed]
    assert report.accuracy >= CITATION_TARGET, (
        f"citation accuracy {report.accuracy:.2f} below {CITATION_TARGET}; "
        f"failures: {[(item.id, item.notes) for item in failures]}"
    )


def test_eval_detects_zero_unapproved_writes() -> None:
    report = run_offline_eval()

    assert report.writes_detected is False
    proposals = [result for result in report.results if result.id in ("q24", "q25", "q26", "q27")]
    assert all(result.proposal_ok for result in proposals)


def test_eval_spend_is_zero_offline() -> None:
    report = run_offline_eval()

    assert report.input_tokens == 0
    assert report.output_tokens == 0
