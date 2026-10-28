"""Tests for electronics netlist and BOM extraction.

Extraction is data-driven: node config declares ``spice_kind``/``nets``/
values, and the element table in the netlist module defines every shape.
Fixtures below describe ordinary circuits (dividers, RC stages); the
tables, not the test names, carry part knowledge.
"""

from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.packs.electronics.bom import extract_bom
from bizora.packs.electronics.netlist import (
    ELEMENT_TABLE,
    extract_netlist,
    simulatable_nodes,
)


def make_node(node_id: str, label: str, **config: object) -> GraphNode:
    """Build one component node with the given config data."""
    return GraphNode(id=node_id, kind=NodeKind.COMPONENT, label=label, config=dict(config))


def make_graph(nodes: tuple[GraphNode, ...], edges: tuple[GraphEdge, ...] = ()) -> MethodologyGraph:
    """Build a methodology graph from component nodes."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Divider",
        nodes=nodes,
        edges=edges,
        created_by="tester",
    )


def divider_nodes(r2_value: str = "1k") -> tuple[GraphNode, ...]:
    """Build a voltage-divider circuit with an operating-point readout."""
    directives = (".op", ".control", "run", "print v(out)", ".endc")
    return (
        make_node(
            "v1",
            "Supply",
            spice_kind="voltage-source",
            refdes="V1",
            nets=["in", "0"],
            voltage_v="5",
        ),
        make_node(
            "r1",
            "Resistor",
            spice_kind="resistor",
            refdes="R1",
            nets=["in", "out"],
            resistance_ohm="1k",
        ),
        make_node(
            "r2",
            "Resistor",
            spice_kind="resistor",
            refdes="R2",
            nets=["out", "0"],
            resistance_ohm=r2_value,
        ),
        *(
            make_node(f"d{index}", "Directive", spice_kind="directive", line=text)
            for index, text in enumerate(directives)
        ),
    )


def test_divider_netlist_has_expected_lines() -> None:
    """Element values and nets render in pin order from config data."""
    netlist = extract_netlist(make_graph(divider_nodes()))

    assert netlist.element_lines == (
        "V1 in 0 DC 5",
        "R1 in out 1k",
        "R2 out 0 1k",
    )
    assert netlist.directive_lines == (".op", ".control", "run", "print v(out)", ".endc")
    assert netlist.text.startswith("* netlist for graph-1 v1: Divider\n")
    assert netlist.text.endswith(".end\n")
    assert netlist.warnings == ()


def test_edit_changes_extracted_netlist() -> None:
    """Editing one config value changes exactly that element line."""
    before = extract_netlist(make_graph(divider_nodes("1k")))
    after = extract_netlist(make_graph(divider_nodes("3k")))

    assert before.element_lines[2] == "R2 out 0 1k"
    assert after.element_lines[2] == "R2 out 0 3k"
    assert before.element_lines[:2] == after.element_lines[:2]


def test_refdes_defaults_follow_table_prefixes() -> None:
    """Missing refdes values default to PREFIX + index per table row."""
    graph = make_graph(
        (
            make_node("a", "Resistor", spice_kind="resistor", nets=["n1", "0"], value="1k"),
            make_node("b", "Resistor", spice_kind="resistor", nets=["n1", "0"], value="2k"),
            make_node("c", "Capacitor", spice_kind="capacitor", nets=["n1", "0"], value="1n"),
        )
    )

    netlist = extract_netlist(graph)

    assert netlist.refdes_by_node == {"a": "R1", "b": "R2", "c": "C1"}
    assert netlist.element_lines[0].startswith("R1 ")
    assert netlist.element_lines[2].startswith("C1 ")


def test_model_kinds_emit_default_model_cards() -> None:
    """Diode and transistor rows emit their table-defined .model cards."""
    graph = make_graph(
        (
            make_node("d1", "Diode", spice_kind="diode", refdes="D1", nets=["n1", "0"]),
            make_node(
                "q1",
                "Transistor",
                spice_kind="bjt-npn",
                refdes="Q1",
                nets=["n2", "n1", "0"],
            ),
        )
    )

    netlist = extract_netlist(graph)

    assert ".model DMOD_DEFAULT D" in netlist.model_lines
    assert ".model QMOD_NPN NPN" in netlist.model_lines
    assert netlist.element_lines == (
        "D1 n1 0 DMOD_DEFAULT",
        "Q1 n2 n1 0 QMOD_NPN",
    )


def test_explicit_model_overrides_default_without_card() -> None:
    """A config model name replaces the default and emits no card."""
    graph = make_graph(
        (
            make_node(
                "d1",
                "Diode",
                spice_kind="diode",
                refdes="D1",
                nets=["n1", "0"],
                model="MYDIODE",
            ),
        )
    )

    netlist = extract_netlist(graph)

    assert netlist.element_lines == ("D1 n1 0 MYDIODE",)
    assert netlist.model_lines == ()


def test_unknown_kind_is_skipped_with_warning() -> None:
    """Kinds outside the table are skipped, never guessed."""
    graph = make_graph(
        (
            make_node("x1", "Exotic", spice_kind="flux-capacitor", nets=["n1", "0"]),
            make_node("r1", "Resistor", spice_kind="resistor", nets=["n1", "0"], value="1k"),
        )
    )

    netlist = extract_netlist(graph)

    assert len(netlist.element_lines) == 1
    assert any("flux-capacitor" in warning for warning in netlist.warnings)
    assert simulatable_nodes(graph) == (graph.nodes[1],)


def test_missing_nets_derive_from_incident_edges() -> None:
    """Connectivity falls back to incident edges with a warning."""
    graph = make_graph(
        (
            make_node("r1", "Resistor", spice_kind="resistor", refdes="R1", value="1k"),
            make_node("r2", "Resistor", spice_kind="resistor", refdes="R2", value="1k"),
        ),
        (
            GraphEdge(id="e-link", source="r1", target="r2"),
            GraphEdge(id="e-tail", source="r2", target="r1"),
        ),
    )

    netlist = extract_netlist(graph)

    assert netlist.element_lines[0] == "R1 n_e-link n_e-tail 1k"
    assert any("derived" in warning for warning in netlist.warnings)


def test_pin_repair_pads_and_warns() -> None:
    """Short net lists are padded deterministically with a warning."""
    graph = make_graph(
        (
            make_node(
                "q1",
                "Transistor",
                spice_kind="bjt-npn",
                refdes="Q1",
                nets=["c", "b", "e", "extra"],
            ),
            make_node("m1", "Fet", spice_kind="nmos", refdes="M1", nets=["d", "g"]),
        )
    )

    netlist = extract_netlist(graph)

    assert netlist.element_lines[0] == "Q1 c b e QMOD_NPN"
    assert netlist.element_lines[1] == "M1 d g M1_2 M1_3 MMOD_NMOS"
    assert any("exceed" in warning for warning in netlist.warnings)
    assert any("padded" in warning for warning in netlist.warnings)


def test_missing_ground_warns() -> None:
    """A netlist without net '0' warns about the missing reference."""
    graph = make_graph(
        (make_node("r1", "Resistor", spice_kind="resistor", nets=["a", "b"], value="1k"),)
    )

    netlist = extract_netlist(graph)

    assert any("ground" in warning for warning in netlist.warnings)


def test_directive_nodes_emit_verbatim() -> None:
    """Directive rows pass graph data through to the netlist untouched."""
    graph = make_graph(
        (
            make_node("r1", "Resistor", spice_kind="resistor", nets=["a", "0"], value="1k"),
            make_node("ac", "Analysis", spice_kind="directive", line=".tran 10n 20u"),
        )
    )

    netlist = extract_netlist(graph)

    assert ".tran 10n 20u" in netlist.directive_lines


def test_table_covers_expected_shapes() -> None:
    """Pin counts and prefixes come from the table, not from branches."""
    assert ELEMENT_TABLE["resistor"].terminals == 2
    assert ELEMENT_TABLE["resistor"].prefix == "R"
    assert ELEMENT_TABLE["bjt-npn"].terminals == 3
    assert ELEMENT_TABLE["nmos"].terminals == 4
    assert ELEMENT_TABLE["nmos"].pin_order == ("drain", "gate", "source", "bulk")
    assert ELEMENT_TABLE["voltage-source"].dc_prefix is True
    assert ELEMENT_TABLE["directive"].directive is True


def test_bom_groups_identical_parts() -> None:
    """Same label plus same signature aggregates into one line."""
    graph = make_graph(divider_nodes())
    netlist = extract_netlist(graph)

    bom = extract_bom(graph, netlist.refdes_by_node)

    assert bom.total_quantity == 3
    by_label = {entry.label: entry for entry in bom.entries}
    assert by_label["Resistor"].quantity == 2
    assert by_label["Resistor"].designators == ("R1", "R2")
    assert by_label["Supply"].quantity == 1
    assert all(entry.label != "Directive" for entry in bom.entries)


def test_bom_edit_splits_a_line() -> None:
    """Changing one value splits the shared BOM line in two."""
    graph = make_graph(divider_nodes("3k"))
    netlist = extract_netlist(graph)

    bom = extract_bom(graph, netlist.refdes_by_node)

    resistor_lines = [entry for entry in bom.entries if entry.label == "Resistor"]
    assert len(resistor_lines) == 2
    assert sorted(entry.quantity for entry in resistor_lines) == [1, 1]
    assert bom.total_quantity == 3


def test_bom_assigns_designators_when_map_absent() -> None:
    """BOM extraction stays total without a netlist refdes map."""
    graph = make_graph((make_node("r1", "Resistor", spice_kind="resistor", value="1k"),))

    bom = extract_bom(graph)

    assert bom.entries[0].designators == ("P1",)
    assert len(bom.warnings) == 1
