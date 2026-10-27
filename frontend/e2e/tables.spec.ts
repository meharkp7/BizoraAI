import { expect, test } from "@playwright/test";

const tables = [
  {
    table_id: "table-1",
    project_id: "project-1",
    graph_id: "graph-1",
    source_id: "paper-1",
    caption: "CASP14 results.",
    columns: ["Method", "TM-score"],
    rows: [
      ["AlphaFold2", "0.92"],
      ["Baseline", "0.71"],
    ],
    page: 4,
    quote: "Table 1 reports TM-scores on CASP14 targets.",
    created_by: "researcher-1",
  },
  {
    table_id: "table-2",
    project_id: "project-1",
    graph_id: "graph-1",
    source_id: "paper-1",
    caption: "Ablation study.",
    columns: ["Variant", "RMSD"],
    rows: [["Full model", "1.4"]],
    created_by: "researcher-1",
  },
];

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/graphs/**/tables", async (route) => {
    await route.fulfill({ json: tables });
  });
});

test("tables tab lists and renders extracted tables", async ({ page }) => {
  await page.goto("/g/project-1/graph-1/tables");
  await expect(page.getByRole("heading", { name: "Results tables" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "TM-score" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "AlphaFold2" })).toBeVisible();
  await expect(page.getByText("p. 4")).toBeVisible();

  await page.getByRole("button", { name: /table-2/ }).click();
  await expect(page.getByRole("columnheader", { name: "RMSD" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "AlphaFold2" })).toHaveCount(0);
});

test("workspace nav links to the tables tab", async ({ page }) => {
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    if (route.request().url().endsWith("/layout") || route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      json: {
        schema_version: "1.0",
        project_id: "project-1",
        graph_id: "graph-1",
        version: 1,
        title: "Vision transformer",
        source_ids: ["paper-1"],
        nodes: [],
        edges: [],
        created_by: "test",
        parent_version: null,
      },
    });
  });
  await page.goto("/g/project-1/graph-1");
  await page.getByRole("link", { name: "Tables" }).click();
  await expect(page).toHaveURL(/\/tables$/);
  await expect(page.getByRole("heading", { name: "Results tables" })).toBeVisible();
});
