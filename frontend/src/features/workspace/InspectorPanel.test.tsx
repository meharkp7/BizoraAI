import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RemovalPreflight } from "../../lib/types.ts";
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
    expect(screen.getByText(/the 3D view only shows catalog part models/)).toBeInTheDocument();
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

describe("InspectorPanel removal preflight", () => {
  const node = graphFixture.nodes[1];
  const removal: RemovalPreflight = {
    target_node_id: node.id,
    neighbor_node_ids: [graphFixture.nodes[0].id],
    dropped_edge_ids: ["e1"],
    evidence: [
      {
        source_id: "paper",
        page: 3,
        quote: "a second-order section",
        figure_label: null,
        bbox: null,
        locator: null,
        status: "supported",
      },
    ],
  };

  it("requests a removal preview for the selected node", () => {
    const onPreviewRemoval = vi.fn();
    render(
      <InspectorPanel
        node={node}
        edge={null}
        formatShape={() => "—"}
        onPreviewRemoval={onPreviewRemoval}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Preview removal" }));

    expect(onPreviewRemoval).toHaveBeenCalledOnce();
    expect(onPreviewRemoval).toHaveBeenCalledWith(node.id);
  });

  it("shows neighbors, dropped edges, and paper claims", () => {
    render(
      <InspectorPanel
        node={node}
        edge={null}
        formatShape={() => "—"}
        removal={removal}
        nodeLabels={{ [graphFixture.nodes[0].id]: graphFixture.nodes[0].label }}
        onPreviewRemoval={() => {}}
      />,
    );

    expect(screen.getByText(graphFixture.nodes[0].label)).toBeInTheDocument();
    expect(screen.getByText("e1")).toBeInTheDocument();
    expect(screen.getByText(/a second-order section \(p\. 3\)/)).toBeInTheDocument();
  });

  it("names the honest empty states for an isolated, uncited block", () => {
    render(
      <InspectorPanel
        node={node}
        edge={null}
        formatShape={() => "—"}
        removal={{ ...removal, neighbor_node_ids: [], dropped_edge_ids: [], evidence: [] }}
        onPreviewRemoval={() => {}}
      />,
    );

    expect(screen.getByText(/this block is isolated/)).toBeInTheDocument();
    expect(screen.getByText(/none cited on this block/)).toBeInTheDocument();
  });
});
