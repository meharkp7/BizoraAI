import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSchematicSandbox } from "../../lib/store.ts";
import { diagramsFixture } from "../../test/fixtures.ts";
import { SandboxPanel } from "./SandboxPanel.tsx";
import type { SandboxItem } from "./schematicSandbox.ts";

function item(overrides: Partial<SandboxItem> = {}): SandboxItem {
  const circuit = diagramsFixture.circuits[0];
  if (!circuit) throw new Error("fixture must carry a circuit");
  return {
    key: "k1",
    figureId: circuit.source.figure_id,
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

function nets() {
  const circuit = diagramsFixture.circuits[0];
  if (!circuit) throw new Error("fixture must carry a circuit");
  return circuit.nets;
}

function figureId(): string {
  const circuit = diagramsFixture.circuits[0];
  if (!circuit) throw new Error("fixture must carry a circuit");
  return circuit.source.figure_id;
}

beforeEach(() => {
  useSchematicSandbox.setState({ items: [], activeFigureId: null });
});

describe("SandboxPanel", () => {
  it("renders nothing without trials on this figure", () => {
    useSchematicSandbox.setState({ items: [item({ figureId: "other" })] });
    const { container } = render(<SandboxPanel figureId={figureId()} nets={nets()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("wires pins to nets and removes trials", () => {
    useSchematicSandbox.setState({ items: [item()] });
    render(<SandboxPanel figureId={figureId()} nets={nets()} />);
    expect(screen.getByText("Trying in schematic (1)")).toBeInTheDocument();
    expect(screen.getByText(/Local trial only/)).toBeInTheDocument();
    // Positional mapping is visible: designator 1 drives symbol pin a.
    expect(screen.getByText("1 → a")).toBeInTheDocument();

    const net = nets()[0];
    if (!net) throw new Error("fixture circuit needs a net");
    fireEvent.change(screen.getByLabelText("10k resistor pin 1 net"), {
      target: { value: net.id },
    });
    expect(useSchematicSandbox.getState().items[0]?.pinNets).toEqual({ 1: net.id });

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(useSchematicSandbox.getState().items).toHaveLength(0);
  });

  it("warns about supply shorts and persists trials", async () => {
    useSchematicSandbox.setState({
      items: [item({ pinNets: { 1: "vdd", 2: "gnd" } })],
    });
    render(
      <SandboxPanel
        figureId={figureId()}
        nets={[
          { id: "vdd", label: "VDD", role: "supply", global: true },
          { id: "gnd", label: "GND", role: "ground", global: true },
        ]}
      />,
    );
    expect(screen.getByText("Shorts a supply net to ground.")).toBeInTheDocument();
    expect(window.localStorage.getItem("bizora.sandbox.v1")).toContain("10k resistor");

    vi.resetModules();
    const reloaded = await import("../../lib/store.ts");
    try {
      expect(reloaded.useSchematicSandbox.getState().items).toHaveLength(1);
    } finally {
      window.localStorage.removeItem("bizora.sandbox.v1");
    }
  });
});
