import * as THREE from "three";
import { describe, expect, it } from "vitest";
import {
  buildPartIdentity,
  identityMaterials,
  partShapeFor,
  plateLayout,
  shortTagLabel,
} from "./partIdentity.ts";

function bodyHex(block: { kind: string; part: string | null; label: string }): string {
  const model = buildPartIdentity(block);
  const mesh = model.children[0] as THREE.Mesh;
  const materials = mesh.material as THREE.MeshStandardMaterial[];
  return `#${materials[0].color.getHexString()}`;
}

describe("partIdentity", () => {
  it("shapes stores as canisters from the typed part enum", () => {
    expect(partShapeFor({ kind: "part", part: "store" })).toBe("cylinder");
    expect(partShapeFor({ kind: "part", part: "dataset" })).toBe("cylinder");
    expect(partShapeFor({ kind: "part", part: "Store" })).toBe("cylinder");
  });

  it("shapes modules as slabs and everything else as boxes", () => {
    expect(partShapeFor({ kind: "module", part: null })).toBe("slab");
    expect(partShapeFor({ kind: "part", part: "model" })).toBe("box");
    expect(partShapeFor({ kind: "part", part: "nmos" })).toBe("box");
    expect(partShapeFor({ kind: "part", part: "Raspberry Pi 4" })).toBe("box");
    expect(partShapeFor({ kind: "part", part: null })).toBe("box");
  });

  it("never reads the label: device words in free text change nothing", () => {
    // The mapping takes only kind/part; labels ride the plate instead.
    expect(partShapeFor({ kind: "part", part: "model" })).toBe("box");
    expect(partShapeFor({ kind: "array", part: null })).toBe("box");
  });

  it("wraps plate titles onto two lines with an ellipsis", () => {
    expect(plateLayout("Encode", "part", "model")).toEqual({
      title: ["Encode"],
      sub: "part · model",
    });
    const wrapped = plateLayout("Serial readout circuitry block", "part", null);
    expect(wrapped.title).toEqual(["Serial readout", "circuitry block"]);
    expect(wrapped.sub).toBe("part");
    const long = plateLayout(
      "Fabricate two thousand cell array in TSMC sixty five nanometer process",
      "part",
      "process",
    );
    expect(long.title).toHaveLength(2);
    expect(long.title[1].endsWith("…")).toBe(true);
  });

  it("tints closed type families and slates everything else", () => {
    expect(bodyHex({ kind: "part", part: "nmos", label: "N1" })).toBe("#4a6a8a");
    expect(bodyHex({ kind: "part", part: "PMOS", label: "P1" })).toBe("#4a6a8a");
    expect(bodyHex({ kind: "part", part: "resistor", label: "R1" })).toBe("#8a7350");
    expect(bodyHex({ kind: "part", part: "inverter", label: "INV" })).toBe("#5f7052");
    expect(bodyHex({ kind: "part", part: "ground", label: "GND" })).toBe("#2e343b");
    expect(bodyHex({ kind: "part", part: "decision", label: "Pick" })).toBe("#9a6234");
    expect(bodyHex({ kind: "part", part: "Raspberry Pi 4", label: "Pi" })).toBe("#5a6470");
    expect(bodyHex({ kind: "part", part: null, label: "Mystery" })).toBe("#5a6470");
  });

  it("shortens floating tags at word boundaries", () => {
    expect(shortTagLabel("K1")).toBe("K1");
    expect(shortTagLabel("PTQ Adaptation")).toBe("PTQ Adaptation");
    expect(shortTagLabel("PTQ Adaptation Step: fix Q")).toBe("PTQ Adaptation…");
    expect(shortTagLabel("Construct block-wise scaling matrix S")).toBe("Construct…");
    expect(shortTagLabel("Commonsense-170k-dataset-split")).toBe("Commonsense-170k-…");
  });

  it("builds one body plus edges with fresh materials per call", () => {
    const first = buildPartIdentity({ kind: "part", part: "store", label: "PostgreSQL" });
    const second = buildPartIdentity({ kind: "part", part: "store", label: "PostgreSQL" });
    expect(first.children).toHaveLength(2);
    expect(second.children).toHaveLength(2);
    const a = identityMaterials(first);
    const b = identityMaterials(second);
    expect(a.length).toBeGreaterThan(0);
    expect(a.length).toBe(b.length);
    for (const [index, material] of a.entries()) {
      expect(material).not.toBe(b[index]);
    }
  });

  it("builds without canvas 2D (jsdom) via the plain-top fallback", () => {
    const model = buildPartIdentity({ kind: "module", part: null, label: "Edge node" });
    expect(model.children).toHaveLength(2);
    expect(identityMaterials(model).length).toBeGreaterThan(0);
  });
});
