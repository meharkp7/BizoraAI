import { describe, expect, it } from "vitest";
import { diagramsFixture } from "../../test/fixtures.ts";
import type { CircuitIRJson } from "../../lib/types.ts";
import { deriveCircuitSteps, sharedNet } from "./flowOrder.ts";

describe("deriveCircuitSteps", () => {
  it("walks from the input side over shared signal nets", () => {
    // m1 touches the input net n-in; r1 joins via n-out; g1 only
    // touches ground, so it appends last.
    expect(deriveCircuitSteps(diagramsFixture.circuits[0])).toEqual(["m1", "r1", "g1"]);
  });

  it("seeds from input ports when no input-role net exists", () => {
    const circuit: CircuitIRJson = {
      ...diagramsFixture.circuits[0],
      nets: diagramsFixture.circuits[0].nets.map((net) =>
        net.id === "n-in" ? { ...net, role: "signal" } : net,
      ),
      ports: [
        { id: "p", net: "n-in", label: "IN", dir: "in", side: "left", placement: null },
      ],
    };
    expect(deriveCircuitSteps(circuit)[0]).toBe("m1");
  });

  it("covers every component exactly once", () => {
    const order = deriveCircuitSteps(diagramsFacet());
    expect(order).toHaveLength(3);
    expect(new Set(order)).toEqual(new Set(["m1", "r1", "g1"]));
  });

  it("handles an empty circuit", () => {
    expect(
      deriveCircuitSteps({ ...diagramsFixture.circuits[0], components: [] }),
    ).toEqual([]);
  });
});

function diagramsFacet(): CircuitIRJson {
  return diagramsFixture.circuits[0];
}

describe("sharedNet", () => {
  it("prefers the shared signal net", () => {
    // m1 and r1 share n-out (signal); the tag reads "via OUT".
    expect(sharedNet(diagramsFacet(), "m1", "r1")).toBe("n-out");
  });

  it("falls back to any shared net", () => {
    // m1 and g1 share only ground: still shared copper.
    expect(sharedNet(diagramsFacet(), "m1", "g1")).toBe("n-vss");
  });

  it("returns null with nothing in common", () => {
    // r1 (VDD, OUT) and g1 (VSS) share no net: separate branch.
    expect(sharedNet(diagramsFacet(), "r1", "g1")).toBeNull();
  });

  it("returns null for unknown components", () => {
    expect(sharedNet(diagramsFacet(), "m1", "zzz")).toBeNull();
  });
});
