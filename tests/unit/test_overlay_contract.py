"""Unit tests for the measured-overlay channel contract."""

from bizora.contracts.overlay import EMPTY_OVERLAY, MeasuredOverlay, OverlayValue


def test_empty_overlay_by_default() -> None:
    """A fresh channel carries no run and no values."""
    overlay = MeasuredOverlay()

    assert overlay.is_empty
    assert overlay.run_id is None
    assert EMPTY_OVERLAY.is_empty


def test_overlay_round_trips_node_and_edge_values() -> None:
    """Values keyed by node and edge id survive serialization."""
    overlay = MeasuredOverlay(
        run_id="run-1",
        nodes={"sense": (OverlayValue(signal="bitline_mv", value=42.5, unit="mV"),)},
        edges={"e1": (OverlayValue(signal="current_ua", value=1.2),)},
    )

    assert not overlay.is_empty
    assert overlay.nodes["sense"][0].signal == "bitline_mv"
    assert overlay.edges["e1"][0].value == 1.2
    assert overlay.edges["e1"][0].unit is None
    assert MeasuredOverlay.model_validate(overlay.model_dump()) == overlay
