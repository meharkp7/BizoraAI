import { describe, expect, it } from "vitest";
import { diagramsFixture } from "../../test/fixtures.ts";
import { renderStructureDiagram } from "./adapters.ts";
import { circuitToStructure } from "./circuitToStructure.ts";

describe("circuitToStructure", () => {
  it("maps every component to a part with its figure evidence", () => {
    const structure = circuitToStructure(diagramsFixture.circuits[0]);

    expect(structure.root.children.map((part) => part.id)).toEqual([
      "m1",
      "r1",
      "g1",
    ]);
    const m1 = structure.root.children[0];
    expect(m1.kind).toBe("part");
    expect(m1.part).toBe("nmos");
    expect(m1.evidence?.figure_id).toBe(
      diagramsFixture.circuits[0].source.figure_id,
    );
    expect(m1.confidence).toBe(
      diagramsFixture.circuits[0].components[0].confidence,
    );
  });

  it("builds a plateless scene of exactly the schematic parts", () => {
    const structure = circuitToStructure(diagramsFixture.circuits[0]);
    const built = renderStructureDiagram(structure);

    expect(built.ok).toBe(true);
    if (!built.ok) return;
    // No board, no die plate: only the three component boxes.
    expect(built.scene.boxes.map((box) => box.id).sort()).toEqual([
      "g1",
      "m1",
      "r1",
    ]);
    expect(
      built.scene.boxes.every((box) => box.kind === "part"),
    ).toBe(true);
  });

  it("roots the scene at its source figure", () => {
    const structure = circuitToStructure(diagramsFixture.circuits[0]);

    expect(structure.root.kind).toBe("cell");
    expect(structure.root.evidence?.figure_id).toBe(
      diagramsFixture.circuits[0].source.figure_id,
    );
  });
});
