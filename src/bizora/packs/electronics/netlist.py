"""SPICE netlist extraction from methodology graphs.

Every element mapping lives in data tables (:data:`ELEMENT_TABLE` and the
``*_KEY`` tuples). The logic below only reads node config through those
tables, so new parts are added as data rows, never as new branches
(Rule Zero: parts live in data).

Node config schema (all keys are plain data)::

    spice_kind   element key into ELEMENT_TABLE (required to simulate)
    refdes       reference designator, e.g. "R7" (default: PREFIX + index)
    nets         ordered net names in the table's pin order
                 (default: derived from incident graph edges, with warnings)
    value        generic element value, e.g. "1k", "10u", "5"
    <kind keys>  kind-specific value keys, e.g. resistance_ohm, voltage_v
    model        SPICE model name (default: the table's default model)
    spice_args   extra tokens appended verbatim, e.g. "W=10u L=1u"
    line         directive text for spice_kind "directive"

Connectivity falls back to graph edges when ``nets`` is absent: each
incident edge contributes one net named after the edge, padded or
truncated to the element's terminal count with a warning per repair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bizora.contracts.graph import GraphNode, MethodologyGraph

# ---------------------------------------------------------------------------
# Config-key vocabulary (data: which node-config keys the logic may read).
# ---------------------------------------------------------------------------

KIND_KEY = "spice_kind"
REFDES_KEY = "refdes"
NETS_KEY = "nets"
VALUE_KEY = "value"
MODEL_KEY = "model"
ARGS_KEY = "spice_args"
LINE_KEY = "line"

GROUND_NET = "0"


@dataclass(frozen=True)
class ElementSpec:
    """One data row mapping a config kind to a SPICE element shape."""

    prefix: str
    terminals: int  # 0 means variable (uses every listed net)
    value_keys: tuple[str, ...]  # config keys consulted in order
    default_value: str | None  # emitted when no value key is present
    dc_prefix: bool  # render the value as "DC <value>" (sources)
    default_model: str | None  # model name when config carries none
    default_model_line: str | None  # .model card for the default model
    uses_model: bool  # append the model name to the element line
    block_key: str | None  # required config key naming a block after the nets
    directive: bool  # emit the config line verbatim, no element
    pin_order: tuple[str, ...]  # documents the expected nets order


# ---------------------------------------------------------------------------
# Element table (data: the only place element shapes are defined).
# ---------------------------------------------------------------------------

ELEMENT_TABLE: dict[str, ElementSpec] = {
    "resistor": ElementSpec(
        prefix="R",
        terminals=2,
        value_keys=("resistance_ohm", "resistance", VALUE_KEY),
        default_value=None,
        dc_prefix=False,
        default_model=None,
        default_model_line=None,
        uses_model=False,
        block_key=None,
        directive=False,
        pin_order=("a", "b"),
    ),
    "capacitor": ElementSpec(
        prefix="C",
        terminals=2,
        value_keys=("capacitance_f", "capacitance", VALUE_KEY),
        default_value=None,
        dc_prefix=False,
        default_model=None,
        default_model_line=None,
        uses_model=False,
        block_key=None,
        directive=False,
        pin_order=("a", "b"),
    ),
    "inductor": ElementSpec(
        prefix="L",
        terminals=2,
        value_keys=("inductance_h", "inductance", VALUE_KEY),
        default_value=None,
        dc_prefix=False,
        default_model=None,
        default_model_line=None,
        uses_model=False,
        block_key=None,
        directive=False,
        pin_order=("a", "b"),
    ),
    "voltage-source": ElementSpec(
        prefix="V",
        terminals=2,
        value_keys=("voltage_v", "dc_v", VALUE_KEY),
        default_value="5",
        dc_prefix=True,
        default_model=None,
        default_model_line=None,
        uses_model=False,
        block_key=None,
        directive=False,
        pin_order=("plus", "minus"),
    ),
    "current-source": ElementSpec(
        prefix="I",
        terminals=2,
        value_keys=("current_a", "dc_a", VALUE_KEY),
        default_value="0.001",
        dc_prefix=True,
        default_model=None,
        default_model_line=None,
        uses_model=False,
        block_key=None,
        directive=False,
        pin_order=("plus", "minus"),
    ),
    "diode": ElementSpec(
        prefix="D",
        terminals=2,
        value_keys=(),
        default_value=None,
        dc_prefix=False,
        default_model="DMOD_DEFAULT",
        default_model_line=".model DMOD_DEFAULT D",
        uses_model=True,
        block_key=None,
        directive=False,
        pin_order=("anode", "cathode"),
    ),
    "bjt-npn": ElementSpec(
        prefix="Q",
        terminals=3,
        value_keys=(),
        default_value=None,
        dc_prefix=False,
        default_model="QMOD_NPN",
        default_model_line=".model QMOD_NPN NPN",
        uses_model=True,
        block_key=None,
        directive=False,
        pin_order=("collector", "base", "emitter"),
    ),
    "bjt-pnp": ElementSpec(
        prefix="Q",
        terminals=3,
        value_keys=(),
        default_value=None,
        dc_prefix=False,
        default_model="QMOD_PNP",
        default_model_line=".model QMOD_PNP PNP",
        uses_model=True,
        block_key=None,
        directive=False,
        pin_order=("collector", "base", "emitter"),
    ),
    "nmos": ElementSpec(
        prefix="M",
        terminals=4,
        value_keys=(),
        default_value=None,
        dc_prefix=False,
        default_model="MMOD_NMOS",
        default_model_line=".model MMOD_NMOS NMOS",
        uses_model=True,
        block_key=None,
        directive=False,
        pin_order=("drain", "gate", "source", "bulk"),
    ),
    "pmos": ElementSpec(
        prefix="M",
        terminals=4,
        value_keys=(),
        default_value=None,
        dc_prefix=False,
        default_model="MMOD_PMOS",
        default_model_line=".model MMOD_PMOS PMOS",
        uses_model=True,
        block_key=None,
        directive=False,
        pin_order=("drain", "gate", "source", "bulk"),
    ),
    "subcircuit": ElementSpec(
        prefix="X",
        terminals=0,
        value_keys=(VALUE_KEY,),
        default_value=None,
        dc_prefix=False,
        default_model=None,
        default_model_line=None,
        uses_model=False,
        block_key="subckt",
        directive=False,
        pin_order=(),
    ),
    "directive": ElementSpec(
        prefix="",
        terminals=0,
        value_keys=(),
        default_value=None,
        dc_prefix=False,
        default_model=None,
        default_model_line=None,
        uses_model=False,
        block_key=None,
        directive=True,
        pin_order=(),
    ),
}


@dataclass
class NodeRecord:
    """Extraction outcome for one graph node."""

    node_id: str
    kind: str | None
    refdes: str | None
    nets: tuple[str, ...] = ()
    line: str | None = None
    simulatable: bool = False
    pins_repaired: bool = False
    warnings: tuple[str, ...] = ()


@dataclass
class NetlistResult:
    """One extracted netlist with per-node records and warnings."""

    text: str
    element_lines: tuple[str, ...] = ()
    model_lines: tuple[str, ...] = ()
    directive_lines: tuple[str, ...] = ()
    records: tuple[NodeRecord, ...] = ()
    warnings: tuple[str, ...] = ()
    refdes_by_node: dict[str, str] = field(default_factory=dict)


def simulatable_nodes(graph: MethodologyGraph) -> tuple[GraphNode, ...]:
    """Return nodes whose config names a known, non-directive element kind."""
    selected: list[GraphNode] = []
    for node in graph.nodes:
        kind = node.config.get(KIND_KEY)
        spec = ELEMENT_TABLE.get(kind) if isinstance(kind, str) else None
        if spec is not None and not spec.directive:
            selected.append(node)
    return tuple(selected)


def _config_text(config: dict[str, Any], key: str) -> str | None:
    value = config.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def _config_nets(config: dict[str, Any]) -> tuple[str, ...] | None:
    value = config.get(NETS_KEY)
    if not isinstance(value, list):
        return None
    nets: list[str] = []
    for entry in value:
        if isinstance(entry, (str, int, float)) and not isinstance(entry, bool):
            text = str(entry).strip()
            if text:
                nets.append(text)
    return tuple(nets) if nets else None


def _edge_nets(graph: MethodologyGraph, node_id: str) -> tuple[str, ...]:
    incident = sorted(
        edge.id for edge in graph.edges if edge.source == node_id or edge.target == node_id
    )
    return tuple(f"n_{edge_id}" for edge_id in incident)


def _fit_nets(
    node_id: str,
    refdes: str,
    spec: ElementSpec,
    explicit: tuple[str, ...] | None,
    fallback: tuple[str, ...],
) -> tuple[tuple[str, ...], bool, tuple[str, ...]]:
    """Fit a net list to the element's terminal count, warning on repairs."""
    warnings: list[str] = []
    repaired = False
    if spec.terminals == 0:
        nets = explicit if explicit is not None else fallback
        if not nets:
            warnings.append(f"node '{node_id}': no nets available; element skipped")
        return nets, False, tuple(warnings)
    if explicit is not None:
        nets = explicit
        source = "config nets"
    else:
        nets = fallback
        source = "graph edges"
        warnings.append(f"node '{node_id}': no config nets; derived {len(nets)} nets from {source}")
    if len(nets) > spec.terminals:
        repaired = True
        warnings.append(
            f"node '{node_id}': {len(nets)} nets exceed {spec.terminals} "
            f"terminals ({', '.join(spec.pin_order)}); truncated"
        )
        nets = nets[: spec.terminals]
    elif len(nets) < spec.terminals:
        repaired = True
        missing = spec.terminals - len(nets)
        pad = tuple(f"{refdes}_{index}" for index in range(len(nets), spec.terminals))
        warnings.append(
            f"node '{node_id}': {len(nets)} nets for {spec.terminals} "
            f"terminals ({', '.join(spec.pin_order)}); padded {missing}"
        )
        nets = nets + pad
    return nets, repaired, tuple(warnings)


