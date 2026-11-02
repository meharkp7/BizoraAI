import { describe, expect, it } from "vitest";
import { diagramsFixture } from "../../test/fixtures.ts";
import { rosterFromDiagrams } from "./diagramRoster.ts";

describe("rosterFromDiagrams", () => {
  it("lists methodology nodes with kinds and details", () => {
    const roster = rosterFromDiagrams(diagramsFixture, "methodology");

    expect(roster.map((entry) => entry.element_id)).toEqual([
      "m-input",
      "m-encode",
      "m-check",
      "m-output",
    ]);
    expect(roster[1]).toMatchObject({
      view: "methodology",
      label: "Transformer encoder",
      kind: "model",
      detail: "Twelve stacked blocks.",
    });
  });

  it("lists schematic components with values as details", () => {
    const roster = rosterFromDiagrams(diagramsFixture, "schematic");

    expect(roster.map((entry) => entry.element_id)).toEqual(["m1", "r1", "g1"]);
    expect(roster[1]).toMatchObject({
      view: "schematic",
      label: "R1",
      kind: "resistor",
      detail: "1k",
    });
  });

  it("flattens structure blocks for the 3d tab", () => {
    const roster = rosterFromDiagrams(diagramsFixture, "3d");

    expect(roster.length).toBeGreaterThan(0);
    expect(roster[0].view).toBe("structure");
    expect(roster.map((entry) => entry.element_id)).toContain("chip");
  });

  it("returns nothing without diagrams", () => {
    expect(rosterFromDiagrams(undefined, "schematic")).toEqual([]);
  });
});
