import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { diagramsFixture } from "../../test/fixtures.ts";
import { StructureDiagramView } from "./StructureDiagramView.tsx";

const nodeLabels = new Map([
  ["input", "Image"],
  ["encoder", "Transformer encoder"],
]);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function structure() {
  const ir = diagramsFixture.structure;
  if (!ir) throw new Error("fixture must carry a structure IR");
  return ir;
}

describe("StructureDiagramView", () => {
  it("reports honestly when WebGL is unavailable instead of faking 3D", () => {
    // jsdom has no WebGL context: the view must say so, not draw a stand-in.
    render(
      <StructureDiagramView
        structure={structure()}
        circuits={[]}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    expect(screen.getByRole("heading", { name: "Test chip" })).toBeInTheDocument();
    expect(screen.getByText("2 from paper · 2 assumed")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("3D needs WebGL");
  });

  it("offers the cell interior when the engine builds a detail scene", () => {
    const base = structure();
    const array = base.root.children[0];
    const cell = array.children[0];
    const parts = ["nmos", "pmos"].map((id) => ({
      ...cell,
      id: `part-${id}`,
      label: id.toUpperCase(),
      kind: "part",
      children: [],
    }));
    const detailed = {
      ...base,
      root: {
        ...base.root,
        children: [
          { ...array, children: [{ ...cell, children: parts }] },
          ...base.root.children.slice(1),
        ],
      },
    };
    render(
      <StructureDiagramView
        structure={detailed}
        circuits={[]}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    const toggle = within(screen.getByRole("group", { name: "Structure scene" }));
    expect(
      toggle.getByRole("button", { name: "Full structure" }),
    ).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(toggle.getByRole("button", { name: "Cell interior" }));
    expect(
      toggle.getByRole("button", { name: "Cell interior" }),
    ).toHaveAttribute("aria-pressed", "true");
    // Generic identity caption + shape legend for the dressed scene.
    expect(
      screen.getByText(/Shapes follow the IR kind and plates name each part/),
    ).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Part family legend" })).toBeInTheDocument();
  });

  it("hides the scene toggle when cells carry no interior", () => {
    render(
      <StructureDiagramView
        structure={structure()}
        circuits={[]}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    expect(screen.queryByRole("group", { name: "Structure scene" })).toBeNull();
  });

  it("falls back to the paper figure when no structure was extracted", async () => {
    render(
      <StructureDiagramView
        structure={null}
        circuits={[]}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={vi.fn()}
      />,
      { wrapper },
    );
    expect(await screen.findByText(/the paper's figures yielded nothing suitable/)).toBeInTheDocument();
    expect(await screen.findByAltText("Model overview.")).toBeInTheDocument();
    expect(document.querySelector("svg")).toBeNull();
  });

  it("falls back with the engine reason for an undrawable structure", async () => {
    render(
      <StructureDiagramView
        structure={{
          version: 1,
          title: "Empty",
          root: { ...structure().root, children: [] },
        }}
        circuits={[]}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={vi.fn()}
      />,
      { wrapper },
    );
    expect(await screen.findByText(/no physical structure/)).toBeInTheDocument();
    expect(await screen.findByAltText("Model overview.")).toBeInTheDocument();
  });

  it("shows the schematic circuit as its own scene", () => {
    render(
      <StructureDiagramView
        structure={structure()}
        circuits={diagramsFixture.circuits}
        sourceFigureId={null}
        warnings={["chip warning"]}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    const toggle = within(screen.getByRole("group", { name: "Structure scene" }));
    // Opens on the circuit build: root + M1 + GND from paper, R1
    // assumed, and chip warnings hidden here.
    expect(
      toggle.getByRole("button", { name: "Circuit 3D" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("3 from paper · 1 assumed")).toBeInTheDocument();
    expect(screen.queryByText("chip warning")).toBeNull();
    expect(
      screen.getByText(/Shapes follow the IR kind and plates name each part/),
    ).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Part family legend" })).toBeInTheDocument();
    fireEvent.click(toggle.getByRole("button", { name: "Full structure" }));
    expect(screen.getByText("chip warning")).toBeInTheDocument();
  });

  it("picks between circuit figures for the circuit scene", () => {
    const second = {
      ...diagramsFixture.circuits[0],
      title: "Second cell",
      source: { figure_id: "fig-2", page: 3 },
    };
    render(
      <StructureDiagramView
        structure={structure()}
        circuits={[diagramsFixture.circuits[0], second]}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    const toggle = within(screen.getByRole("group", { name: "Structure scene" }));
    fireEvent.click(toggle.getByRole("button", { name: "Circuit 3D" }));
    expect(screen.getByRole("heading", { name: "Test cell" })).toBeInTheDocument();
    const picker = within(screen.getByRole("tablist", { name: "Circuits" }));
    fireEvent.click(picker.getByRole("tab", { name: "Second cell" }));
    expect(screen.getByRole("heading", { name: "Second cell" })).toBeInTheDocument();
  });

  it("hides the circuit scene when the circuit is too thin", () => {
    const thin = {
      ...diagramsFixture.circuits[0],
      components: [diagramsFixture.circuits[0].components[0]],
    };
    render(
      <StructureDiagramView
        structure={structure()}
        circuits={[thin]}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    // No detail scene in the fixture either: no toggle at all.
    expect(screen.queryByRole("group", { name: "Structure scene" })).toBeNull();
  });

  it("opens on the circuit build when one renders", () => {
    render(
      <StructureDiagramView
        structure={structure()}
        circuits={diagramsFixture.circuits}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    const toggle = within(screen.getByRole("group", { name: "Structure scene" }));
    expect(
      toggle.getByRole("button", { name: "Circuit 3D" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { name: "Test cell" })).toBeInTheDocument();
  });

  it("lists parts and spotlights one into the Inspector", () => {
    const onSelect = vi.fn();
    render(
      <StructureDiagramView
        structure={structure()}
        circuits={[]}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={onSelect}
      />,
      { wrapper },
    );
    const parts = within(screen.getByRole("group", { name: "Parts in this scene" }));
    fireEvent.click(parts.getByRole("button", { name: "cell array" }));
    expect(
      parts.getByRole("button", { name: "cell array" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ view: "structure", elementId: "arr" }),
    );
  });

  it("clears the spotlight when the scene changes", () => {
    const base = structure();
    const array = base.root.children[0];
    const cell = array.children[0];
    const parts = ["nmos", "pmos"].map((id) => ({
      ...cell,
      id: `part-${id}`,
      label: id.toUpperCase(),
      kind: "part",
      children: [],
    }));
    const detailed = {
      ...base,
      root: {
        ...base.root,
        children: [
          { ...array, children: [{ ...cell, children: parts }] },
          ...base.root.children.slice(1),
        ],
      },
    };
    render(
      <StructureDiagramView
        structure={detailed}
        circuits={[]}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    const list = within(screen.getByRole("group", { name: "Parts in this scene" }));
    fireEvent.click(list.getByRole("button", { name: "cell array" }));
    expect(
      list.getByRole("button", { name: "cell array" }),
    ).toHaveAttribute("aria-pressed", "true");
    const toggle = within(screen.getByRole("group", { name: "Structure scene" }));
    fireEvent.click(toggle.getByRole("button", { name: "Cell interior" }));
    // The detail scene shows the repeated cell's own parts now.
    const detailParts = within(screen.getByRole("group", { name: "Parts in this scene" }));
    expect(detailParts.queryByRole("button", { name: "cell array" })).toBeNull();
    expect(detailParts.getByRole("button", { name: "NMOS" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });
});
