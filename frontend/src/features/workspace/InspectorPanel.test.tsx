import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { entitiesFixture, graphFixture } from "../../test/fixtures.ts";
import { InspectorPanel } from "./InspectorPanel.tsx";

describe("InspectorPanel replace form", () => {
  it("submits a component replacement for the selected node", () => {
    const onReplaceNode = vi.fn();
    const node = graphFixture.nodes[1];
    render(
      <InspectorPanel
        node={node}
        edge={null}
        formatShape={() => "—"}
        onReplaceNode={onReplaceNode}
      />,
    );

    fireEvent.change(screen.getByLabelText("Label"), { target: { value: "INT8 quantizer" } });
    fireEvent.change(screen.getByLabelText("Replacement configuration JSON"), {
      target: { value: JSON.stringify({ bits: 8 }) },
    });
    fireEvent.click(screen.getByRole("button", { name: "Replace component" }));

    expect(onReplaceNode).toHaveBeenCalledOnce();
    expect(onReplaceNode).toHaveBeenCalledWith({
      kind: node.kind,
      label: "INT8 quantizer",
      description: node.description,
      config: { bits: 8 },
    });
  });

  it("rejects an empty replacement label", () => {
    const onReplaceNode = vi.fn();
    render(
      <InspectorPanel
        node={graphFixture.nodes[1]}
        edge={null}
        formatShape={() => "—"}
        onReplaceNode={onReplaceNode}
      />,
    );

    fireEvent.change(screen.getByLabelText("Label"), { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "Replace component" }));

    expect(onReplaceNode).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("label is required");
  });
});

describe("InspectorPanel system entity", () => {
  it("shows the resolved entity with interfaces and grounding", () => {
    render(
      <InspectorPanel
        node={graphFixture.nodes[0]}
        edge={null}
        entity={entitiesFixture.entities[0] ?? null}
        formatShape={() => "—"}
      />,
    );

    expect(screen.getByText("System entity")).toBeInTheDocument();
    expect(screen.getByText(/Memory cell · Memory Cell/)).toBeInTheDocument();
    expect(screen.getByText(/Electronics · Package · Bitcell · Structure · 75%/)).toBeInTheDocument();
    expect(screen.getByText(/Interfaces: power · data/)).toBeInTheDocument();
    expect(screen.getByText(/Grounded by: sram/)).toBeInTheDocument();
  });

  it("marks generic placeholders instead of inventing a part", () => {
    render(
      <InspectorPanel
        node={graphFixture.nodes[1]}
        edge={null}
        entity={entitiesFixture.entities[1] ?? null}
        formatShape={() => "—"}
      />,
    );

    expect(screen.getByText("generic placeholder")).toBeInTheDocument();
    expect(screen.getByText(/rather than guessing/)).toBeInTheDocument();
  });

  it("shows a resolving state while entities load", () => {
    render(
      <InspectorPanel
        node={graphFixture.nodes[0]}
        edge={null}
        entity={null}
        formatShape={() => "—"}
      />,
    );

    expect(screen.getByText("resolving…")).toBeInTheDocument();
  });
});
