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

const comparison = {
  a: { project_id: "project-1", graph_id: "graph-1", version: 2, title: "Vision transformer" },
  b: { project_id: "project-2", graph_id: "graph-2", version: 1, title: "SRAM PUF" },
  structure_a: { node_count: 2, edge_count: 1, kinds: { input: 1, model: 1 } },
  structure_b: { node_count: 3, edge_count: 2, kinds: { input: 1, model: 2 } },
  shared_labels: [
    { label: "Transformer encoder", a_node_ids: ["encoder"], b_node_ids: ["enc"] },
  ],
  unique_a: [],
  unique_b: [{ label: "Sense amp", node_ids: ["sense"] }],
  metrics: [
    {
      name: "Ours — Accuracy",
      a: { raw_value: "92%", value: 92, unit: "%" },
      b: { raw_value: "0.88", value: 0.88, unit: null },
    },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/graphs", async (route) => {
    await route.fulfill({ json: graphs });
  });
  await page.route("**/api/v1/graphs/compare", async (route) => {
    await route.fulfill({ json: comparison });
  });
});

test("arena compares two tray graphs head-to-head", async ({ page }) => {
  await page.goto("/cross-paper");

  const list = page.getByRole("region", { name: "Graphs" });
  await list.getByRole("button", { name: "Add to tray" }).first().click();
  await list.getByRole("button", { name: "Add to tray" }).nth(1).click();

  await page.getByRole("tab", { name: "Arena" }).click();
  await page.getByLabel("Side A").selectOption("project-1::graph-1");
  await page.getByLabel("Side B").selectOption("project-2::graph-2");
  await page.getByRole("button", { name: "Compare" }).click();

  await expect(
    page.getByText("Structure: Vision transformer vs SRAM PUF"),
  ).toBeVisible();
  await expect(page.getByText("Transformer encoder")).toBeVisible();
  await expect(page.getByText("Ours — Accuracy")).toBeVisible();
});
