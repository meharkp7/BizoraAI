import { expect, test } from "@playwright/test";

const graphs = [
  {
    project_id: "project-1",
    graph_id: "graph-1",
    version: 2,
    title: "Vision transformer",
    source_ids: ["paper-1"],
    node_count: 2,
    edge_count: 1,
    created_by: "test",
    created_at: "2026-01-02T00:00:00Z",
  },
];

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    globalThis.localStorage.setItem("bizora.auth.token", "e2e-token");
  });
  await page.route("**/api/v1/graphs", async (route) => {
    await route.fulfill({ json: graphs });
  });
  await page.route("**/api/v1/projects/*/invites", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as { email: string; role: string };
      await route.fulfill({
        status: 201,
        json: {
          invite: {
            invite_id: "inv-new",
            project_id: "project-1",
            email: body.email,
            role: body.role,
            status: "pending",
            created_by: "owner-1",
            created_at: "2026-11-02T00:00:00+00:00",
            expires_at: "2026-11-09T00:00:00+00:00",
          },
          token: "e2e-one-time-token",
        },
      });
      return;
    }
    await route.fulfill({
      json: [
        {
          invite_id: "inv-1",
          project_id: "project-1",
          email: "guest@example.com",
          role: "editor",
          status: "pending",
          created_by: "owner-1",
          created_at: "2026-11-02T00:00:00+00:00",
          expires_at: "2026-11-09T00:00:00+00:00",
        },
      ],
    });
  });
});

test("share tab lists invites and shows the one-time token", async ({ page }) => {
  await page.goto("/cross-paper");

  const list = page.getByRole("region", { name: "Graphs" });
  await list.getByRole("button", { name: "Add to tray" }).first().click();

  await page.getByRole("tab", { name: "Share" }).click();
  await expect(page.getByText("guest@example.com")).toBeVisible();

  await page.getByLabel("Invitee email").fill("teammate@example.com");
  await page.getByRole("button", { name: "Invite" }).click();
  await expect(page.getByText("e2e-one-time-token")).toBeVisible();
});
