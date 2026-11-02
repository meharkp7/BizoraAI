import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server.ts";
import { MemoryPanel } from "./MemoryPanel.tsx";
import type { TrayEntry } from "./tray.ts";

const TRAY: TrayEntry[] = [
  { project_id: "project-1", graph_id: "graph-1", title: "Vision transformer" },
];

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("MemoryPanel", () => {
  it("asks for a tray graph before opening memory", () => {
    render(<MemoryPanel tray={[]} />, { wrapper });

    expect(
      screen.getByText("Add a graph to the tray to open its project memory."),
    ).toBeInTheDocument();
  });

  it("remembers and forgets facts", async () => {
    const facts: Array<{ id: number; fact: string }> = [
      { id: 1, fact: "The tapeout uses 65nm." },
    ];
    server.use(
      http.get("/api/v1/projects/:projectId/memory", ({ params }) =>
        HttpResponse.json(
          facts.map((entry) => ({
            id: entry.id,
            project_id: params["projectId"],
            fact: entry.fact,
            created_by: "cross-paper-ui",
            created_at: "2026-11-02T00:00:00+00:00",
          })),
        ),
      ),
      http.post("/api/v1/projects/:projectId/memory", async ({ request, params }) => {
        const body = (await request.json()) as { fact: string };
        const entry = { id: 2, fact: body.fact };
        facts.push(entry);
        return HttpResponse.json(
          {
            ...entry,
            project_id: params["projectId"],
            created_by: "cross-paper-ui",
            created_at: "2026-11-02T00:00:00+00:00",
          },
          { status: 201 },
        );
      }),
      http.delete("/api/v1/projects/:projectId/memory/:factId", ({ params }) => {
        const index = facts.findIndex((entry) => entry.id === Number(params["factId"]));
        if (index !== -1) facts.splice(index, 1);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    render(<MemoryPanel tray={TRAY} />, { wrapper });

    expect(await screen.findByText("The tapeout uses 65nm.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Memory fact"), "Corners first, always.");
    await user.click(screen.getByRole("button", { name: "Remember" }));
    expect(await screen.findByText("Corners first, always.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Forget: The tapeout uses 65nm." }));
    expect(await screen.findByText("Corners first, always.")).toBeInTheDocument();
    expect(screen.queryByText("The tapeout uses 65nm.")).not.toBeInTheDocument();
  });
});
