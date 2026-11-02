import * as THREE from "three";
import { describe, expect, it } from "vitest";
import {
  buildComponentModel,
  modelKindForBlock,
  modelKindForKind,
  modelKindForType,
  modelMaterials,
  type ComponentModelKind,
} from "./componentModels.ts";

const ALL_KINDS: ComponentModelKind[] = [
  "nmos",
  "pmos",
  "nmosPair",
  "pmosPair",
  "inverter",
  "buffer",
  "capacitor",
  "resistor",
  "inductor",
  "diode",
  "ground",
  "vsource",
  "isource",
  "amp",
  "comparator",
  "adc",
  "dac",
  "sensor",
  "database",
  "layerStack",
  "modelStack",
  "inputPort",
  "outputPort",
  "decision",
  "moduleSlab",
];

describe("modelKindForType", () => {
  it.each([
    ["nmos", "nmos"],
    ["NMOSFET", "nmos"],
    ["nfet", "nmos"],
    ["pmos", "pmos"],
    ["pFET", "pmos"],
    ["inverter", "inverter"],
    ["inv", "inverter"],
    ["capacitor", "capacitor"],
    ["cap", "capacitor"],
    ["resistor", "resistor"],
    ["inductor", "inductor"],
    ["coil", "inductor"],
    ["diode", "diode"],
    ["ground", "ground"],
    ["gnd", "ground"],
    ["vsource", "vsource"],
    ["isource", "isource"],
    ["buffer", "buffer"],
    ["amp", "amp"],
    ["opamp", "amp"],
    ["comparator", "comparator"],
    ["adc", "adc"],
    ["dac", "dac"],
    ["sensor", "sensor"],
    ["store", "database"],
    ["dataset", "database"],
    ["model", "modelStack"],
    ["input", "inputPort"],
    ["output", "outputPort"],
    ["decision", "decision"],
  ] as Array<[string, ComponentModelKind]>)("maps typed %s to %s", (type, kind) => {
    expect(modelKindForType(type)).toBe(kind);
  });

  it.each([["block"], ["process"], ["evaluation"], ["transistor"], ["mystery"], [null], [""]])(
    "leaves %s to the fallback",
    (type) => {
      expect(modelKindForType(type)).toBeNull();
    },
  );
});

describe("modelKindForKind", () => {
  it("reads layers as weight stacks and modules as slabs", () => {
    expect(modelKindForKind("layer")).toBe("layerStack");
    expect(modelKindForKind("module")).toBe("moduleSlab");
  });

  it.each(["part", "chip", "array", "cell", "board", "region", "periphery"])(
    "leaves kind %s to part/label mapping",
    (kind) => {
      expect(modelKindForKind(kind)).toBeNull();
    },
  );
});

describe("modelKindForBlock", () => {
  it("prefers the typed part over the label", () => {
    expect(
      modelKindForBlock({ kind: "part", part: "pmos", label: "NMOS pair N1-N2" }),
    ).toBe("pmos");
  });

  it("reads pairs from whole label words", () => {
    expect(modelKindForBlock({ kind: "part", part: null, label: "NMOS pair N1-N2" })).toBe(
      "nmosPair",
    );
    expect(
      modelKindForBlock({ kind: "part", part: null, label: "cross-coupled PMOS pair" }),
    ).toBe("pmosPair");
  });

  it("reads devices from whole label words", () => {
    expect(modelKindForBlock({ kind: "part", part: null, label: "MOM unit cap" })).toBe(
      "capacitor",
    );
    expect(modelKindForBlock({ kind: "part", part: null, label: "SAR ADC" })).toBe("adc");
    expect(modelKindForBlock({ kind: "part", part: null, label: "readout inverter" })).toBe(
      "inverter",
    );
  });

  it("respects a typed non-device part over label words", () => {
    // Methodology steps that merely mention a device stay honest boxes.
    expect(
      modelKindForBlock({
        kind: "part",
        part: "block",
        label: "Analyze decision voltage to isolate NMOS mismatch",
      }),
    ).toBeNull();
    expect(
      modelKindForBlock({ kind: "part", part: "process", label: "coupling capacitor sizing" }),
    ).toBeNull();
  });

  it("never matches substrings or bare transistor", () => {
    // "transistors" is not a whole device word; "not" inside text is
    // not an inverter; "ind" inside "winding" is not an inductor.
    expect(
      modelKindForBlock({ kind: "part", part: null, label: "transistors in the array" }),
    ).toBeNull();
    expect(
      modelKindForBlock({ kind: "part", part: null, label: "readout, not shown" }),
    ).toBeNull();
    expect(
      modelKindForBlock({ kind: "part", part: null, label: "winding loss" }),
    ).toBeNull();
    expect(modelKindForBlock({ kind: "part", part: null, label: "keeper switch" })).toBeNull();
  });
});

describe("buildComponentModel", () => {
  it.each(ALL_KINDS)("builds %s inside the unit footprint", (kind) => {
    const model = buildComponentModel(kind);
    model.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(model);

    expect(bounds.min.x).toBeGreaterThanOrEqual(-0.51);
    expect(bounds.max.x).toBeLessThanOrEqual(0.51);
    expect(bounds.min.z).toBeGreaterThanOrEqual(-0.51);
    expect(bounds.max.z).toBeLessThanOrEqual(0.51);
    expect(bounds.min.y).toBeGreaterThanOrEqual(-0.01);
    expect(bounds.max.y).toBeLessThanOrEqual(0.51);
  });

  it.each(ALL_KINDS)("builds %s from real meshes", (kind) => {
    const model = buildComponentModel(kind);
    let meshes = 0;
    model.traverse((child) => {
      if (child instanceof THREE.Mesh) meshes += 1;
    });

    expect(meshes).toBeGreaterThan(0);
    expect(modelMaterials(model).length).toBeGreaterThan(0);
  });

  it("mints fresh materials per build", () => {
    const first = new Set(modelMaterials(buildComponentModel("nmos")));
    const second = modelMaterials(buildComponentModel("nmos"));

    expect(second.length).toBeGreaterThan(0);
    for (const material of second) {
      expect(first.has(material)).toBe(false);
    }
  });

  it("gives NMOS and PMOS different diffusion colors", () => {
    const nColors = new Set(
      modelMaterials(buildComponentModel("nmos")).map((mat) => mat.color.getHex()),
    );
    const pColors = new Set(
      modelMaterials(buildComponentModel("pmos")).map((mat) => mat.color.getHex()),
    );

    expect(nColors.has(0x3d9950)).toBe(true);
    expect(pColors.has(0x8a63c8)).toBe(true);
  });
});
