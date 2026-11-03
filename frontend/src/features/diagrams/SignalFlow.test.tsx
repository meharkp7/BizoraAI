import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { diagramsFixture } from "../../test/fixtures.ts";
import type { CircuitIRJson } from "../../lib/types.ts";
import { renderCircuitDiagram } from "./adapters.ts";
import { SignalFlow } from "./SignalFlow.tsx";

function circuit(): CircuitIRJson {
  return diagramsFixture.circuits[0];
}

function svg(): string {
  const result = renderCircuitDiagram(circuit());
  if (!result.ok) throw new Error("fixture circuit must render");
  return result.svg;
}

function netLabels(): Map<string, string> {
  return new Map(circuit().nets.map((net) => [net.id, net.label] as const));
}

describe("SignalFlow", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the schematic at its drawn size, never shrunk to fit", () => {
    render(<SignalFlow circuit={circuit()} svg={svg()} netLabels={netLabels()} onSelect={() => {}} />);
    // A wide auto-layout shrunk to the frame would be unreadable: the
    // frame scrolls at natural size instead (see canvasNatural).
    const stage = screen.getByRole("group", { name: "Schematic diagram" });
    expect(stage.className).toMatch(/canvasNatural/);
    expect(stage.className).toMatch(/canvas/);
  });

  it("scrolls the active step into view without yanking the page", async () => {
    const user = userEvent.setup();
    const scroll = vi.fn();
    const proto = Element.prototype as unknown as Record<string, unknown>;
    const previous = proto.scrollIntoView;
    proto.scrollIntoView = scroll;
    try {
      render(<SignalFlow circuit={circuit()} svg={svg()} netLabels={netLabels()} onSelect={() => {}} />);
      expect(scroll).toHaveBeenCalledTimes(1);
      await user.click(screen.getByRole("button", { name: "Next" }));
      expect(scroll).toHaveBeenCalledTimes(2);
      expect(scroll).toHaveBeenLastCalledWith(
        expect.objectContaining({ block: "nearest", inline: "center" }),
      );
    } finally {
      if (previous === undefined) delete proto.scrollIntoView;
      else proto.scrollIntoView = previous;
    }
  });

  it("opens the first step on mount and rings its group", () => {
    const onSelect = vi.fn();
    render(<SignalFlow circuit={circuit()} svg={svg()} netLabels={netLabels()} onSelect={onSelect} />);
    expect(screen.getByText("Step 1 of 3 — M1 (nmos)")).toBeInTheDocument();
    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ view: "schematic", elementId: "m1" }),
    );
    expect(document.querySelector('[data-id="m1"]')?.classList.contains("flow-active")).toBe(true);
    expect(document.querySelector('[data-id="r1"]')?.classList.contains("flow-active")).toBe(false);
  });

  it("steps forward and back through connectivity order", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<SignalFlow circuit={circuit()} svg={svg()} netLabels={netLabels()} onSelect={onSelect} />);
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Step 2 of 3 — R1 (resistor)")).toBeInTheDocument();
    expect(onSelect).toHaveBeenLastCalledWith(
      expect.objectContaining({ elementId: "r1" }),
    );
    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(screen.getByText("Step 1 of 3 — M1 (nmos)")).toBeInTheDocument();
  });

  it("jumps the walkthrough when a component is clicked", () => {
    const onSelect = vi.fn();
    render(<SignalFlow circuit={circuit()} svg={svg()} netLabels={netLabels()} onSelect={onSelect} />);
    const group = document.querySelector('[data-id="g1"]');
    if (!group) throw new Error("engine must stamp data-id");
    fireEvent.click(group);
    expect(screen.getByText("Step 3 of 3 — GND (ground)")).toBeInTheDocument();
    expect(onSelect).toHaveBeenLastCalledWith(
      expect.objectContaining({ elementId: "g1" }),
    );
  });

  it("plays through the steps and stops at the end", () => {
    vi.useFakeTimers();
    const onSelect = vi.fn();
    render(<SignalFlow circuit={circuit()} svg={svg()} netLabels={netLabels()} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(2600);
    });
    expect(screen.getByText("Step 2 of 3 — R1 (resistor)")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(2600);
    });
    expect(screen.getByText("Step 3 of 3 — GND (ground)")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(2600);
    });
    // Ended: back to Play, staying on the last step.
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    expect(screen.getByText("Step 3 of 3 — GND (ground)")).toBeInTheDocument();
    expect(onSelect).toHaveBeenLastCalledWith(
      expect.objectContaining({ elementId: "g1" }),
    );
  });

  it("rides an explainer tag on the dot and fades across separate branches", () => {
    vi.useFakeTimers();
    const rect = (x: number, y: number, w: number, h: number): DOMRect =>
      ({
        x,
        y,
        width: w,
        height: h,
        top: y,
        left: x,
        right: x + w,
        bottom: y + h,
        toJSON: () => ({}),
      }) as DOMRect;
    // r1 and g1 sit far from the drawn copper, so both legs fade
    // instead of flying: deterministic without touching rAF.
    const spy = vi
      .spyOn(Element.prototype, "getBoundingClientRect")
      .mockImplementation(function (this: Element) {
        const id =
          typeof this.getAttribute === "function"
            ? this.getAttribute("data-id")
            : null;
        if (id === "m1") return rect(10, 10, 20, 20);
        if (id === "r1") return rect(5000, 10, 20, 20);
        if (id === "g1") return rect(5000, 5000, 20, 20);
        return rect(0, 0, 600, 600);
      });
    try {
      const quoted: CircuitIRJson = {
        ...circuit(),
        components: circuit().components.map((entry) =>
          entry.id === "r1"
            ? {
                ...entry,
                evidence: {
                  figure_id: "fig1",
                  bbox: null,
                  quote: "The resistor sets the bitline load current.",
                },
              }
            : entry,
        ),
      };
      render(
        <SignalFlow circuit={quoted} svg={svg()} netLabels={netLabels()} onSelect={() => {}} />,
      );
      expect(screen.getByTestId("flow-tag")).toHaveTextContent("Step 1 of 3 — M1");
      expect(screen.getByTestId("flow-tag")).toHaveTextContent("Flow starts here");
      expect(screen.getByTestId("flow-tag")).not.toHaveTextContent("→");
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      expect(screen.getByTestId("flow-tag")).toHaveTextContent("Step 2 of 3 — R1");
      expect(screen.getByTestId("flow-tag")).toHaveTextContent("M1 → R1");
      expect(screen.getByTestId("flow-tag")).toHaveTextContent("via OUT");
      expect(screen.getByTestId("flow-tag")).toHaveTextContent(
        "The resistor sets the bitline load current.",
      );
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      expect(screen.getByTestId("flow-tag")).toHaveTextContent("R1 → GND");
      expect(screen.getByTestId("flow-pulse").className).toMatch(/dimmed/);
      act(() => {
        vi.advanceTimersByTime(140);
      });
      const pulse = screen.getByTestId("flow-pulse");
      expect(pulse.className).not.toMatch(/dimmed/);
      expect(pulse.style.left).toBe("5010px");
      expect(pulse.style.top).toBe("5010px");
      expect(screen.getByTestId("flow-tag")).toHaveTextContent("Separate branch");
    } finally {
      spy.mockRestore();
    }
  });

  it("pauses on demand", () => {
    vi.useFakeTimers();
    render(
      <SignalFlow circuit={circuit()} svg={svg()} netLabels={netLabels()} onSelect={() => {}} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    act(() => {
      vi.advanceTimersByTime(5200);
    });
    expect(screen.getByText("Step 1 of 3 — M1 (nmos)")).toBeInTheDocument();
  });
});
