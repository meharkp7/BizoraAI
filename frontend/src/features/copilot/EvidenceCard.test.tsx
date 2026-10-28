import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import { graphFixture } from "../../test/fixtures.ts";
import { server } from "../../test/server.ts";
import { CopilotPanel } from "./CopilotPanel.tsx";
import { EvidenceCard } from "./EvidenceCard.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("EvidenceCard", () => {
  it("badges evidence as grounded in the paper", () => {
    render(
      <EvidenceCard
        card={{
          kind: "evidence",
          title: "Paper evidence",
          body: "Source: paper-1 · Page 3",
          component_ids: [],
          node_id: "encoder",
        }}
      />,
    );

    expect(screen.getByText("Grounded in paper")).toBeInTheDocument();
    expect(screen.getByText(/Page 3/)).toBeInTheDocument();
  });

  it("badges run cards as measured", () => {
    render(
      <EvidenceCard
        card={{
          kind: "info",
          title: "Measured run",
          body: "Run: run-1\nState: succeeded",
          component_ids: [],
          node_id: null,
        }}
      />,
    );

    expect(screen.getByText("Measured")).toBeInTheDocument();
  });
});

describe("CopilotPanel grounding", () => {
  it("renders cited answers with badges and the approval gate", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: ["encoder"], selectedEdgeIds: [] });
    server.use(
      http.post("/api/v1/graphs/:projectId/:graphId/revisions/:version/copilot", () =>
        HttpResponse.json({
          reply: "The paper describes the encoder on page 3.",
          cards: [
            {
              kind: "evidence",
              title: "Paper evidence",
              body: "Source: paper-1 · Page 3",
              component_ids: [],
              node_id: "encoder",
            },
            {
              kind: "info",
              title: "Measured run",
              body: "Run: run-1\nState: succeeded",
              component_ids: [],
              node_id: null,
            },
            {
              kind: "proposal",
              title: "Proposed change on Transformer encoder",
              body: "Try a wider layer.\nAwaiting your approval — nothing was changed yet.",
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
            config: { width: 512 },
            rationale: "Try a wider layer.",
          },
        }),
      ),
    );
    const user = userEvent.setup();
    render(
      <CopilotPanel
        projectId="project-1"
        graph={graphFixture}
        disabled={false}
        onSubmit={() => {}}
      />,
      { wrapper },
    );

    await user.type(screen.getByLabelText("Copilot message"), "What does the paper say?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText("Grounded in paper")).toBeInTheDocument();
    expect(screen.getByText("Measured")).toBeInTheDocument();
    expect(screen.getByText("Nothing is applied until you approve.")).toBeInTheDocument();
  });
});
