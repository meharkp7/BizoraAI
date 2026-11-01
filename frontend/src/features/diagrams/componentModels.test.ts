import * as THREE from "three";
import { describe, expect, it } from "vitest";
import type { ComponentModelKind } from "./componentModels.ts";
import {
  buildComponentModel,
  modelKindForBlock,
  modelKindForType,
  modelMaterials,
} from "./componentModels.ts";

const KINDS: ComponentModelKind[] = [
  "nmos",
  "pmos",
  "nmosPair",
  "pmosPair",
  "inverter",
  "capacitor",
  "resistor",
  "inductor",
  "ground",
];

describe("modelKindForType", () => {
  it("maps IR component types to models", () => {
    expect(modelKindForType("nmos")).toBe("nmos");
    expect(modelKindForType("pmos")).toBe("pmos");
    expect(modelKindForType("inverter")).toBe("inverter");
    expect(modelKindForType("capacitor")).toBe("capacitor");
    expect(modelKindForType("resistor")).toBe("resistor");
    expect(modelKindForType("inductor")).toBe("inductor");
    expect(modelKindForType("ground")).toBe("ground");
  });

  it("accepts aliases and letter case", () => {
    expect(modelKindForType("NFET")).toBe("nmos");
    expect(modelKindForType("pfet")).toBe("pmos");
    expect(modelKindForType("NOT")).toBe("inverter");
    expect(modelKindForType("cap")).toBe("capacitor");
    expect(modelKindForType("GND")).toBe("ground");
  });

  it("keeps the engine box for unknown types", () => {
    expect(modelKindForType("bjt")).toBeNull();
    expect(modelKindForType("")).toBeNull();
    expect(modelKindForType(null)).toBeNull();
    expect(modelKindForType(undefined)).toBeNull();
  });
});

describe("modelKindForBlock", () => {
  it("prefers the typed part field", () => {
    expect(modelKindForBlock({ part: "pmos", label: "NMOS pair N1-N2" })).toBe("pmos");
  });

  it("reads device keywords from the paper's own labels", () => {
    expect(modelKindForBlock({ part: null, label: "NMOS pair N1-N2" })).toBe("nmosPair");
    expect(modelKindForBlock({ part: null, label: "PMOS pair P1-P2 HVT" })).toBe("pmosPair");
    expect(modelKindForBlock({ part: null, label: "MOM coupling capacitor" })).toBe(
      "capacitor",
    );
    expect(modelKindForBlock({ part: null, label: "footer NFET S1" })).toBe("nmos");
  });

  it("keeps boxes for switches, keepers and near-misses", () => {
    expect(modelKindForBlock({ part: null, label: "Discharge switch S1 HVT" })).toBeNull();
    expect(modelKindForBlock({ part: null, label: "Selection switches S2-S3" })).toBeNull();
    expect(modelKindForBlock({ part: null, label: "Keepers K1-K2" })).toBeNull();
    // Whole words only: "knot" is not a NOT gate, "capsule" is not a cap.
    expect(modelKindForBlock({ part: null, label: "knot anchor" })).toBeNull();
    expect(modelKindForBlock({ part: null, label: "capsule lid" })).toBeNull();
  });
});

describe("buildComponentModel", () => {
  it.each(KINDS)("builds a multi-part %s inside the unit footprint", (kind) => {
    const model = buildComponentModel(kind);
    let meshes = 0;
    model.traverse((child) => {
      if (child instanceof THREE.Mesh) meshes += 1;
    });
    expect(meshes).toBeGreaterThanOrEqual(4);
    const bounds = new THREE.Box3().setFromObject(model);
    expect(bounds.min.x).toBeGreaterThanOrEqual(-0.55);
    expect(bounds.max.x).toBeLessThanOrEqual(0.55);
    expect(bounds.min.z).toBeGreaterThanOrEqual(-0.55);
    expect(bounds.max.z).toBeLessThanOrEqual(0.55);
    expect(bounds.min.y).toBeGreaterThanOrEqual(-0.01);
    expect(bounds.max.y).toBeLessThanOrEqual(0.55);
  });

  it("mints fresh materials per build so the spotlight stays local", () => {
    const first = new Set(modelMaterials(buildComponentModel("nmos")));
    const second = modelMaterials(buildComponentModel("nmos"));
    expect(second.length).toBeGreaterThan(0);
    for (const material of second) expect(first.has(material)).toBe(false);
  });

  it("gives PMOS a well tub NMOS lacks", () => {
    const nmosColors = new Set(
      modelMaterials(buildComponentModel("nmos")).map((mat) => mat.color.getHex()),
    );
    const pmosColors = new Set(
      modelMaterials(buildComponentModel("pmos")).map((mat) => mat.color.getHex()),
    );
    // Well blue only on the PMOS side; both share gate metal.
    expect(pmosColors.has(0x7fb6dc)).toBe(true);
    expect(nmosColors.has(0x7fb6dc)).toBe(false);
  });
});
