import pytest
from pydantic import ValidationError

from bizora.contracts.evidence import EvidenceRef, EvidenceStatus


def test_evidence_requires_a_source_locator() -> None:
    with pytest.raises(ValidationError, match="at least one locator"):
        EvidenceRef(source_id="paper-1")


def test_evidence_bbox_must_be_normalized_and_ordered() -> None:
    with pytest.raises(ValidationError, match="bbox must be normalized"):
        EvidenceRef(source_id="paper-1", page=2, bbox=(0.8, 0.1, 0.4, 0.9))


def test_valid_evidence_is_immutable() -> None:
    evidence = EvidenceRef(
        source_id="paper-1", page=3, quote="We use a vision transformer.", status=EvidenceStatus.SUPPORTED
    )
    assert evidence.page == 3
    with pytest.raises(ValidationError):
        evidence.page = 4  # type: ignore[misc]
