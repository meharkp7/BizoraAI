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
  await page.route("**/api/v1/graphs", async (route) => {
    await route.fulfill({ json: graphs });
  });
  await page.route("**/api/v1/projects/*/memory", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as { fact: string };
      await route.fulfill({
        status: 201,
        json: {
          id: 2,
          project_id: "project-1",
          fact: body.fact,
          created_by: "cross-paper-ui",
          created_at: "2026-11-02T00:00:00+00:00",
        },
      });
      return;
    }
    await route.fulfill({
      json: [
        {
          id: 1,
          project_id: "project-1",
          fact: "The tapeout uses 65nm.",
          created_by: "cross-paper-ui",
          created_at: "2026-11-02T00:00:00+00:00",
        },
      ],
    });
  });
});

test("memory tab lists and stores project facts", async ({ page }) => {
  await page.goto("/cross-paper");

  const list = page.getByRole("region", { name: "Graphs" });
  await list.getByRole("button", { name: "Add to tray" }).first().click();

  await page.getByRole("tab", { name: "Memory" }).click();
  await expect(page.getByText("The tapeout uses 65nm.")).toBeVisible();

  await page.getByLabel("Memory fact").fill("Corners first, always.");
  await page.getByRole("button", { name: "Remember" }).click();
  await expect(page.getByLabel("Memory fact")).toHaveValue("");
});
