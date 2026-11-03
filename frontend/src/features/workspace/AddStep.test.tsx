import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { GraphPatch } from "../../lib/types.ts";
import { graphFixture } from "../../test/fixtures.ts";
import { AddStepForm } from "./AddStep.tsx";

describe("AddStepForm", () => {
  it("appends a connected step after the selected node", async () => {
    const seen: GraphPatch[][] = [];
    const user = userEvent.setup();
    render(
      <AddStepForm
        graph={graphFixture}
        disabled={false}
        insertAfter="encoder"
        onSubmit={(patches) => seen.push(patches)}
        onCancel={() => {}}
      />,
    );

    await user.type(screen.getByLabelText("Step label"), "Quantize weights");
    await user.selectOptions(screen.getByLabelText("Kind"), "operation");
    await user.click(screen.getByRole("button", { name: "Add step" }));

    expect(seen).toHaveLength(1);
    const [nodePatch, edgePatch] = seen[0];
    expect(nodePatch.operation).toBe("add_node");
    const node = nodePatch.payload["node"] as Record<string, unknown>;
    expect(node["id"]).toBe("quantize-weights");
    expect(node["label"]).toBe("Quantize weights");
    expect(node["kind"]).toBe("operation");
    expect(edgePatch.operation).toBe("add_edge");
    const edge = edgePatch.payload["edge"] as Record<string, unknown>;
    expect(edge["source"]).toBe("encoder");
    expect(edge["target"]).toBe("quantize-weights");
  });

  it("adds a standalone step without an edge", async () => {
    const seen: GraphPatch[][] = [];
    const user = userEvent.setup();
    render(
      <AddStepForm
        graph={graphFixture}
        disabled={false}
        insertAfter={null}
        onSubmit={(patches) => seen.push(patches)}
        onCancel={() => {}}
      />,
    );

    await user.type(screen.getByLabelText("Step label"), "Collect dataset");
    await user.selectOptions(screen.getByLabelText("Insert after"), "");
    await user.click(screen.getByRole("button", { name: "Add step" }));

    expect(seen).toHaveLength(1);
    expect(seen[0]).toHaveLength(1);
    expect(seen[0][0].operation).toBe("add_node");
  });

  it("refuses duplicate ids and explains why", async () => {
    const seen: GraphPatch[][] = [];
    const user = userEvent.setup();
    render(
      <AddStepForm
        graph={graphFixture}
        disabled={false}
        insertAfter={null}
        onSubmit={(patches) => seen.push(patches)}
        onCancel={() => {}}
      />,
    );

    await user.type(screen.getByLabelText("Step label"), "Encoder copy");
    await user.clear(screen.getByLabelText("Step ID"));
    await user.type(screen.getByLabelText("Step ID"), "encoder");
    await user.click(screen.getByRole("button", { name: "Add step" }));

    expect(seen).toHaveLength(0);
    expect(await screen.findByText("This ID is already in the graph.")).toBeInTheDocument();
  });

  it("cancels without submitting", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(
      <AddStepForm
        graph={graphFixture}
        disabled={false}
        insertAfter={null}
        onSubmit={() => {}}
        onCancel={onCancel}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
