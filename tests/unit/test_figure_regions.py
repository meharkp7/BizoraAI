"""Tests for figure-region localization contracts and merging."""

import pytest
from pydantic import ValidationError

from bizora.contracts.figures import (
    FigureAttachment,
    FigureRegion,
    FigureRegionList,
    FigureRegionProposal,
    NodeHint,
    RegionLocalizationRequest,
    build_region_set,
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


def make_request() -> RegionLocalizationRequest:
    return RegionLocalizationRequest(
        project_id="project-1",
        graph_id="graph-1",
        source_id="paper-1",
        created_by="test-user",
        figures=(make_attachment("fig-1"),),
        nodes=(
            NodeHint(node_id="bitcell", label="6T SRAM bitcell", kind="component"),
            NodeHint(node_id="sense", label="Sense amplifier", kind="component"),
        ),
    )


def test_build_region_set_links_known_nodes() -> None:
    region_set, warnings = build_region_set(
        make_request(),
        FigureRegionList(
            regions=(
                FigureRegionProposal(
                    figure_id="fig-1",
                    bbox=(0.1, 0.2, 0.3, 0.25),
                    node_id="bitcell",
                    label="bitcell array",
                    confidence=0.8,
                ),
                FigureRegionProposal(
                    figure_id="fig-1",
                    bbox=(0.5, 0.5, 0.2, 0.2),
                    node_id=None,
                    label="legend",
                    confidence=0.4,
                ),
            )
        ),
    )

    assert warnings == ()
    assert region_set.project_id == "project-1"
    first, second = region_set.regions
    assert isinstance(first, FigureRegion)
    assert first.region_id == "fig-1-r1"
    assert first.node_id == "bitcell"
    assert first.bbox == (0.1, 0.2, 0.3, 0.25)
    assert second.region_id == "fig-1-r2"
    assert second.node_id is None


def test_build_region_set_unlinks_unknown_nodes_with_warning() -> None:
    region_set, warnings = build_region_set(
        make_request(),
        FigureRegionList(
            regions=(
                FigureRegionProposal(
                    figure_id="fig-1",
                    bbox=(0.1, 0.2, 0.3, 0.25),
                    node_id="ghost-node",
                    label="mystery block",
                ),
            )
        ),
    )

    assert len(warnings) == 1
    assert "ghost-node" in warnings[0]
    assert region_set.regions[0].node_id is None
    assert region_set.regions[0].label == "mystery block"


def test_build_region_set_skips_unknown_figures() -> None:
    region_set, warnings = build_region_set(
        make_request(),
        FigureRegionList(
            regions=(
                FigureRegionProposal(
                    figure_id="fig-9",
                    bbox=(0.1, 0.1, 0.2, 0.2),
                    node_id=None,
                    label="elsewhere",
                ),
            )
        ),
    )

    assert region_set.regions == ()
    assert len(warnings) == 1
    assert "fig-9" in warnings[0]


def test_build_region_set_caps_regions_per_figure() -> None:
    proposals = tuple(
        FigureRegionProposal(
            figure_id="fig-1",
            bbox=(0.01 * (i % 9), 0.01 * (i % 9), 0.05, 0.05),
            node_id=None,
            label=f"cell {i}",
        )
        for i in range(45)
    )
    region_set, warnings = build_region_set(
        make_request(), FigureRegionList(regions=proposals)
    )

    assert len(region_set.regions) == 40
    assert len(warnings) == 5
    assert region_set.regions[0].region_id == "fig-1-r1"
    assert region_set.regions[-1].region_id == "fig-1-r40"


def test_region_proposal_rejects_malformed_bboxes() -> None:
    with pytest.raises(ValidationError):
        FigureRegionProposal(
            figure_id="fig-1",
            bbox=(0.1, 0.1, 0.2),  # type: ignore[arg-type]
            node_id=None,
            label="short box",
        )
    with pytest.raises(ValidationError):
        FigureRegionProposal(
            figure_id="fig-1",
            bbox=(1.5, 0.1, 0.2, 0.2),
            node_id=None,
            label="outside box",
        )
    with pytest.raises(ValidationError):
        FigureRegionProposal(
            figure_id="fig-1",
            bbox=(0.9, 0.9, 0.5, 0.5),
            node_id=None,
            label="overflowing box",
        )
    with pytest.raises(ValidationError):
        FigureRegionProposal(
            figure_id="fig-1",
            bbox=(0.1, 0.1, 0.0, 0.2),
            node_id=None,
            label="flat box",
        )


def test_region_localization_request_bounds() -> None:
    with pytest.raises(ValidationError):
        RegionLocalizationRequest(
            project_id="project-1",
            graph_id="graph-1",
            source_id="paper-1",
            created_by="test-user",
            figures=(),
            nodes=(NodeHint(node_id="a", label="A", kind="component"),),
        )
    with pytest.raises(ValidationError):
        RegionLocalizationRequest(
            project_id="project-1",
            graph_id="graph-1",
            source_id="paper-1",
            created_by="test-user",
            figures=(make_attachment(),),
            nodes=(),
        )
