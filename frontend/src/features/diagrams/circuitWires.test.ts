import * as THREE from "three";
import { describe, expect, it } from "vitest";
import type { CircuitIRJson } from "../../lib/types.ts";
import { buildCircuitWires, wireHoverThreshold, wireLabel } from "./circuitWires.ts";

function circuit(): CircuitIRJson {
  return {
    version: 1,
    title: "wired",
    source: { figure_id: "fig1", page: 1 },
    components: [
      {
        id: "a",
        type: "nmos",
        label: "A",
        value: null,
        pins: { d: "n1", s: "gnd" },
        pin_sides: null,
        placement: null,
        confidence: 1,
        evidence: null,
      },
      {
        id: "b",
        type: "pmos",
        label: "B",
        value: null,
        pins: { d: "n1" },
        pin_sides: null,
        placement: null,
        confidence: 1,
        evidence: null,
      },
      {
        id: "loner",
        type: "resistor",
        label: "R",
        value: null,
        pins: { p: "open" },
        pin_sides: null,
        placement: null,
        confidence: 1,
        evidence: null,
      },
    ],
    nets: [
      { id: "n1", label: "N1", role: "signal", global: false },
      { id: "gnd", label: "GND", role: "ground", global: true },
      { id: "open", label: "OPEN", role: "signal", global: false },
    ],
    ports: [],
    subcircuits: [],
    layout: null,
  };
}

function anchors(): Map<string, THREE.Vector3> {
  return new Map([
    ["a", new THREE.Vector3(0, 1, 0)],
    ["b", new THREE.Vector3(4, 1, 0)],
    ["loner", new THREE.Vector3(0, 1, 5)],
  ]);
}

describe("buildCircuitWires", () => {
  it("draws one lifted arc per net leg between anchored parts", () => {
    const group = buildCircuitWires(circuit(), anchors());
    // n1 connects a-b; gnd and open touch one anchored part each.
    expect(group.children).toHaveLength(1);
    const wires = group.children[0] as THREE.LineSegments;
    expect(wires.userData).toEqual({
      net: "n1",
      label: "Net n1 (a → b)",
      legs: [{ hub: "a", spoke: "b" }],
    });
    const positions = wires.geometry.getAttribute("position") as THREE.BufferAttribute;
    expect(positions.count).toBe(4);
    // Hub -> lifted mid -> spoke.
    expect([positions.getX(0), positions.getY(0), positions.getZ(0)]).toEqual([0, 1, 0]);
    expect(positions.getY(1)).toBeGreaterThan(1);
    expect([positions.getX(3), positions.getY(3), positions.getZ(3)]).toEqual([4, 1, 0]);
  });

  it("colors supply and ground nets distinctly", () => {
    const wired = circuit();
    wired.components[1].pins = { d: "n1", s: "gnd" };
    const group = buildCircuitWires(wired, anchors());
    expect(group.children).toHaveLength(2);
    const colors = new Map(
      group.children.map((child) => [
        (child as THREE.LineSegments).userData["net"],
        ((child as THREE.LineSegments).material as THREE.LineBasicMaterial).color.getHex(),
      ]),
    );
    expect(colors.get("n1")).not.toBe(colors.get("gnd"));
  });

  it("keeps the default raycast for hover picking and draws nothing unanchored", () => {
    const group = buildCircuitWires(circuit(), anchors());
    const wires = group.children[0] as THREE.LineSegments;
    // Hover answers; clicks exclude the wires group so they pass through.
    expect(wires.raycast).toBe(THREE.Line.prototype.raycast);
    expect(buildCircuitWires(circuit(), new Map()).children).toHaveLength(0);
  });

  it("truncates long member lists in the hover label", () => {
    expect(wireLabel("vdd", ["a", "b", "c", "d", "e"])).toBe("Net vdd (a → b → c +2)");
    expect(wireLabel("n1", ["a"])).toBe("Net n1 (a)");
  });

  it("scales the hover threshold with scene size", () => {
    expect(wireHoverThreshold(10)).toBeCloseTo(0.2);
    expect(wireHoverThreshold(0)).toBeGreaterThan(0);
  });
});
