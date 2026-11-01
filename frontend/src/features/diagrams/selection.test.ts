import { describe, expect, it } from "vitest";
import { diagramsFixture } from "../../test/fixtures.ts";
import {
  findBlock,
  methodologySelection,
  schematicSelection,
  sceneIdToBlockId,
  structureSelection,
} from "./selection.ts";

describe("diagram selections", () => {
  it("builds a methodology selection with evidence and params", () => {
    const node = diagramsFixture.methodology?.nodes[1];
    if (!node) throw new Error("fixture must carry methodology nodes");
    const selection = methodologySelection(node);
    expect(selection.view).toBe("methodology");
    expect(selection.elementId).toBe("m-encode");
    expect(selection.provenance).toBe("from-paper");
    expect(selection.evidence?.page).toBe(4);
    expect(selection.evidence?.quote).toContain("twelve blocks");
    expect(selection.extra).toContainEqual({ label: "layers", value: "12" });
  });

  it("marks evidence-free nodes as assumed", () => {
    const node = diagramsFixture.methodology?.nodes[2];
    if (!node) throw new Error("fixture must carry methodology nodes");
    const selection = methodologySelection(node);
    expect(selection.provenance).toBe("assumed");
    expect(selection.evidence).toBeNull();
  });

  it("builds a schematic selection with pin nets and figure evidence", () => {
    const component = diagramsFixture.circuits[0].components[0];
    const selection = schematicSelection(
      component,
      new Map([["n-out", "OUT"], ["n-in", "IN"], ["n-vss", "VSS"]]),
    );
    expect(selection.view).toBe("schematic");
    expect(selection.elementId).toBe("m1");
    expect(selection.provenance).toBe("from-paper");
    expect(selection.evidence?.figure_id).toBe("paper-1-p2-f1-a1b2c3d4");
    expect(selection.extra).toContainEqual({ label: "Pin d", value: "OUT" });
  });

  it("builds a structure selection with count and dims", () => {
    const root = diagramsFixture.structure?.root;
    if (!root) throw new Error("fixture must carry a structure IR");
    const array = findBlock(root, "arr");
    if (!array) throw new Error("fixture must carry the array block");
    const selection = structureSelection(array, "arr[0,2]");
    expect(selection.view).toBe("structure");
    expect(selection.elementId).toBe("arr[0,2]");
    expect(selection.label).toContain("[0,2]");
    expect(selection.extra).toContainEqual({ label: "Count", value: "2 x 3" });
    expect(selection.evidence?.quote).toContain("2000 cells");
  });

  it("maps scene mesh ids back to repeated blocks", () => {
    expect(sceneIdToBlockId("arr[0,2]")).toBe("arr");
    expect(sceneIdToBlockId("peri")).toBe("peri");
    const root = diagramsFixture.structure?.root;
    if (!root) throw new Error("fixture must carry a structure IR");
    expect(findBlock(root, "cell")?.label).toBe("cell");
    expect(findBlock(root, "missing")).toBeNull();
  });
});
