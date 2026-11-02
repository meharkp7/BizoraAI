import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../lib/api.ts";
import { useLibrarySelection, useWorkspaceSelection } from "../../lib/store.ts";
import type { CopilotThread, GraphPatch } from "../../lib/types.ts";
import {
  copilotFixture,
  copilotStreamBody,
  copilotThreadDetailFixture,
  copilotThreadFixture,
  graphFixture,
} from "../../test/fixtures.ts";
import { server } from "../../test/server.ts";
import type { DiagramSelection } from "../diagrams/selection.ts";
import { CopilotPanel } from "./CopilotPanel.tsx";
import { diagramContextFor } from "./copilotContext.ts";
import { turnsFromThread } from "./copilotThreads.ts";

const n1Selection: DiagramSelection = {
  view: "schematic",
  elementId: "N1",
  label: "Inverter stage",
  kind: "inverter",
  detail: null,
  confidence: 0.9,
  provenance: "from-paper",
  evidence: null,
  extra: [],
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("CopilotPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows stream progress while the answer is pending", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    let releaseDone!: () => void;
    const doneGate = new Promise<void>((resolve) => {
      releaseDone = resolve;
    });
    const encoder = new TextEncoder();
    const statusChunk = `event: status\ndata: ${JSON.stringify({ message: "Thinking (round 1)…" })}\n\n`;
    const doneChunk = `event: done\ndata: ${JSON.stringify({ response: copilotFixture })}\n\n`;
    vi.spyOn(api, "postCopilotStream").mockResolvedValue(
      new Response(
        new ReadableStream<Uint8Array>({
          async start(controller) {
            controller.enqueue(encoder.encode(statusChunk));
            await doneGate;
            controller.enqueue(encoder.encode(doneChunk));
            controller.close();
          },
        }),
        { headers: { "Content-Type": "text/event-stream" } },
      ),
    );
    const user = userEvent.setup();
    render(
      <CopilotPanel
        projectId="project-1"
        graph={graphFixture}
        disabled={false}
        view="methodology"
        selection={null}
        onSubmit={() => {}}
      />,
      { wrapper },
    );

    await user.type(screen.getByLabelText("Copilot message"), "why is this slow?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText("Thinking (round 1)…")).toBeInTheDocument();
    releaseDone();
    expect(await screen.findByText(/Closest library matches/)).toBeInTheDocument();
  });

  it("answers with library cards that open the library", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: ["encoder"], selectedEdgeIds: [] });
    useLibrarySelection.setState({ selectedComponentId: null, indexTab: "graph" });
    const user = userEvent.setup();
    render(
      <CopilotPanel
        projectId="project-1"
        graph={graphFixture}
        disabled={false}
        view="schematic"
        selection={null}
        onSubmit={() => {}}
      />,
      { wrapper },
    );

    await user.type(screen.getByLabelText("Copilot message"), "find NPN transistor");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText(/Closest library matches/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open in library" }));
    expect(useLibrarySelection.getState().selectedComponentId).toBe("npn-2n3904");
    expect(useLibrarySelection.getState().indexTab).toBe("library");
  });

  it("approves a replacement proposal as a patch", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: ["encoder"], selectedEdgeIds: [] });
    server.use(
      http.post("/api/v1/graphs/:projectId/:graphId/revisions/:version/copilot/stream", () =>
        new HttpResponse(copilotStreamBody({
          reply: "2N3904 NPN transistor is compatible with Transformer encoder.",
          cards: [
            {
              kind: "proposal",
              title: "Replace Transformer encoder with 2N3904 NPN transistor",
              body: "All known interfaces are preserved.",
              component_ids: ["npn-2n3904"],
              node_id: "encoder",
            },
          ],
          proposal: {
            node_id: "encoder",
            component_id: "npn-2n3904",
            kind: "component",
            label: "2N3904 NPN transistor",
            description: "NPN transistor.",
            config: { part: "2N3904" },
            rationale: "Test proposal.",
          },
        }), { headers: { "Content-Type": "text/event-stream" } }),
      ),
    );
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <CopilotPanel
        projectId="project-1"
        graph={graphFixture}
        disabled={false}
        view="schematic"
        selection={null}
        onSubmit={onSubmit}
      />,
      { wrapper },
    );

    await user.type(screen.getByLabelText("Copilot message"), "replace encoder with 2N3904");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText(/is compatible with/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve and apply" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    const [[patches]] = onSubmit.mock.calls as [[GraphPatch[]]];
    expect(patches[0].operation).toBe("replace_node");
    expect(patches[0].target_id).toBe("encoder");
  });

  it("approves a config-only proposal as a config patch", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: ["encoder"], selectedEdgeIds: [] });
    server.use(
      http.post("/api/v1/graphs/:projectId/:graphId/revisions/:version/copilot/stream", () =>
        new HttpResponse(copilotStreamBody({
          reply: "Ready to set layers.",
          cards: [
            {
              kind: "proposal",
              title: "Set layers on Transformer encoder",
              body: "layers = 24",
              component_ids: [],
              node_id: "encoder",
            },
          ],
          proposal: {
            node_id: "encoder",
            component_id: null,
            kind: "model",
            label: "Transformer encoder",
            description: null,
            config: { layers: 24 },
            rationale: "Test config proposal.",
          },
        }), { headers: { "Content-Type": "text/event-stream" } }),
      ),
    );
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <CopilotPanel
        projectId="project-1"
        graph={graphFixture}
        disabled={false}
        view="schematic"
        selection={null}
        onSubmit={onSubmit}
      />,
      { wrapper },
    );

    await user.type(screen.getByLabelText("Copilot message"), "set layers to 24");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText("Ready to set layers.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve and apply" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    const [[patches]] = onSubmit.mock.calls as [[GraphPatch[]]];
    expect(patches[0].operation).toBe("update_node_config");
    expect(patches[0].payload["config"]).toEqual({ layers: 24 });
  });

  it("sends the diagram tab and selection as viewer context", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    const bodies: Array<Record<string, unknown>> = [];
    server.use(
      http.post(
        "/api/v1/graphs/:projectId/:graphId/revisions/:version/copilot/stream",
        async ({ request }) => {
          bodies.push((await request.json()) as Record<string, unknown>);
          return new HttpResponse(copilotStreamBody(copilotFixture), { headers: { "Content-Type": "text/event-stream" } });
        },
      ),
    );
    const user = userEvent.setup();
    render(
      <CopilotPanel
        projectId="project-1"
        graph={graphFixture}
        disabled={false}
        view="schematic"
        selection={n1Selection}
        onSubmit={() => {}}
      />,
      { wrapper },
    );

    expect(screen.getByText(/Talking about/)).toHaveTextContent("N1");
    await user.type(screen.getByLabelText("Copilot message"), "What does this do?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText(/Closest library matches/)).toBeInTheDocument();
    expect(bodies).toHaveLength(1);
    expect(bodies[0].diagram_context).toBe(
      "viewing schematic tab; diagram selection N1 (Inverter stage)",
    );
  });

  it("offers follow-up chips that ask on click", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: ["encoder"], selectedEdgeIds: [] });
    const user = userEvent.setup();
    render(
      <CopilotPanel
        projectId="project-1"
        graph={graphFixture}
        disabled={false}
        view="methodology"
        selection={null}
        onSubmit={() => {}}
      />,
      { wrapper },
    );

    await user.type(screen.getByLabelText("Copilot message"), "find NPN transistor");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(
      await screen.findByRole("button", { name: "What does the paper say here?" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Compare the top two options" }));

    expect(await screen.findAllByText(/Closest library matches/)).toHaveLength(2);
    expect(
      screen.getByRole("button", { name: "Compare the top two options" }),
    ).toBeInTheDocument();
  });
});

