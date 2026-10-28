"""Electrical preflight rules over methodology graphs.

Four rule families, all data-driven (thresholds, config keys, and kinds
live in the tables below; the logic only interprets them):

- ``electronics_pin_compatibility`` (block): explicit config nets must
  match the element's terminal count from the netlist table.
- ``electronics_voltage_levels`` (block/warn): rails must exist for
  stated supplies, rails must not exceed stated maxima, and nets must
  not join conflicting logic levels.
- ``electronics_missing_pullup`` (warn): nodes flagging
  ``requires_pullup`` need a resistor from that net to a rail net.
- ``electronics_power_budget`` (block/warn): stated plus estimated
  draw must fit the stated budget and each rail's current limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bizora.contracts.graph import GraphNode, MethodologyGraph
from bizora.contracts.packs import (
    PackPreflightFinding,
    PackPreflightSeverity,
)
from bizora.packs.electronics.netlist import (
    ELEMENT_TABLE,
    KIND_KEY,
    NETS_KEY,
    ElementSpec,
    extract_netlist,
)

# ---------------------------------------------------------------------------
# Preflight data: rule ids, kinds, config keys, and tolerances.
# ---------------------------------------------------------------------------

RULE_PIN_COMPATIBILITY = "electronics_pin_compatibility"
RULE_VOLTAGE_LEVELS = "electronics_voltage_levels"
RULE_MISSING_PULLUP = "electronics_missing_pullup"
RULE_POWER_BUDGET = "electronics_power_budget"

RULE_IDS: tuple[str, ...] = (
    RULE_PIN_COMPATIBILITY,
    RULE_VOLTAGE_LEVELS,
    RULE_MISSING_PULLUP,
    RULE_POWER_BUDGET,
)

SOURCE_KINDS: tuple[str, ...] = ("voltage-source",)
RESISTOR_KINDS: tuple[str, ...] = ("resistor",)

SOURCE_VALUE_KEYS: tuple[str, ...] = ("voltage_v", "dc_v", "value")
SUPPLY_KEYS: tuple[str, ...] = ("supply_v", "rail_v", "vdd_v")
MAX_VOLTAGE_KEYS: tuple[str, ...] = ("max_voltage_v", "max_supply_v", "voltage_rating_v")
LOGIC_LEVEL_KEYS: tuple[str, ...] = ("logic_level_v", "io_voltage_v")
POWER_KEYS: tuple[str, ...] = ("power_mw", "power_dissipation_mw")
CURRENT_KEYS: tuple[str, ...] = ("current_ma", "supply_current_ma", "load_current_ma")
SOURCE_CURRENT_KEYS: tuple[str, ...] = ("max_current_ma", "current_limit_ma")
BUDGET_KEYS: tuple[str, ...] = ("power_budget_mw",)
PULLUP_KEYS: tuple[str, ...] = ("requires_pullup",)

VOLTAGE_TOLERANCE_V = 0.05
RAIL_TERMINAL_INDEX = 0


@dataclass(frozen=True)
class _Number:
    value: float
    estimated: bool


def _read_float(config: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        raw = config.get(key)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str):
            try:
                return float(raw.strip())
            except ValueError:
                continue
    return None


def _has_unparseable(
    config: dict[str, Any], keys: tuple[str, ...], *, exclude_bool: bool = True
) -> str | None:
    for key in keys:
        raw = config.get(key)
        if raw is None or (exclude_bool and isinstance(raw, bool)):
            continue
        if isinstance(raw, (int, float)):
            continue
        if isinstance(raw, str):
            try:
                float(raw.strip())
            except ValueError:
                return key
    return None


def _explicit_nets(node: GraphNode) -> tuple[str, ...] | None:
    value = node.config.get(NETS_KEY)
    if not isinstance(value, list):
        return None
    nets = [
        str(entry).strip()
        for entry in value
        if isinstance(entry, (str, int, float)) and not isinstance(entry, bool)
    ]
    return tuple(net for net in nets if net) or None


def _node_kind(node: GraphNode) -> tuple[str | None, ElementSpec | None]:
    raw = node.config.get(KIND_KEY)
    kind = raw if isinstance(raw, str) else None
    return kind, ELEMENT_TABLE.get(kind) if kind is not None else None


def _check_pins(graph: MethodologyGraph) -> list[PackPreflightFinding]:
    findings: list[PackPreflightFinding] = []
    for node in graph.nodes:
        kind, spec = _node_kind(node)
        if kind is None or spec is None or spec.directive or spec.terminals == 0:
            continue
        nets = _explicit_nets(node)
        if nets is None:
            continue  # implicit nets are repaired with warnings at extraction
        if len(nets) != spec.terminals:
            findings.append(
                PackPreflightFinding(
                    rule_id=RULE_PIN_COMPATIBILITY,
                    severity=PackPreflightSeverity.BLOCK,
                    message=(
                        f"node '{node.id}': {len(nets)} config nets for "
                        f"{spec.terminals} terminals "
                        f"({', '.join(spec.pin_order)}); fix the nets list"
                    ),
                )
            )
    return findings


@dataclass(frozen=True)
class _Rail:
    net: str
    volts: float
    node_id: str
    max_current_ma: float | None


def _collect_rails(graph: MethodologyGraph) -> tuple[tuple[_Rail, ...], list[str]]:
    rails: list[_Rail] = []
    bad: list[str] = []
    for node in graph.nodes:
        kind, _ = _node_kind(node)
        if kind not in SOURCE_KINDS:
            continue
        volts = _read_float(node.config, SOURCE_VALUE_KEYS)
        if volts is None:
            key = _has_unparseable(node.config, SOURCE_VALUE_KEYS)
            if key is not None:
                bad.append(f"node '{node.id}': unparseable voltage in '{key}'")
            continue
        nets = _explicit_nets(node)
        if nets is None or len(nets) <= RAIL_TERMINAL_INDEX:
            continue
        rails.append(
            _Rail(
                net=nets[RAIL_TERMINAL_INDEX],
                volts=volts,
                node_id=node.id,
                max_current_ma=_read_float(node.config, SOURCE_CURRENT_KEYS),
            )
        )
    return tuple(rails), bad


def _check_voltage(graph: MethodologyGraph) -> list[PackPreflightFinding]:
    findings: list[PackPreflightFinding] = []
    rails, bad = _collect_rails(graph)
    for message in bad:
        findings.append(
            PackPreflightFinding(
                rule_id=RULE_VOLTAGE_LEVELS,
                severity=PackPreflightSeverity.WARN,
                message=message,
            )
        )
    netlist = extract_netlist(graph)
    nets_by_node = {record.node_id: record.nets for record in netlist.records}
    rail_nets = {rail.net: rail for rail in rails}

    for node in graph.nodes:
        kind, spec = _node_kind(node)
        if kind is None or spec is None or spec.directive:
            continue
        supply = _read_float(node.config, SUPPLY_KEYS)
        if (
            supply is not None
            and rails
            and not any(abs(rail.volts - supply) <= VOLTAGE_TOLERANCE_V for rail in rails)
        ):
            findings.append(
                PackPreflightFinding(
                    rule_id=RULE_VOLTAGE_LEVELS,
                    severity=PackPreflightSeverity.WARN,
                    message=(f"node '{node.id}': supply {supply:g} V matches no rail voltage"),
                )
            )
        maximum = _read_float(node.config, MAX_VOLTAGE_KEYS)
        if maximum is not None:
            for net in nets_by_node.get(node.id, ()):
                rail = rail_nets.get(net)
                if rail is not None and rail.volts > maximum + VOLTAGE_TOLERANCE_V:
                    findings.append(
                        PackPreflightFinding(
                            rule_id=RULE_VOLTAGE_LEVELS,
                            severity=PackPreflightSeverity.BLOCK,
                            message=(
                                f"node '{node.id}': rail '{net}' at "
                                f"{rail.volts:g} V exceeds max {maximum:g} V"
                            ),
                        )
                    )
        key = _has_unparseable(node.config, SUPPLY_KEYS + MAX_VOLTAGE_KEYS)
        if key is not None and supply is None and maximum is None:
            findings.append(
                PackPreflightFinding(
                    rule_id=RULE_VOLTAGE_LEVELS,
                    severity=PackPreflightSeverity.WARN,
                    message=f"node '{node.id}': unparseable voltage in '{key}'",
                )
            )

    levels: dict[str, dict[str, float]] = {}
    for node in graph.nodes:
        level = _read_float(node.config, LOGIC_LEVEL_KEYS)
        if level is None:
            continue
        for net in nets_by_node.get(node.id, ()):
            levels.setdefault(net, {})[node.id] = level
    for net, drivers in levels.items():
        distinct = sorted({round(value, 6) for value in drivers.values()})
        if len(distinct) > 1:
            involved = ", ".join(sorted(drivers))
            findings.append(
                PackPreflightFinding(
                    rule_id=RULE_VOLTAGE_LEVELS,
                    severity=PackPreflightSeverity.BLOCK,
                    message=(
                        f"net '{net}': conflicting logic levels "
                        f"{', '.join(f'{value:g} V' for value in distinct)} "
                        f"on {involved}"
                    ),
                )
            )
    return findings


def _check_pullups(graph: MethodologyGraph) -> list[PackPreflightFinding]:
    findings: list[PackPreflightFinding] = []
    netlist = extract_netlist(graph)
    nets_by_node = {record.node_id: record.nets for record in netlist.records}
    rails, _ = _collect_rails(graph)
    rail_nets = {rail.net for rail in rails}

    resistor_links: set[frozenset[str]] = set()
    kinds_by_node = {node.id: node.config.get(KIND_KEY) for node in graph.nodes}
    for node_id, nets in nets_by_node.items():
        if kinds_by_node.get(node_id) in RESISTOR_KINDS and len(nets) >= 2:
            resistor_links.add(frozenset((nets[0], nets[1])))

    for node in graph.nodes:
        wants = any(
            node.config.get(key) is True
            or (
                isinstance(node.config.get(key), str)
                and str(node.config.get(key)).lower() in ("true", "yes", "1")
            )
            for key in PULLUP_KEYS
        )
        if not wants:
            continue
        served = any(
            any(link == frozenset((net, rail)) for rail in rail_nets)
            for net in nets_by_node.get(node.id, ())
            for link in resistor_links
        )
        if not served:
            findings.append(
                PackPreflightFinding(
                    rule_id=RULE_MISSING_PULLUP,
                    severity=PackPreflightSeverity.WARN,
                    message=(
                        f"node '{node.id}': requires a pull-up but no "
                        "resistor ties its nets to a rail"
                    ),
                )
            )
    return findings


def _node_power_mw(node: GraphNode) -> _Number | None:
    stated = _read_float(node.config, POWER_KEYS)
    if stated is not None:
        return _Number(value=stated, estimated=False)
    supply = _read_float(node.config, SUPPLY_KEYS)
    current = _read_float(node.config, CURRENT_KEYS)
    if supply is not None and current is not None:
        return _Number(value=supply * current, estimated=True)
    return None


def _check_power(graph: MethodologyGraph) -> list[PackPreflightFinding]:
    findings: list[PackPreflightFinding] = []
    total = 0.0
    estimated = False
    contributors = 0
    for node in graph.nodes:
        kind, spec = _node_kind(node)
        if kind is None or spec is None or spec.directive or kind in SOURCE_KINDS:
            continue
        power = _node_power_mw(node)
        if power is None:
            continue
        total += power.value
        estimated = estimated or power.estimated
        contributors += 1

    budgets: list[tuple[str, float]] = []
    for node in graph.nodes:
        budget = _read_float(node.config, BUDGET_KEYS)
        if budget is not None:
            budgets.append((node.id, budget))
    if len({round(value, 9) for _, value in budgets}) > 1:
        findings.append(
            PackPreflightFinding(
                rule_id=RULE_POWER_BUDGET,
                severity=PackPreflightSeverity.WARN,
                message="conflicting power budgets stated on multiple nodes",
            )
        )
    if budgets and contributors:
        budget = min(value for _, value in budgets)
        if total > budget:
            findings.append(
                PackPreflightFinding(
                    rule_id=RULE_POWER_BUDGET,
                    severity=(
                        PackPreflightSeverity.WARN if estimated else PackPreflightSeverity.BLOCK
                    ),
                    message=(
                        f"estimated draw {total:g} mW exceeds budget {budget:g} mW"
                        if estimated
                        else f"stated draw {total:g} mW exceeds budget {budget:g} mW"
                    ),
                )
            )

    rails, _ = _collect_rails(graph)
    if any(rail.max_current_ma is not None for rail in rails):
        netlist = extract_netlist(graph)
        nets_by_node = {record.node_id: record.nets for record in netlist.records}
        for rail in rails:
            if rail.max_current_ma is None:
                continue
            load = 0.0
            for node in graph.nodes:
                if node.id == rail.node_id:
                    continue
                current = _read_float(node.config, CURRENT_KEYS)
                if current is not None and rail.net in nets_by_node.get(node.id, ()):
                    load += current
            if load > rail.max_current_ma:
                findings.append(
                    PackPreflightFinding(
                        rule_id=RULE_POWER_BUDGET,
                        severity=PackPreflightSeverity.BLOCK,
                        message=(
                            f"rail '{rail.net}': load {load:g} mA exceeds "
                            f"source limit {rail.max_current_ma:g} mA"
                        ),
                    )
                )
    return findings


def preflight_graph(graph: MethodologyGraph) -> tuple[PackPreflightFinding, ...]:
    """Run every electrical preflight rule; empty means clear."""
    findings = [
        *_check_pins(graph),
        *_check_voltage(graph),
        *_check_pullups(graph),
        *_check_power(graph),
    ]
    findings.sort(key=lambda item: (item.rule_id, item.severity.value, item.message))
    return tuple(findings)
