"""Tests for figure/diagram contracts and description merging."""

import pytest
from pydantic import ValidationError

from bizora.contracts.figures import (
    FigureAttachment,
    FigureDescription,
    FigureDescriptionList,
    FigureDescriptionRequest,
    FigureSet,
    build_figure_set,
)

FAKE_IMAGE_BYTES = b"\x89PNG-fake-figure-bytes"


def make_attachment(figure_id: str = "fig-1") -> FigureAttachment:
    return FigureAttachment(
        figure_id=figure_id,
        page=2,
        image_bytes=FAKE_IMAGE_BYTES,
        mime_type="image/png",
        surrounding_text="Figure 1 shows the device.",
        label_hint="Figure 1",
    )


def make_request() -> FigureDescriptionRequest:
    return FigureDescriptionRequest(
        project_id="project-1",
        graph_id="graph-1",
        source_id="paper-1",
        created_by="test-user",
        figures=(make_attachment("fig-1"), make_attachment("fig-2")),
    )


def test_build_figure_set_merges_trusted_metadata() -> None:
    figure_set, warnings = build_figure_set(
        make_request(),
        FigureDescriptionList(
            figures=(
                FigureDescription(
                    figure_id="fig-1",
                    label="Figure 1",
                    caption="The device.",
                    kind="photo",
                    confidence=0.9,
                ),
                FigureDescription(figure_id="fig-2", kind="diagram"),
            )
        ),
    )

    assert warnings == ()
    assert figure_set.project_id == "project-1"
    first, second = figure_set.figures
    assert first.label == "Figure 1"
    assert first.page == 2
    assert first.mime_type == "image/png"
    assert first.byte_size == len(FAKE_IMAGE_BYTES)
    assert first.sha256 is not None and len(first.sha256) == 64
    assert first.context == "Figure 1 shows the device."
    assert second.kind.value == "diagram"
    assert second.label is None


def test_build_figure_set_warns_on_unknown_and_missing() -> None:
    figure_set, warnings = build_figure_set(
        make_request(),
        FigureDescriptionList(
            figures=(
                FigureDescription(figure_id="fig-1"),
                FigureDescription(figure_id="fig-ghost"),
                FigureDescription(figure_id="fig-1"),
            )
        ),
    )

    assert len(warnings) == 3
    assert any("fig-ghost" in warning for warning in warnings)
    assert any("Duplicate" in warning for warning in warnings)
    assert any("fig-2" in warning for warning in warnings)
    by_id = {figure.figure_id: figure for figure in figure_set.figures}
    assert by_id["fig-2"].kind.value == "unknown"
    assert by_id["fig-2"].label is None
    assert "fig-ghost" not in by_id


def test_figure_set_rejects_duplicate_ids() -> None:
    attachment = make_attachment("fig-1")
    with pytest.raises(ValidationError):
        FigureSet(
            project_id="project-1",
            graph_id="graph-1",
            source_id="paper-1",
            figures=(
                {
                    "figure_id": attachment.figure_id,
                    "page": attachment.page,
                },
                {
                    "figure_id": attachment.figure_id,
                    "page": attachment.page,
                },
            ),
        )


def test_attachment_rejects_non_image_mime() -> None:
    with pytest.raises(ValidationError):
        FigureAttachment(
            figure_id="fig-1",
            image_bytes=FAKE_IMAGE_BYTES,
            mime_type="application/pdf",
        )


def test_attachment_rejects_empty_bytes() -> None:
    with pytest.raises(ValidationError):
        FigureAttachment(
            figure_id="fig-1",
            image_bytes=b"",
            mime_type="image/png",
        )


def test_request_rejects_empty_figures() -> None:
    with pytest.raises(ValidationError):
        FigureDescriptionRequest(
            project_id="project-1",
            graph_id="graph-1",
            source_id="paper-1",
            created_by="test-user",
            figures=(),
        )


def test_build_figure_set_keeps_full_surrounding_text() -> None:
    """Attachments carry up to 4000 chars; records must accept them all."""
    request = FigureDescriptionRequest(
        project_id="project-1",
        graph_id="graph-1",
        source_id="paper-1",
        created_by="test-user",
        figures=(
            FigureAttachment(
                figure_id="fig-1",
                page=5,
                image_bytes=FAKE_IMAGE_BYTES,
                mime_type="image/jpeg",
                surrounding_text="x" * 4000,
            ),
        ),
    )
    figure_set, warnings = build_figure_set(
        request,
        FigureDescriptionList(
            figures=(FigureDescription(figure_id="fig-1", kind="plot"),)
        ),
    )

    assert warnings == ()
    assert figure_set.figures[0].context == "x" * 4000