describe("CopilotPanel threads", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function renderPanel() {
    return render(
      <CopilotPanel
        projectId="project-1"
        graph={graphFixture}
        disabled={false}
        view="methodology"
        selection={null}
        onSubmit={() => {}}
      />,
      { wrapper },
    );
  }

  it("resumes the most recent conversation on load", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    server.use(
      http.get("/api/v1/graphs/:projectId/:graphId/copilot/threads", () =>
        HttpResponse.json([copilotThreadFixture]),
      ),
      http.get("/api/v1/graphs/:projectId/:graphId/copilot/threads/:threadId", () =>
        HttpResponse.json(copilotThreadDetailFixture),
      ),
    );
    renderPanel();

    expect(await screen.findByText("find NPN transistor")).toBeInTheDocument();
    expect(await screen.findByText(/Closest library matches/)).toBeInTheDocument();
    expect(screen.getByLabelText("Conversation")).toHaveValue("thread-1");
  });

  it("switches conversations and starts new ones", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    const second = { ...copilotThreadFixture, thread_id: "thread-2", title: "Second chat" };
    const secondDetail = {
      thread_id: "thread-2",
      title: "Second chat",
      turns: [
        { seq: 0, role: "user", message: "compare options", response: null },
        {
          seq: 1,
          role: "assistant",
          message: "Here is the comparison.",
          response: { ...copilotFixture, reply: "Here is the comparison." },
        },
      ],
    };
    server.use(
      http.get("/api/v1/graphs/:projectId/:graphId/copilot/threads", () =>
        HttpResponse.json([copilotThreadFixture, second]),
      ),
      http.get(
        "/api/v1/graphs/:projectId/:graphId/copilot/threads/:threadId",
        ({ params }) =>
          HttpResponse.json(
            params.threadId === "thread-2" ? secondDetail : copilotThreadDetailFixture,
          ),
      ),
    );
    const user = userEvent.setup();
    renderPanel();

    expect(await screen.findByText("find NPN transistor")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Conversation"), "thread-2");

    expect(await screen.findByText("compare options")).toBeInTheDocument();
    expect(screen.queryByText("find NPN transistor")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "New" }));
    expect(screen.getByLabelText("Conversation")).toHaveValue("");
    expect(screen.queryByText("compare options")).not.toBeInTheDocument();
  });

  it("sends the active thread id with each turn", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    const bodies: Array<Record<string, unknown>> = [];
    server.use(
      http.post(
        "/api/v1/graphs/:projectId/:graphId/revisions/:version/copilot/stream",
        async ({ request }) => {
          bodies.push((await request.json()) as Record<string, unknown>);
          return new HttpResponse(copilotStreamBody(copilotFixture), {
            headers: { "Content-Type": "text/event-stream" },
          });
        },
      ),
    );
    const user = userEvent.setup();
    renderPanel();

    await user.type(screen.getByLabelText("Copilot message"), "hello");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText(/Closest library matches/)).toBeInTheDocument();
    expect(bodies).toHaveLength(1);
    expect(bodies[0].thread_id).toBe("thread-1");
  });
});

