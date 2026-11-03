import { describe, expect, it } from "vitest";
import { dark, light } from "../../diagram-engine/index.js";
import { sceneToThree } from "../../diagram-engine/three-adapter.js";
import { diagramsFixture } from "../../test/fixtures.ts";
import type { CircuitIRJson, MethodologyIRJson } from "../../lib/types.ts";
import {
  circuitHasPaperLayout,
  renderCircuitDiagram,
  renderMethodologyDiagram,
  renderStructureDiagram,
} from "./adapters.ts";

describe("diagram adapters", () => {
  it("renders the methodology fixture through the real engine", () => {
    const ir = diagramsFixture.methodology;
    if (!ir) throw new Error("fixture must carry a methodology IR");
    const result = renderMethodologyDiagram(ir);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.svg).toContain("Transformer encoder");
    expect(result.svg).toContain('data-node-id="m-check"');
  });

  it("fits methodology SVGs to provenance and decision text", () => {
    const ir = diagramsFixture.methodology;
    if (!ir) throw new Error("fixture must carry a methodology IR");
    const result = renderMethodologyDiagram(ir);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const groups =
      result.svg.match(/<g\b[^>]*data-node-id="[^"]+"[^>]*>[\s\S]*?<\/g>/g) ?? [];
    expect(groups).toHaveLength(4);
    // Only the assumed decision node is dashed; its diamond is enlarged.
    const dashed = groups.filter((group) =>
      group.includes('stroke-dasharray="5 4"'),
    );
    expect(dashed).toHaveLength(1);
    expect(dashed[0]).toContain('data-node-id="m-check"');
    expect(dashed[0]).toContain("<polygon");
  });

  it("renders the circuit fixture with clickable component ids", () => {
    const result = renderCircuitDiagram(diagramsFixture.circuits[0]);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.svg).toContain('data-id="m1"');
    expect(result.svg).toContain('data-id="r1"');
  });

  it("draws methodology-derived system blocks without unknown-type warnings", () => {
    // Derived circuits carry step kinds (model/store/...) as component
    // types: first-class system blocks, not unknown devices.
    const derived: CircuitIRJson = {
      version: 1,
      title: "derived",
      source: { figure_id: "methodology", page: 1 },
      components: [
        {
          id: "load",
          type: "input",
          label: "load",
          value: null,
          pins: { out: "e0" },
          pin_sides: { out: "right" },
          placement: null,
          confidence: 0.6,
          evidence: null,
        },
        {
          id: "train",
          type: "model",
          label: "train",
          value: null,
          pins: { in: "e0", out: "e1" },
          pin_sides: { in: "left", out: "right" },
          placement: null,
          confidence: 0.6,
          evidence: null,
        },
        {
          id: "score",
          type: "output",
          label: "score",
          value: null,
          pins: { in: "e1" },
          pin_sides: { in: "left" },
          placement: null,
          confidence: 0.6,
          evidence: null,
        },
      ],
      nets: [
        { id: "e0", label: "e0", role: "signal", global: false },
        { id: "e1", label: "e1", role: "signal", global: false },
      ],
      ports: [],
      subcircuits: [],
      layout: null,
    };
    const result = renderCircuitDiagram(derived);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.svg).toContain('data-id="train"');
    expect(
      result.validation.warnings.filter(
        (warning) => warning.code === "unknown_type",
      ),
    ).toEqual([]);
  });

  it("gives schematic labels a halo in the active theme background", () => {
    const lightResult = renderCircuitDiagram(diagramsFixture.circuits[0], {
      theme: light,
    });
    expect(lightResult.ok).toBe(true);
    if (!lightResult.ok) return;
    expect(lightResult.svg).toContain("paint-order:stroke");
    expect(lightResult.svg).toContain(`stroke:${light.bg}`);

    const darkResult = renderCircuitDiagram(diagramsFixture.circuits[0], {
      theme: dark,
    });
    expect(darkResult.ok).toBe(true);
    if (!darkResult.ok) return;
    expect(darkResult.svg).toContain(`stroke:${dark.bg}`);
  });

  it("builds a 3D scene whose meshes carry block ids", () => {
    const structure = diagramsFixture.structure;
    if (!structure) throw new Error("fixture must carry a structure IR");
    const result = renderStructureDiagram(structure);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.scene.boxes.length).toBeGreaterThanOrEqual(2);
    const group = sceneToThree(result.scene);
    const ids = group.children.map(
      (child) => (child.userData as { id?: unknown }).id,
    );
    expect(ids).toContain("chip");
    expect(ids).toContain("peri");
    expect(ids.some((id) => typeof id === "string" && id.startsWith("arr["))).toBe(true);
  });

  it("refuses thin IRs instead of inventing diagrams", () => {
    const thinMethodology: MethodologyIRJson = {
      version: 1,
      title: "thin",
      groups: [],
      nodes: [
        {
          id: "only",
          label: "Only",
          kind: "process",
          group: null,
          detail: null,
          params: {},
          confidence: 0.9,
          evidence: null,
        },
      ],
      edges: [],
    };
    const methodology = renderMethodologyDiagram(thinMethodology);
    expect(methodology.ok).toBe(false);
    if (methodology.ok) return;
    expect(methodology.reason).toContain("too little structure");

    const circuit = renderCircuitDiagram({
      ...diagramsFixture.circuits[0],
      components: [diagramsFixture.circuits[0].components[0]],
    });
    expect(circuit.ok).toBe(false);

    const structure = renderStructureDiagram({
      version: 1,
      title: "empty",
      root: {
        id: "root",
        label: "root",
        kind: "region",
        count: null,
        dims: null,
        pos: null,
        part: null,
        tensor_shape: null,
        children: [],
        confidence: 0.9,
        evidence: null,
      },
    });
    expect(structure.ok).toBe(false);
  });

  it("stringifies non-scalar methodology params for the engine", () => {
    const ir = diagramsFixture.methodology;
    if (!ir) throw new Error("fixture must carry a methodology IR");
    const result = renderMethodologyDiagram({
      ...ir,
      nodes: [
        ...ir.nodes.slice(0, 3),
        {
          ...ir.nodes[3],
          id: "m-output",
          label: "Class token output",
          kind: "output",
          group: null,
          detail: null,
          params: { layers: 12, cached: true, shape: { h: 14, w: 14 } },
          confidence: 0.8,
          evidence: { page: 5, figure_id: null, quote: null },
        },
      ],
    });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.svg).toContain("layers: 12");
    expect(result.svg).toContain("cached: true");
    expect(result.svg).toContain("shape:");
  });

  it("detects paper layout only when every component has placement", () => {
    expect(circuitHasPaperLayout(diagramsFixture.circuits[0])).toBe(true);
    expect(
      circuitHasPaperLayout({
        ...diagramsFixture.circuits[0],
        components: [
          { ...diagramsFixture.circuits[0].components[0], placement: null },
          ...diagramsFixture.circuits[0].components.slice(1),
        ],
      }),
    ).toBe(false);
    expect(
      circuitHasPaperLayout({ ...diagramsFixture.circuits[0], components: [] }),
    ).toBe(false);
  });
});
