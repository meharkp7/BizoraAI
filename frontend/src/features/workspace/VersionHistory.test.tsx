import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { server } from "../../test/server.ts";
import { VersionHistory } from "./VersionHistory.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderHistory(callbacks: { onSelectVersion?: (version: number) => void; onCompare?: (base: number) => void } = {}) {
  const onSelectVersion = callbacks.onSelectVersion ?? vi.fn();
  const onCompare = callbacks.onCompare ?? vi.fn();
  render(
    <VersionHistory
      projectId="project-1"
      graphId="graph-1"
      currentVersion={2}
      onSelectVersion={onSelectVersion}
      onCompare={onCompare}
    />,
    { wrapper },
  );
  return { onSelectVersion, onCompare };
}

describe("VersionHistory", () => {
  it("lists revisions newest first with the current version marked", async () => {
    renderHistory();

    const panel = await screen.findByRole("region", { name: "Version history" });
    const rows = await within(panel).findAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("v2");
    expect(rows[0]).toHaveTextContent("current");
    expect(rows[1]).toHaveTextContent("v1");
    expect(rows[1]).not.toHaveTextContent("current");
    expect(panel).toHaveTextContent("Vision transformer");
  });

  it("views an older revision without restoring it", async () => {
    const user = userEvent.setup();
    const { onSelectVersion } = renderHistory();

    const panel = await screen.findByRole("region", { name: "Version history" });
    const rows = await within(panel).findAllByRole("listitem");
    const row = rows[1];
    await user.click(within(row).getByRole("button", { name: "View" }));

    expect(onSelectVersion).toHaveBeenCalledWith(1);
  });

  it("sends a compare request for an older revision", async () => {
    const user = userEvent.setup();
    const { onCompare } = renderHistory();

    const panel = await screen.findByRole("region", { name: "Version history" });
    const rows = await within(panel).findAllByRole("listitem");
    const row = rows[1];
    await user.click(within(row).getByRole("button", { name: "Compare" }));

    expect(onCompare).toHaveBeenCalledWith(1);
  });

  it("restores after confirmation and navigates to the new head", async () => {
    const user = userEvent.setup();
    const { onSelectVersion } = renderHistory();

    const panel = await screen.findByRole("region", { name: "Version history" });
    const rows = await within(panel).findAllByRole("listitem");
    const row = rows[1];
    await user.click(within(row).getByRole("button", { name: "Restore" }));
    await user.click(within(row).getByRole("button", { name: "Confirm restore" }));

    expect(onSelectVersion).toHaveBeenCalledWith(3);
  });

  it("cancels a restore without calling the API", async () => {
    const user = userEvent.setup();
    const { onSelectVersion } = renderHistory();

    const panel = await screen.findByRole("region", { name: "Version history" });
    const rows = await within(panel).findAllByRole("listitem");
    const row = rows[1];
    await user.click(within(row).getByRole("button", { name: "Restore" }));
    await user.click(within(row).getByRole("button", { name: "Cancel" }));

    expect(onSelectVersion).not.toHaveBeenCalled();
    expect(
      within(panel).getAllByRole("button", { name: "Restore" })[0],
    ).toBeInTheDocument();
  });

  it("explains a restore conflict in plain words", async () => {
    server.use(
      http.post(
        "/api/v1/graphs/:projectId/:graphId/revisions/:version/restore",
        () =>
          HttpResponse.json(
            {
              error: {
                code: "RESOURCE_CONFLICT",
                message: "The revision is already the latest; nothing to restore.",
                details: {},
              },
            },
            { status: 409 },
          ),
      ),
    );
    const user = userEvent.setup();
    renderHistory();

    const panel = await screen.findByRole("region", { name: "Version history" });
    const rows = await within(panel).findAllByRole("listitem");
    const row = rows[1];
    await user.click(within(row).getByRole("button", { name: "Restore" }));
    await user.click(within(row).getByRole("button", { name: "Confirm restore" }));

    expect(
      await screen.findByText("That revision is already the latest; nothing to restore."),
    ).toBeInTheDocument();
  });
});