describe("turnsFromThread", () => {
  it("pairs stored turns oldest-first and drops stray assistant turns", () => {
    const thread: CopilotThread = {
      ...copilotThreadDetailFixture,
      turns: [
        ...copilotThreadDetailFixture.turns,
        { seq: 2, role: "user", message: "and then?", response: null },
        { seq: 3, role: "assistant", message: "stray", response: copilotFixture },
        { seq: 4, role: "assistant", message: "really stray", response: copilotFixture },
      ],
    };
    const turns = turnsFromThread(thread);

    expect(turns).toHaveLength(2);
    expect(turns[0].message).toBe("find NPN transistor");
    expect(turns[0].response?.reply).toMatch(/Closest library matches/);
    expect(turns[1].message).toBe("and then?");
    expect(turns[1].response?.reply).toBe(copilotFixture.reply);
    expect(turns.map((turn) => turn.id)).toEqual([1, 2]);
  });
});

describe("diagramContextFor", () => {
  it("names the tab and the freshest selection", () => {
    expect(diagramContextFor("schematic", n1Selection, null)).toBe(
      "viewing schematic tab; diagram selection N1 (Inverter stage)",
    );
    expect(
      diagramContextFor("3d", null, { id: "encoder", label: "Transformer encoder" }),
    ).toBe("viewing 3D tab; graph selection encoder (Transformer encoder)");
    expect(diagramContextFor("methodology", null, null)).toBe("viewing methodology tab");
  });
});
