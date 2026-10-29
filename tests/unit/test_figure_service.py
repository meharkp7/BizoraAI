"""Tests for the paper-figure overlay pipeline (stub vision provider)."""

import asyncio
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from tests.unit.test_figure_ingest import make_fake_pdf_with_images

from bizora.contracts.figures import (
    FigureDescription,
    FigureDescriptionList,
    FigureDescriptionRequest,
    FigureDescriptionResult,
    FigureRegionList,
    FigureRegionProposal,
    FigureSet,
    RegionLocalizationRequest,
    RegionLocalizationResult,
    build_figure_set,
    build_region_set,
)
from bizora.contracts.graph import GraphNode, MethodologyGraph, NodeKind
from bizora.core.figure_service import ingest_paper_figures, list_graph_figures
from bizora.core.pdf import extract_page_texts
from bizora.db.base import Base
from bizora.db.repository import get_paper_figure


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def make_graph() -> MethodologyGraph:
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        parent_version=None,
        title="Cell paper",
        source_ids=("paper-1",),
        nodes=(
            GraphNode(id="bitcell", kind=NodeKind.COMPONENT, label="6T SRAM bitcell"),
            GraphNode(id="sense", kind=NodeKind.COMPONENT, label="Sense amplifier"),
        ),
        edges=(),
        created_by="researcher-1",
    )


class StubVisionProvider:
    """Deterministic stand-in for the Muse vision calls."""

    def __init__(self) -> None:
        self.describe_calls = 0
        self.localize_calls = 0

    async def describe_figures(
        self, request: FigureDescriptionRequest
    ) -> FigureDescriptionResult:
        self.describe_calls += 1
        figure_set, warnings = build_figure_set(
            request,
            FigureDescriptionList(
                figures=tuple(
                    FigureDescription(
                        figure_id=figure.figure_id,
                        label=f"Figure {position + 1}",
                        kind="diagram",
                        confidence=0.9,
                    )
                    for position, figure in enumerate(request.figures)
                )
            ),
        )
        assert isinstance(figure_set, FigureSet)
        return FigureDescriptionResult(
            draft_figures=figure_set,
            provider_name="stub",
            model_name="stub-vision",
            warnings=warnings,
            usage=None,
        )

    async def localize_regions(
        self, request: RegionLocalizationRequest
    ) -> RegionLocalizationResult:
        self.localize_calls += 1
        region_set, warnings = build_region_set(
            request,
            FigureRegionList(
                regions=tuple(
                    FigureRegionProposal(
                        figure_id=figure.figure_id,
                        bbox=(0.1, 0.1, 0.4, 0.4),
                        node_id="bitcell",
                        label="bitcell block",
                        confidence=0.7,
                    )
                    for figure in request.figures
                )
            ),
        )
        return RegionLocalizationResult(
            draft_regions=region_set,
            provider_name="stub",
            model_name="stub-vision",
            warnings=warnings,
            usage=None,
        )


def test_ingest_persists_figures_with_regions(db_session: Session) -> None:
    async def run_test() -> None:
        pdf = make_fake_pdf_with_images(2, text="See Figure 1 and Figure 2.")
        report = await ingest_paper_figures(
            db_session,
            graph=make_graph(),
            pdf_bytes=pdf,
            page_texts=extract_page_texts(pdf),
            source_id="paper-1",
            created_by="researcher-1",
            provider=StubVisionProvider(),
        )
        assert len(report.figures) == 2
        assert report.warnings == ()
        assert report.truncated is False
        first = report.figures[0]
        assert first.label == "Figure 1"
        assert first.page == 1
        assert len(first.regions) == 1
        assert first.regions[0].node_id == "bitcell"
        assert first.regions[0].region_id == f"{first.figure_id}-r1"

        listed = list_graph_figures(
            db_session, project_id="project-1", graph_id="graph-1"
        )
        assert [figure.figure_id for figure in listed] == [
            figure.figure_id for figure in report.figures
        ]
        stored = get_paper_figure(
            db_session,
            project_id="project-1",
            graph_id="graph-1",
            figure_id=first.figure_id,
        )
        assert stored is not None
        assert len(stored.image_bytes) > 0
        assert stored.mime_type == "image/png"

    asyncio.run(run_test())


def test_reingest_replaces_previous_figures(db_session: Session) -> None:
    async def run_test() -> None:
        provider = StubVisionProvider()
        for _ in range(2):
            pdf = make_fake_pdf_with_images(2, text="See Figure 1 and Figure 2.")
            report = await ingest_paper_figures(
                db_session,
                graph=make_graph(),
                pdf_bytes=pdf,
                page_texts=extract_page_texts(pdf),
                source_id="paper-1",
                created_by="researcher-1",
                provider=provider,
            )
            assert len(report.figures) == 2
        listed = list_graph_figures(
            db_session, project_id="project-1", graph_id="graph-1"
        )
        assert len(listed) == 2
        assert provider.describe_calls == 2

    asyncio.run(run_test())


def test_ingest_without_images_yields_empty_report(db_session: Session) -> None:
    async def run_test() -> None:
        pdf = make_fake_pdf_with_images(0, text="No figures here.")
        provider = StubVisionProvider()
        report = await ingest_paper_figures(
            db_session,
            graph=make_graph(),
            pdf_bytes=pdf,
            page_texts=extract_page_texts(pdf),
            source_id="paper-1",
            created_by="researcher-1",
            provider=provider,
        )
        assert report.figures == ()
        assert provider.describe_calls == 0
        assert provider.localize_calls == 0

    asyncio.run(run_test())
