import { describe, expect, it } from "vitest";
import { diagramsFixture } from "../../test/fixtures.ts";
import type { CircuitIRJson, ComponentDetail } from "../../lib/types.ts";
import type { SandboxItem } from "./schematicSandbox.ts";
import {
  applySandboxItems,
  parseTrialsExport,
  sandboxEngineType,
  sandboxPinMap,
  sandboxSymbolPins,
  sandboxValue,
  sandboxWarnings,
  serializeTrials,
} from "./schematicSandbox.ts";

function detail(overrides: Partial<ComponentDetail> = {}): ComponentDetail {
  return {
    component_id: "c1",
    domain: "electronics",
    entity_type: "resistor",
    category: "passive",
    kind: "resistor",
    label: "10k resistor",
    generic: false,
    manufacturer: null,
    part_number: null,
    headline: "h",
    symbol: "resistor",
    description: "d",
    datasheet_url: null,
    reference_url: null,
    specs: [],
    pinout: [],
    interfaces: [],
    constraints: {},
    config_schema: [],
    default_config: {},
    evidence: [],
    ...overrides,
  };
}

function item(overrides: Partial<SandboxItem> = {}): SandboxItem {
  return {
    key: "k1",
    figureId: circuit().source.figure_id,
    componentId: "c1",
    label: "10k resistor",
    engineType: "resistor",
    value: "10 kΩ",
    pinout: [
      { designator: "1", name: "A" },
      { designator: "2", name: "B" },
    ],
    pinNets: {},
    ...overrides,
  };
}

function circuit(): CircuitIRJson {
  const found = diagramsFixture.circuits[0];
  if (!found) throw new Error("fixture must carry a circuit");
  return found;
}

describe("sandboxEngineType", () => {
  it("matches exact engine types and aliases", () => {
    expect(sandboxEngineType(detail({ kind: "resistor" }))).toBe("resistor");
    expect(sandboxEngineType(detail({ kind: "nmos", entity_type: "x" }))).toBe("nmos");
    expect(sandboxEngineType(detail({ kind: "unknown", entity_type: "cap" }))).toBe(
      "capacitor",
    );
    expect(sandboxEngineType(detail({ kind: "unknown", entity_type: "x", category: "y", label: "power inductor 10uH" }))).toBe(
      "inductor",
    );
  });

  it("falls back to a trial block instead of a wrong symbol", () => {
    expect(
      sandboxEngineType(detail({ kind: "bjt", entity_type: "transistor", category: "discrete", label: "2N3904 NPN" })),
    ).toBe("trial:bjt");
  });
});

describe("sandboxPinMap", () => {
  it("maps positionally onto real symbol pins", () => {
    expect(sandboxSymbolPins("resistor")).toEqual(["a", "b"]);
    expect(
      sandboxPinMap("resistor", [
        { designator: "1", name: "A" },
        { designator: "2", name: "B" },
        { designator: "3", name: "extra" },
      ]),
    ).toEqual([
      { designator: "1", symbolPin: "a" },
      { designator: "2", symbolPin: "b" },
    ]);
  });

  it("passes every pin through for the generic block", () => {
    expect(
      sandboxPinMap("trial:bjt", [
        { designator: "E", name: "emitter" },
        { designator: "B", name: "base" },
        { designator: "C", name: "collector" },
      ]),
    ).toEqual([
      { designator: "E", symbolPin: "E" },
      { designator: "B", symbolPin: "B" },
      { designator: "C", symbolPin: "C" },
    ]);
  });
});

describe("sandboxValue", () => {
  it("reads a display value from catalog specs", () => {
    expect(
      sandboxValue(detail({ specs: [{ name: "Resistance", value: "10k", unit: "Ω", typical: true }] })),
    ).toBe("10k Ω");
    expect(sandboxValue(detail({ specs: [{ name: "Package", value: "0603", unit: null, typical: true }] }))).toBeNull();
  });
});

describe("applySandboxItems", () => {
  it("merges trials below the paper rows with mapped pins only", () => {
    const base = circuit();
    const net = base.nets[0];
    if (!net) throw new Error("fixture circuit needs a net");
    const merged = applySandboxItems(base, [
      item({ pinNets: { 1: net.id, 2: "no-such-net" } }),
      item({ key: "k2", figureId: "other-fig", pinNets: { 1: net.id } }),
    ]);
    expect(merged.components).toHaveLength(base.components.length + 1);
    const trial = merged.components[merged.components.length - 1];
    if (!trial) throw new Error("expected a trial component");
    expect(trial.id).toBe("try-k1");
    expect(trial.label).toContain("trial");
    expect(trial.evidence).toBeNull();
    // Wired pin joins the paper net; the unknown net falls back to a
    // private open stub instead of shorting or vanishing.
    expect(trial.pins).toEqual({ a: net.id, b: "try-open-try-k1-b" });
    expect(merged.nets.map((entry) => entry.id)).toContain("try-open-try-k1-b");
    const maxY = Math.max(
      ...base.components.map((c) => c.placement?.y ?? Number.NEGATIVE_INFINITY),
    );
    expect(trial.placement?.y).toBeGreaterThan(maxY);
  });

  it("returns the circuit untouched when nothing applies", () => {
    const base = circuit();
    expect(applySandboxItems(base, [])).toBe(base);
    expect(applySandboxItems(base, [item({ figureId: "other" })])).toBe(base);
  });
});

describe("sandboxWarnings", () => {
  const nets = [
    { id: "vdd", role: "supply" },
    { id: "vdd2", role: "supply" },
    { id: "gnd", role: "ground" },
    { id: "o", role: "signal" },
  ];

  it("flags supply-to-ground shorts and tied rails", () => {
    expect(sandboxWarnings(item({ pinNets: { 1: "vdd", 2: "gnd" } }), nets)).toEqual([
      "Shorts a supply net to ground.",
    ]);
    expect(sandboxWarnings(item({ pinNets: { 1: "vdd", 2: "vdd2" } }), nets)).toEqual([
      "Ties two supply rails together.",
    ]);
  });

  it("stays silent for sane wiring and unknown nets", () => {
    expect(sandboxWarnings(item({ pinNets: { 1: "o", 2: "gnd" } }), nets)).toEqual([]);
    expect(sandboxWarnings(item({ pinNets: {} }), nets)).toEqual([]);
    expect(sandboxWarnings(item({ pinNets: { 1: "nope" } }), nets)).toEqual([]);
  });
});

describe("trial export", () => {
  it("round-trips trials through JSON", () => {
    const exported = serializeTrials([item({ pinNets: { 1: "o" } })]);
    const restored = parseTrialsExport(exported, "fig-9");
    expect(restored).toHaveLength(1);
    expect(restored[0]).toMatchObject({
      figureId: "fig-9",
      componentId: "c1",
      label: "10k resistor",
      engineType: "resistor",
      pinNets: { 1: "o" },
    });
    expect(restored[0]?.key).not.toBe("k1");
  });

  it("rejects anything that isn't a trial export", () => {
    expect(() => parseTrialsExport("nope{", "fig")).toThrow("not a trial export");
    expect(() => parseTrialsExport('{"version":99,"items":[]}', "fig")).toThrow(
      "not a trial export",
    );
    expect(() => parseTrialsExport('{"version":1,"items":[{"label":"x"}]}', "fig")).toThrow(
      "not a trial export",
    );
  });
});
