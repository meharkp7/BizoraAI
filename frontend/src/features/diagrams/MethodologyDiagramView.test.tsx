import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { diagramsFixture } from "../../test/fixtures.ts";
import { MethodologyDiagramView } from "./MethodologyDiagramView.tsx";

const nodeLabels = new Map([
  ["input", "Image"],
  ["encoder", "Transformer encoder"],
]);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function methodology() {
  const ir = diagramsFixture.methodology;
  if (!ir) throw new Error("fixture must carry a methodology IR");
  return ir;
}

describe("MethodologyDiagramView", () => {
  it("renders the engine SVG with counts and the provenance key", () => {
    render(
      <MethodologyDiagramView
        methodology={methodology()}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        paperId="paper-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    const canvas = screen.getByRole("group", { name: "Methodology diagram" });
    expect(canvas.querySelectorAll("[data-node-id]")).toHaveLength(4);
    // Only the layers node carries params: exactly one what-if badge.
    expect(canvas.querySelectorAll(".whatif")).toHaveLength(1);
    expect(
      canvas.querySelector('[data-node-id="m-encode"] .whatif-dot'),
    ).not.toBeNull();
    expect(screen.getByText("3 from paper · 1 assumed")).toBeInTheDocument();
    expect(screen.getAllByRole("term")).toHaveLength(3);
    expect(screen.getByText("computed layout, not in the paper")).toBeInTheDocument();
  });

  it("opens the clicked node in the Inspector", () => {
    const onSelect = vi.fn();
    render(
      <MethodologyDiagramView
        methodology={methodology()}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        paperId="paper-1"
        nodeLabels={nodeLabels}
        onSelect={onSelect}
      />,
      { wrapper },
    );
    const node = document.querySelector('[data-node-id="m-encode"]');
    if (!node) throw new Error("engine must stamp data-node-id");
    fireEvent.click(node.querySelector("text") ?? node);
    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ view: "methodology", elementId: "m-encode" }),
    );
  });

  it("lays out vertically by default and switches on request", () => {
    render(
      <MethodologyDiagramView
        methodology={methodology()}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        paperId="paper-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    const canvas = screen.getByRole("group", { name: "Methodology diagram" });
    const viewBox = (canvas.querySelector("svg")?.getAttribute("viewBox") ?? "")
      .split(" ")
      .map(Number);
    // Vertical flow: taller than wide, nodes at full text size.
    expect(viewBox[3]).toBeGreaterThan(viewBox[2]);

    fireEvent.click(screen.getByRole("button", { name: "Horizontal" }));
    const wide = (canvas.querySelector("svg")?.getAttribute("viewBox") ?? "")
      .split(" ")
      .map(Number);
    expect(wide[2]).toBeGreaterThan(wide[3]);
  });

  it("ignores clicks outside nodes", () => {
    const onSelect = vi.fn();
    render(
      <MethodologyDiagramView
        methodology={methodology()}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        paperId="paper-1"
        nodeLabels={nodeLabels}
        onSelect={onSelect}
      />,
      { wrapper },
    );
    fireEvent.click(screen.getByRole("group", { name: "Methodology diagram" }));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("falls back to the paper figure when no IR was extracted", async () => {
    render(
      <MethodologyDiagramView
        methodology={null}
        sourceFigureId={null}
        warnings={["flow figure was a plot"]}
        projectId="project-1"
        graphId="graph-1"
        paperId="paper-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    expect(
      await screen.findByText(/the paper's figures yielded nothing suitable/),
    ).toBeInTheDocument();
    // The paper's own figure, not a placeholder diagram.
    expect(await screen.findByAltText("Model overview.")).toBeInTheDocument();
    expect(screen.getByText("flow figure was a plot")).toBeInTheDocument();
    expect(document.querySelector("svg")).toBeNull();
  });

  it("falls back with the engine reason when the IR is too thin", async () => {
    render(
      <MethodologyDiagramView
        methodology={{ ...methodology(), nodes: methodology().nodes.slice(0, 1), edges: [] }}
        sourceFigureId={null}
        warnings={[]}
        projectId="project-1"
        graphId="graph-1"
        paperId="paper-1"
        nodeLabels={nodeLabels}
        onSelect={() => {}}
      />,
      { wrapper },
    );
    expect(await screen.findByText(/too little structure/)).toBeInTheDocument();
    expect(await screen.findByAltText("Model overview.")).toBeInTheDocument();
  });
});
