"""Tests for the electronics electrical preflight rules.

Each rule reads generic config keys (voltages, currents, flags) through
data tables; fixtures use ordinary small circuits and the assertions pin
severities, so a regression cannot silently soften a block to a warn.
"""

from bizora.contracts.graph import (
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.contracts.packs import PackPreflightSeverity
from bizora.packs.electronics.preflight import (
    RULE_IDS,
    RULE_MISSING_PULLUP,
    RULE_PIN_COMPATIBILITY,
    RULE_POWER_BUDGET,
    RULE_VOLTAGE_LEVELS,
    preflight_graph,
)


def make_node(node_id: str, label: str, **config: object) -> GraphNode:
    """Build one component node with the given config data."""
    return GraphNode(id=node_id, kind=NodeKind.COMPONENT, label=label, config=dict(config))


def make_graph(*nodes: GraphNode) -> MethodologyGraph:
    """Build a methodology graph from component nodes."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Preflight fixture",
        nodes=tuple(nodes),
        created_by="tester",
    )


def supply(nets: list[str] | None = None, **overrides: object) -> GraphNode:
    """Build a 5 V rail source node."""
    config: dict[str, object] = {
        "spice_kind": "voltage-source",
        "refdes": "V1",
        "nets": nets or ["vcc", "0"],
        "voltage_v": 5,
    }
    config.update(overrides)
    return make_node("v1", "Supply", **config)


def test_clean_divider_reports_no_findings() -> None:
    """A consistent divider with a budget passes every rule."""
    graph = make_graph(
        supply(),
        make_node(
            "r1",
            "Resistor",
            spice_kind="resistor",
            refdes="R1",
            nets=["vcc", "out"],
            resistance_ohm="1k",
            power_mw=6.25,
        ),
        make_node(
            "r2",
            "Resistor",
            spice_kind="resistor",
            refdes="R2",
            nets=["out", "0"],
            resistance_ohm="1k",
            power_mw=6.25,
            power_budget_mw=100,
        ),
    )

    assert preflight_graph(graph) == ()


def test_pin_mismatch_blocks() -> None:
    """Three nets on a two-terminal element is a blocking finding."""
    graph = make_graph(
        make_node(
            "r1",
            "Resistor",
            spice_kind="resistor",
            refdes="R1",
            nets=["a", "b", "c"],
            resistance_ohm="1k",
        ),
    )

    findings = preflight_graph(graph)

    assert len(findings) == 1
    assert findings[0].rule_id == RULE_PIN_COMPATIBILITY
    assert findings[0].severity is PackPreflightSeverity.BLOCK


def test_rail_over_max_blocks() -> None:
    """A rail above a part's stated maximum is a blocking finding."""
    graph = make_graph(
        supply(nets=["vcc", "0"]),
        make_node(
            "u1",
            "Regulator load",
            spice_kind="resistor",
            refdes="R1",
            nets=["vcc", "0"],
            resistance_ohm="1k",
            max_voltage_v=3.3,
        ),
    )

    findings = preflight_graph(graph)

    blocks = [item for item in findings if item.rule_id == RULE_VOLTAGE_LEVELS]
    assert len(blocks) == 1
    assert blocks[0].severity is PackPreflightSeverity.BLOCK
    assert "exceeds max" in blocks[0].message


def test_unmatched_supply_warns() -> None:
    """A supply with no rail at its voltage warns instead of blocking."""
    graph = make_graph(
        supply(),
        make_node(
            "u1",
            "Load",
            spice_kind="resistor",
            refdes="R1",
            nets=["v33", "0"],
            resistance_ohm="1k",
            supply_v=3.3,
        ),
    )

    findings = preflight_graph(graph)

    warns = [
        item
        for item in findings
        if item.rule_id == RULE_VOLTAGE_LEVELS and item.severity is PackPreflightSeverity.WARN
    ]
    assert len(warns) == 1
    assert "matches no rail" in warns[0].message


def test_logic_level_conflict_blocks() -> None:
    """Two logic levels shorted on one net is a blocking finding."""
    graph = make_graph(
        make_node(
            "u1",
            "Driver",
            spice_kind="subcircuit",
            refdes="X1",
            nets=["sig", "0"],
            subckt="DRV",
            logic_level_v=3.3,
        ),
        make_node(
            "u2",
            "Receiver",
            spice_kind="subcircuit",
            refdes="X2",
            nets=["sig", "0"],
            subckt="RCV",
            logic_level_v=1.8,
        ),
    )

    findings = preflight_graph(graph)

    assert any(
        item.rule_id == RULE_VOLTAGE_LEVELS
        and item.severity is PackPreflightSeverity.BLOCK
        and "conflicting logic levels" in item.message
        for item in findings
    )


def test_missing_pullup_warns_and_pullup_clears() -> None:
    """An unserved pull-up flag warns; a resistor to the rail clears it."""
    flagged = make_node(
        "u1",
        "Open-drain output",
        spice_kind="subcircuit",
        refdes="X1",
        nets=["sda", "0"],
        subckt="OD",
        requires_pullup=True,
    )
    floating = make_graph(supply(), flagged)
    pulled = make_graph(
        supply(),
        flagged,
        make_node(
            "r1",
            "Resistor",
            spice_kind="resistor",
            refdes="R1",
            nets=["sda", "vcc"],
            resistance_ohm="4.7k",
        ),
    )

    assert any(item.rule_id == RULE_MISSING_PULLUP for item in preflight_graph(floating))
    assert all(item.rule_id != RULE_MISSING_PULLUP for item in preflight_graph(pulled))


def test_stated_power_over_budget_blocks() -> None:
    """Stated draw above the stated budget is a blocking finding."""
    graph = make_graph(
        supply(),
        make_node(
            "r1",
            "Heater",
            spice_kind="resistor",
            refdes="R1",
            nets=["vcc", "0"],
            resistance_ohm="10",
            power_mw=2500,
            power_budget_mw=1000,
        ),
    )

    findings = preflight_graph(graph)

    assert any(
        item.rule_id == RULE_POWER_BUDGET
        and item.severity is PackPreflightSeverity.BLOCK
        and "stated draw" in item.message
        for item in findings
    )


def test_estimated_power_over_budget_warns() -> None:
    """V*I-estimated draw above budget warns rather than blocks."""
    graph = make_graph(
        supply(),
        make_node(
            "r1",
            "Load",
            spice_kind="resistor",
            refdes="R1",
            nets=["vcc", "0"],
            resistance_ohm="10",
            supply_v=5,
            current_ma=500,
            power_budget_mw=1000,
        ),
    )

    findings = preflight_graph(graph)

    assert any(
        item.rule_id == RULE_POWER_BUDGET
        and item.severity is PackPreflightSeverity.WARN
        and "estimated draw" in item.message
        for item in findings
    )


def test_rail_overcurrent_blocks() -> None:
    """Load current above the source limit is a blocking finding."""
    graph = make_graph(
        supply(max_current_ma=100),
        make_node(
            "r1",
            "Load",
            spice_kind="resistor",
            refdes="R1",
            nets=["vcc", "0"],
            resistance_ohm="10",
            current_ma=500,
        ),
    )

    findings = preflight_graph(graph)

    assert any(
        item.rule_id == RULE_POWER_BUDGET
        and item.severity is PackPreflightSeverity.BLOCK
        and "exceeds source limit" in item.message
        for item in findings
    )


def test_rule_ids_are_stable_and_sorted() -> None:
    """Rule ids stay fixed and findings sort deterministically."""
    graph = make_graph(
        make_node(
            "r1",
            "Resistor",
            spice_kind="resistor",
            refdes="R1",
            nets=["a", "b", "c"],
            resistance_ohm="1k",
            power_mw=5000,
            power_budget_mw=10,
        ),
    )

    findings = preflight_graph(graph)

    assert RULE_IDS == (
        "electronics_pin_compatibility",
        "electronics_voltage_levels",
        "electronics_missing_pullup",
        "electronics_power_budget",
    )
    assert [item.rule_id for item in findings] == sorted(item.rule_id for item in findings)