def extract_netlist(graph: MethodologyGraph) -> NetlistResult:
    """Extract a SPICE netlist from a methodology graph.

    Unknown or absent ``spice_kind`` values are skipped with a warning;
    nothing is guessed about parts the table does not define.
    """
    element_lines: list[str] = []
    model_lines: list[str] = []
    directive_lines: list[str] = []
    warnings: list[str] = []
    records: list[NodeRecord] = []
    refdes_by_node: dict[str, str] = {}
    seen_models: set[str] = set()
    counters: dict[str, int] = {}

    for node in graph.nodes:
        raw_kind = node.config.get(KIND_KEY)
        kind = raw_kind if isinstance(raw_kind, str) else None
        spec = ELEMENT_TABLE.get(kind) if kind is not None else None
        if spec is None:
            records.append(NodeRecord(node_id=node.id, kind=kind, refdes=None))
            if kind is not None:
                warnings.append(f"node '{node.id}': unknown spice_kind '{kind}'; skipped")
            continue
        if spec.directive:
            text = _config_text(node.config, LINE_KEY)
            if text is None:
                message = f"node '{node.id}': directive without '{LINE_KEY}'; skipped"
                warnings.append(message)
                records.append(
                    NodeRecord(node_id=node.id, kind=kind, refdes=None, warnings=(message,))
                )
                continue
            directive_lines.append(text)
            records.append(NodeRecord(node_id=node.id, kind=kind, refdes=None, line=text))
            continue

        refdes = _config_text(node.config, REFDES_KEY)
        if refdes is None:
            counters[spec.prefix] = counters.get(spec.prefix, 0) + 1
            refdes = f"{spec.prefix}{counters[spec.prefix]}"
        refdes_by_node[node.id] = refdes
        explicit = _config_nets(node.config)
        fallback = _edge_nets(graph, node.id)
        nets, repaired, fit_warnings = _fit_nets(node.id, refdes, spec, explicit, fallback)
        warnings.extend(fit_warnings)
        if not nets:
            records.append(
                NodeRecord(
                    node_id=node.id,
                    kind=kind,
                    refdes=refdes,
                    nets=(),
                    pins_repaired=repaired,
                    warnings=fit_warnings,
                )
            )
            continue

        tokens = [refdes, *nets]
        if spec.block_key is not None:
            block = _config_text(node.config, spec.block_key)
            if block is None:
                message = f"node '{node.id}': {kind} without '{spec.block_key}'; skipped"
                warnings.append(message)
                records.append(
                    NodeRecord(
                        node_id=node.id,
                        kind=kind,
                        refdes=refdes,
                        nets=nets,
                        pins_repaired=repaired,
                        warnings=fit_warnings + (message,),
                    )
                )
                continue
            tokens.append(block)
        model = _config_text(node.config, MODEL_KEY) or spec.default_model
        if spec.uses_model and model is not None:
            tokens.append(model)
            if (
                model == spec.default_model
                and spec.default_model_line is not None
                and spec.default_model not in seen_models
            ):
                seen_models.add(spec.default_model)
                model_lines.append(spec.default_model_line)
        value: str | None = None
        for key in spec.value_keys:
            value = _config_text(node.config, key)
            if value is not None:
                break
        if value is None:
            value = spec.default_value
            if value is None and spec.value_keys:
                warnings.append(
                    f"node '{node.id}': no value for keys "
                    f"{', '.join(spec.value_keys)}; element may fail in ngspice"
                )
        if value is not None:
            tokens.append(f"DC {value}" if spec.dc_prefix else value)
        args = _config_text(node.config, ARGS_KEY)
        if args is not None:
            tokens.append(args)
        line = " ".join(tokens)
        element_lines.append(line)
        records.append(
            NodeRecord(
                node_id=node.id,
                kind=kind,
                refdes=refdes,
                nets=nets,
                line=line,
                simulatable=True,
                pins_repaired=repaired,
                warnings=fit_warnings,
            )
        )

    if element_lines and not any(net == GROUND_NET for record in records for net in record.nets):
        warnings.append("no ground net ('0') found; ngspice needs a ground reference")

    title = " ".join(str(graph.title).split())
    text_lines = [f"* netlist for {graph.graph_id} v{graph.version}: {title}"]
    text_lines.extend(model_lines)
    text_lines.extend(element_lines)
    text_lines.extend(directive_lines)
    text_lines.append(".end")
    return NetlistResult(
        text="\n".join(text_lines) + "\n",
        element_lines=tuple(element_lines),
        model_lines=tuple(model_lines),
        directive_lines=tuple(directive_lines),
        records=tuple(records),
        warnings=tuple(warnings),
        refdes_by_node=refdes_by_node,
    )
