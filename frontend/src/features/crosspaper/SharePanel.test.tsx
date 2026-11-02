import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { useSession } from "../../lib/store.ts";
import type { ProjectInviteSummary } from "../../lib/types.ts";
import { server } from "../../test/server.ts";
import { SharePanel } from "./SharePanel.tsx";
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

function inviteOf(email: string, status: ProjectInviteSummary["status"] = "pending") {
  return {
    invite_id: `inv-${email}`,
    project_id: "project-1",
    email,
    role: "viewer",
    status,
    created_by: "owner-1",
    created_at: "2026-11-02T00:00:00+00:00",
    expires_at: "2026-11-09T00:00:00+00:00",
  };
}

describe("SharePanel", () => {
  afterEach(() => {
    useSession.setState({ token: null });
  });

  it("asks logged-out visitors to log in", () => {
    render(<SharePanel tray={TRAY} />, { wrapper });

    expect(screen.getByText("Log in")).toBeInTheDocument();
    expect(screen.queryByLabelText("Invitee email")).not.toBeInTheDocument();
  });

  it("asks for a tray graph before sharing", () => {
    useSession.setState({ token: "test-token" });
    render(<SharePanel tray={[]} />, { wrapper });

    expect(
      screen.getByText("Add a graph to the tray to share its project."),
    ).toBeInTheDocument();
  });

  it("invites, revokes, and accepts", async () => {
    useSession.setState({ token: "test-token" });
    const invites = [inviteOf("guest@example.com")];
    server.use(
      http.get("/api/v1/projects/:projectId/invites", () => HttpResponse.json(invites)),
      http.post("/api/v1/projects/:projectId/invites", async ({ request }) => {
        const body = (await request.json()) as { email: string; role: string };
        const created = { ...inviteOf(body.email), role: body.role };
        invites.push(created);
        return HttpResponse.json({ invite: created, token: "one-time-token" }, { status: 201 });
      }),
      http.delete("/api/v1/projects/:projectId/invites/:inviteId", ({ params }) => {
        const entry = invites.find((candidate) => candidate.invite_id === params["inviteId"]);
        if (!entry) return new HttpResponse(null, { status: 404 });
        entry.status = "revoked";
        return HttpResponse.json(entry);
      }),
      http.post("/api/v1/projects/:projectId/invites/:inviteId/accept", () =>
        HttpResponse.json({ ...inviteOf("guest@example.com"), status: "accepted" }),
      ),
    );
    const user = userEvent.setup();
    render(<SharePanel tray={TRAY} />, { wrapper });

    expect(await screen.findByText("guest@example.com")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Invitee email"), "teammate@example.com");
    await user.click(screen.getByRole("button", { name: "Invite" }));
    expect(await screen.findByText(/Invite for teammate@example.com/)).toBeInTheDocument();
    expect(screen.getByText("one-time-token")).toBeInTheDocument();

    const row = screen.getByText("guest@example.com").closest("li")!;
    await user.click(within(row).getByRole("button", { name: /Revoke invite/ }));

    await user.type(screen.getByLabelText("Invite ID"), "inv-guest@example.com");
    await user.type(screen.getByLabelText("Invite token"), "pasted-token");
    await user.click(screen.getByRole("button", { name: "Accept" }));
    expect(await screen.findByText("Welcome to project-1.")).toBeInTheDocument();
  });
});
