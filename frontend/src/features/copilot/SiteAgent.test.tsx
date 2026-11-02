import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { SiteAgent } from "./SiteAgent.tsx";

const STORAGE_KEY = "bizora.siteAgent.graph";

function renderAt(path: string, routePath: string): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={routePath} element={<SiteAgent />} />
      </Routes>
    </MemoryRouter>,
    { wrapper },
  );
}

describe("SiteAgent", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("stays hidden on the workspace canvas", () => {
    renderAt("/g/project-1/graph-1", "g/:projectId/:graphId");

    expect(
      screen.queryByRole("button", { name: "Open Bizora agent" }),
    ).not.toBeInTheDocument();
  });

  it("chats about the graph on a graph sub-page", async () => {
    const user = userEvent.setup();
    renderAt("/g/project-1/graph-1/notebook", "g/:projectId/:graphId/notebook");

    const opener = await screen.findByRole("button", { name: "Open Bizora agent" });
    await user.click(opener);

    expect(
      await screen.findByText(
        (_, element) =>
          element?.textContent ===
          "Chatting about Vision transformer — open the workspace to apply proposals.",
      ),
    ).toBeInTheDocument();
    // The visit becomes the most recent graph for non-graph pages.
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe(
      JSON.stringify({ projectId: "project-1", graphId: "graph-1" }),
    );
  });

  it("falls back to the most recent graph off graph routes", async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ projectId: "project-1", graphId: "graph-1" }),
    );
    const user = userEvent.setup();
    renderAt("/papers", "papers");

    const opener = await screen.findByRole("button", { name: "Open Bizora agent" });
    await user.click(opener);

    expect(
      await screen.findByText(
        (_, element) =>
          element?.textContent ===
          "Chatting about Vision transformer — open the workspace to apply proposals.",
      ),
    ).toBeInTheDocument();
  });

  it("stays hidden with no graph in reach", () => {
    renderAt("/papers", "papers");

    expect(
      screen.queryByRole("button", { name: "Open Bizora agent" }),
    ).not.toBeInTheDocument();
  });

  it("stays hidden on the login page", () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ projectId: "project-1", graphId: "graph-1" }),
    );
    renderAt("/login", "login");

    expect(
      screen.queryByRole("button", { name: "Open Bizora agent" }),
    ).not.toBeInTheDocument();
  });
});
