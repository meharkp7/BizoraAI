import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { server } from "../../test/server.ts";
import { ReplicationPlanPanel } from "./ReplicationPlanPanel.tsx";

const PLAN = {
  project_id: "project-1",
  graph_id: "graph-1",
  version: 2,
  steps: [
    {
      seq: 1,
      node_id: "input",
      label: "Image",
      kind: "input",
      action: "Provide input 'Image' (input).",
      verify: ["Confirm the input format matches the paper's description."],
    },
    {
      seq: 2,
      node_id: "vit",
      label: "ViT backbone",
      kind: "model",
      action: "Build model 'ViT backbone' (vit).",
      verify: ["Confirm parameter counts match the reported architecture."],
    },
  ],
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("ReplicationPlanPanel", () => {
  beforeEach(() => {
    window.localStorage.clear();
    server.use(
      http.get("/api/v1/projects/:projectId/graphs/:graphId/replication-plan", () =>
        HttpResponse.json(PLAN),
      ),
    );
  });

  it("lists ordered steps with verify hints", async () => {
    render(<ReplicationPlanPanel projectId="project-1" graphId="graph-1" />, { wrapper });

    expect(await screen.findByText(/0 of 2 steps done/)).toBeInTheDocument();
    expect(screen.getByText(/Provide input 'Image'/)).toBeInTheDocument();
    expect(screen.getByText(/Build model 'ViT backbone'/)).toBeInTheDocument();
    expect(
      screen.getByText("Confirm parameter counts match the reported architecture."),
    ).toBeInTheDocument();
  });

  it("persists checkmarks per graph revision", async () => {
    const { unmount } = render(
      <ReplicationPlanPanel projectId="project-1" graphId="graph-1" />,
      { wrapper },
    );
    const first = await screen.findByRole("checkbox", { name: "Step 1: Image" });
    first.click();
    expect(await screen.findByText(/1 of 2 steps done/)).toBeInTheDocument();
    unmount();

    render(<ReplicationPlanPanel projectId="project-1" graphId="graph-1" />, { wrapper });
    expect(await screen.findByText(/1 of 2 steps done/)).toBeInTheDocument();
    expect(await screen.findByRole("checkbox", { name: "Step 1: Image" })).toBeChecked();
  });

  it("says plainly when the plan is unavailable", async () => {
    server.use(
      http.get("/api/v1/projects/:projectId/graphs/:graphId/replication-plan", () =>
        HttpResponse.json(
          { error: { code: "RESOURCE_NOT_FOUND", message: "Graph not found." } },
          { status: 404 },
        ),
      ),
    );
    render(<ReplicationPlanPanel projectId="nope" graphId="nope" />, { wrapper });

    expect(
      await screen.findByText("The replication plan is unavailable for this graph."),
    ).toBeInTheDocument();
  });

  it("says plainly when speech is unsupported", async () => {
    render(<ReplicationPlanPanel projectId="project-1" graphId="graph-1" />, { wrapper });

    expect(await screen.findByText(/0 of 2 steps done/)).toBeInTheDocument();
    expect(
      screen.getByText("Spoken narration needs a browser with speech support."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Narrate build" })).not.toBeInTheDocument();
  });
});

class FakeUtterance {
  text: string;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(text: string) {
    this.text = text;
  }
}

describe("ReplicationPlanPanel narration", () => {
  const spoken: FakeUtterance[] = [];
  let autoEnd = true;

  beforeEach(() => {
    window.localStorage.clear();
    spoken.length = 0;
    autoEnd = true;
    server.use(
      http.get("/api/v1/projects/:projectId/graphs/:graphId/replication-plan", () =>
        HttpResponse.json(PLAN),
      ),
      http.get(
        "/api/v1/projects/:projectId/graphs/:graphId/replication-plan/narration",
        () =>
          HttpResponse.json({
            project_id: "project-1",
            graph_id: "graph-1",
            version: 2,
            intro: "Replication guide: 2 steps.",
            lines: [
              { seq: 1, node_id: "input", text: "Step 1 of 2. Provide input." },
              { seq: 2, node_id: "vit", text: "Step 2 of 2. Build model." },
            ],
          }),
      ),
    );
    const w = window as unknown as Record<string, unknown>;
    w["SpeechSynthesisUtterance"] = FakeUtterance;
    w["speechSynthesis"] = {
      speak: (utterance: FakeUtterance) => {
        spoken.push(utterance);
        if (autoEnd) utterance.onend?.();
      },
      cancel: () => {},
    };
  });

  afterEach(() => {
    const w = window as unknown as Record<string, unknown>;
    delete w["SpeechSynthesisUtterance"];
    delete w["speechSynthesis"];
  });

  it("reads the guide and checks steps off", async () => {
    const user = userEvent.setup();
    render(<ReplicationPlanPanel projectId="project-1" graphId="graph-1" />, { wrapper });

    await user.click(await screen.findByRole("button", { name: "Narrate build" }));

    expect(await screen.findByText(/2 of 2 steps done/)).toBeInTheDocument();
    expect(spoken.map((utterance) => utterance.text)).toEqual([
      "Replication guide: 2 steps.",
      "Step 1 of 2. Provide input.",
      "Step 2 of 2. Build model.",
    ]);
    // Narration finished: the button is back and nothing stays current.
    expect(await screen.findByRole("button", { name: "Narrate build" })).toBeInTheDocument();
  });

  it("stops mid-narration", async () => {
    autoEnd = false;
    const user = userEvent.setup();
    render(<ReplicationPlanPanel projectId="project-1" graphId="graph-1" />, { wrapper });

    await user.click(await screen.findByRole("button", { name: "Narrate build" }));
    await user.click(await screen.findByRole("button", { name: "Stop narration" }));

    expect(await screen.findByRole("button", { name: "Narrate build" })).toBeInTheDocument();
    expect(spoken.map((utterance) => utterance.text)).toEqual([
      "Replication guide: 2 steps.",
    ]);
  });
});
