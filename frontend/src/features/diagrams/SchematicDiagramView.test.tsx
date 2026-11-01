import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { diagramsFixture } from "../../test/fixtures.ts";
import { useSchematicSandbox } from "../../lib/store.ts";
import type { CircuitIRJson } from "../../lib/types.ts";
import { SchematicDiagramView } from "./SchematicDiagramView.tsx";

const nodeLabels = new Map([
  ["input", "Image"],
  ["encoder", "Transformer encoder"],
]);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function circuit(): CircuitIRJson {
  return diagramsFixture.circuits[0];
}

describe("SchematicDiagramView", () => {
  it("renders the engine SVG with counts and no picker for one circuit", () => {
    render(
      <SchematicDiagramView
        circuits={[circuit()]}
        validation={diagramsFixture.validation}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    const canvas = screen.getByRole("group", { name: "Schematic diagram" });
    expect(canvas.querySelectorAll("[data-id]")).toHaveLength(3);
    expect(screen.getByText("2 from paper · 1 assumed")).toBeInTheDocument();
    expect(screen.queryByRole("tablist", { name: "Circuits" })).not.toBeInTheDocument();
  });

  it("opens the clicked component in the Inspector", () => {
    const onSelect = vi.fn();
    render(
      <SchematicDiagramView
        circuits={[circuit()]}
        validation={diagramsFixture.validation}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={onSelect}
      />,
      { wrapper },
    );
    // The walkthrough already selected the first step on mount; the
    // click must move the selection to the clicked component.
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ view: "schematic", elementId: "m1" }),
    );
    const component = document.querySelector('[data-id="r1"]');
    if (!component) throw new Error("engine must stamp data-id");
    fireEvent.click(component.querySelector("path") ?? component);
    expect(onSelect).toHaveBeenLastCalledWith(
      expect.objectContaining({ view: "schematic", elementId: "r1" }),
    );
  });

  it("offers the signal-flow walkthrough", () => {
    render(
      <SchematicDiagramView
        circuits={[circuit()]}
        validation={diagramsFixture.validation}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    expect(
      screen.getByRole("group", { name: "Signal flow walkthrough" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Step 1 of 3 — M1 (nmos)")).toBeInTheDocument();
  });

  it("flags auto-layout as illustrative when placement is missing", () => {
    render(
      <SchematicDiagramView
        circuits={[
          {
            ...circuit(),
            components: circuit().components.map((entry) => ({ ...entry, placement: null })),
          },
        ]}
        validation={diagramsFixture.validation}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    // Header badge plus the legend entry.
    expect(screen.getAllByText("illustrative")).toHaveLength(2);
    expect(screen.getByText(/Illustrative layout/)).toBeInTheDocument();
  });

  it("switches between circuits with the picker", async () => {
    const user = userEvent.setup();
    const second: CircuitIRJson = {
      ...circuit(),
      title: "Second cell",
      source: { figure_id: "other-fig", page: 3 },
    };
    render(
      <SchematicDiagramView
        circuits={[circuit(), second]}
        validation={diagramsFixture.validation}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    const picker = screen.getByRole("tablist", { name: "Circuits" });
    expect(screen.getByRole("heading", { name: "Test cell" })).toBeInTheDocument();
    await user.click(within(picker).getByRole("tab", { name: "Second cell" }));
    expect(screen.getByRole("heading", { name: "Second cell" })).toBeInTheDocument();
  });

  it("falls back to the paper figure when no circuit was extracted", async () => {
    render(
      <SchematicDiagramView
        circuits={[]}
        validation={diagramsFixture.validation}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    expect(
      await screen.findByText(/the paper's figures yielded nothing suitable/),
    ).toBeInTheDocument();
    expect(await screen.findByAltText("Model overview.")).toBeInTheDocument();
    expect(document.querySelector("svg")).toBeNull();
  });

  it("falls back with the engine reason for a thin circuit", async () => {
    render(
      <SchematicDiagramView
        circuits={[{ ...circuit(), components: circuit().components.slice(0, 1) }]}
        validation={diagramsFixture.validation}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    expect(await screen.findByText(/too few components/)).toBeInTheDocument();
    expect(await screen.findByAltText("Model overview.")).toBeInTheDocument();
  });

  it("merges sandbox trials into the rendered circuit and tracks the figure", () => {
    useSchematicSandbox.setState({
      items: [
        {
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
        },
      ],
      activeFigureId: null,
    });
    try {
      render(
        <SchematicDiagramView
          circuits={[circuit()]}
          validation={diagramsFixture.validation}
          projectId="project-1"
          graphId="graph-1"
          nodeLabels={nodeLabels}
          onSelect={() => {}}
        />,
        { wrapper },
      );
      const canvas = screen.getByRole("group", { name: "Schematic diagram" });
      expect(canvas.querySelectorAll("[data-id]")).toHaveLength(4);
      expect(canvas.querySelector('[data-id="try-k1"]')).not.toBeNull();
      // The trial carries no evidence: counted assumed.
      expect(screen.getByText("2 from paper · 2 assumed")).toBeInTheDocument();
      expect(screen.getByRole("region", { name: "Trying in schematic" })).toBeInTheDocument();
      expect(useSchematicSandbox.getState().activeFigureId).toBe(
        circuit().source.figure_id,
      );
    } finally {
      useSchematicSandbox.setState({ items: [], activeFigureId: null });
    }
  });
});
