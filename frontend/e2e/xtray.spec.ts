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
  {
    project_id: "project-2",
    graph_id: "graph-2",
    version: 1,
    title: "SRAM PUF",
    source_ids: ["paper-2"],
    node_count: 3,
    edge_count: 2,
    created_by: "test",
    created_at: "2026-01-01T00:00:00Z",
  },
];

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/graphs", async (route) => {
    await route.fulfill({ json: graphs });
  });
});

test("cross-paper tray collects and removes graphs", async ({ page }) => {
  await page.goto("/cross-paper");
  await expect(page.getByRole("heading", { name: "Cross-paper workspace" })).toBeVisible();

  const list = page.getByRole("region", { name: "Graphs" });
  await expect(list.getByText("Vision transformer")).toBeVisible();
  await list.getByRole("button", { name: "Add to tray" }).first().click();

  const tray = page.getByRole("region", { name: "Tray" });
  await expect(tray.getByText("Vision transformer")).toBeVisible();
  await expect(tray.getByRole("link", { name: "Vision transformer" })).toHaveAttribute(
    "href",
    "/g/project-1/graph-1",
  );

  await tray.getByRole("button", { name: "Remove" }).click();
  await expect(tray.getByText("Vision transformer")).toBeHidden();
});
