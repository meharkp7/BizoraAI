"""Tests for figure segmentation: SAM seam, cache, and endpoints (no weights)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bizora.api import get_segmentation_provider
from bizora.contracts.figures import FigureRecord, FigureSegment
from bizora.core.segmentation import (
    Sam3SegmentationProvider,
    SegmentationProvider,
    clean_prompts,
    load_cached_segments,
    save_cached_segments,
    segment_cache_key,
    simplify_polygon,
)
from bizora.db.base import Base
from bizora.db.repository import save_paper_figure
from bizora.db.session import get_db_session
from bizora.main import app


class ScriptedSegmentationProvider:
    """Fake backend: scripted outlines, availability on a switch."""

    name = "scripted"

    def __init__(
        self,
        segments: tuple[FigureSegment, ...] = (),
        *,
        available: bool = True,
        reason: str | None = None,
    ) -> None:
        self._segments = segments
        self._available = available
        self._reason = reason
        self.calls: list[tuple[bytes, tuple[str, ...]]] = []

    def available(self) -> tuple[bool, str | None]:
        return self._available, self._reason

    def segment(
        self, image_bytes: bytes, prompts: tuple[str, ...]
    ) -> tuple[FigureSegment, ...]:
        self.calls.append((image_bytes, prompts))
        return self._segments


def make_segment(
    segment_id: str = "nmos-1-1", label: str = "nmos transistor"
) -> FigureSegment:
    return FigureSegment(
        segment_id=segment_id,
        label=label,
        bbox=(0.1, 0.2, 0.3, 0.4),
        polygon=((0.1, 0.2), (0.4, 0.2), (0.4, 0.6), (0.1, 0.6)),
        score=0.9,
    )


@pytest.fixture
def segmenter() -> ScriptedSegmentationProvider:
    return ScriptedSegmentationProvider(segments=(make_segment(),))


@pytest.fixture
def client(
    segmenter: ScriptedSegmentationProvider,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setenv("BIZORA_CACHE_DIR", str(tmp_path))
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_db_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    def seed() -> None:
        with Session(engine) as session:
            save_paper_figure(
                session,
                project_id="project-1",
                graph_id="graph-1",
                source_id="paper-1",
                created_by="test",
                figure=FigureRecord(figure_id="fig1", page=3),
                regions=(),
                image_bytes=b"fake-image-bytes",
            )
            session.commit()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_segmentation_provider] = lambda: segmenter
    seed()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_segmentation_provider, None)


def test_clean_prompts_trims_dedupes_and_caps() -> None:
    assert clean_prompts(("  nmos ", "", "nmos", "x" * 100)) == (
        "nmos",
        "x" * 64,
    )
    assert clean_prompts(tuple(f"p{i}" for i in range(20))) == tuple(
        f"p{i}" for i in range(12)
    )


def test_simplify_polygon_stride_samples_long_rings() -> None:
    ring = [(i / 200, 0.5) for i in range(200)]
    simplified = simplify_polygon(ring, limit=16)
    assert len(simplified) == 16
    assert simplified[0] == ring[0]


def test_sam3_provider_reports_unavailable_without_setup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("BIZORA_SAM3_WEIGHTS", raising=False)
    provider = Sam3SegmentationProvider()
    available, reason = provider.available()
    # Either ultralytics or the weights path is missing in this env;
    # both are honest setup reasons, never an exception.
    assert available is False
    assert reason is not None and "SAM_SETUP.md" in reason


def test_segments_unknown_figure_is_404(client: TestClient) -> None:
    response = client.get(
        "/api/v1/graphs/project-1/graph-1/figures/nope/segments?prompts=nmos"
    )
    assert response.status_code == 404
    response = client.post(
        "/api/v1/graphs/project-1/graph-1/figures/nope/segments",
        json={"prompts": ["nmos"]},
    )
    assert response.status_code == 404


def test_segments_post_runs_once_then_serves_cache(
    client: TestClient, segmenter: ScriptedSegmentationProvider
) -> None:
    first = client.post(
        "/api/v1/graphs/project-1/graph-1/figures/fig1/segments",
        json={"prompts": ["nmos transistor"]},
    )
    assert first.status_code == 200
    body = first.json()
    assert body["available"] is True
    assert body["cached"] is False
    assert body["elapsed_ms"] is not None
    assert [segment["segment_id"] for segment in body["segments"]] == ["nmos-1-1"]
    assert len(segmenter.calls) == 1

    second = client.post(
        "/api/v1/graphs/project-1/graph-1/figures/fig1/segments",
        json={"prompts": ["nmos transistor"]},
    )
    assert second.status_code == 200
    assert second.json()["cached"] is True
    assert len(segmenter.calls) == 1

    peek = client.get(
        "/api/v1/graphs/project-1/graph-1/figures/fig1/segments"
        "?prompts=nmos%20transistor"
    )
    assert peek.status_code == 200
    assert peek.json()["cached"] is True
    assert len(segmenter.calls) == 1


def test_segments_post_unavailable_is_503(
    client: TestClient, segmenter: ScriptedSegmentationProvider
) -> None:
    segmenter._available = False
    segmenter._reason = "Set BIZORA_SAM3_WEIGHTS. See docs/SAM_SETUP.md."
    response = client.post(
        "/api/v1/graphs/project-1/graph-1/figures/fig1/segments",
        json={"prompts": ["nmos"]},
    )
    assert response.status_code == 503
    assert "SAM_SETUP.md" in response.json()["detail"]

    peek = client.get(
        "/api/v1/graphs/project-1/graph-1/figures/fig1/segments?prompts=nmos"
    )
    assert peek.status_code == 200
    assert peek.json()["available"] is False


def test_segments_reject_blank_prompts(client: TestClient) -> None:
    response = client.post(
        "/api/v1/graphs/project-1/graph-1/figures/fig1/segments",
        json={"prompts": ["   "]},
    )
    assert response.status_code == 422
    peek = client.get(
        "/api/v1/graphs/project-1/graph-1/figures/fig1/segments?prompts=%20"
    )
    assert peek.status_code == 422


def test_segment_cache_roundtrip_and_version_guard(tmp_path: Path) -> None:
    import json
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        key = segment_cache_key("ab" * 32, ("nmos",))
        assert load_cached_segments(key) is None
        save_cached_segments(key, (make_segment(),))
        cached = load_cached_segments(key)
        assert cached is not None and cached[0].segment_id == "nmos-1-1"

        stale = segment_cache_key("cd" * 32, ("nmos",))
        path = tmp_path / "bizora" / "segments" / f"{stale}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 999, "segments": []}))
        assert load_cached_segments(stale) is None
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_segmentation_provider_protocol_matches_script() -> None:
    provider: SegmentationProvider = ScriptedSegmentationProvider()
    assert provider.name == "scripted"
    assert provider.available() == (True, None)
