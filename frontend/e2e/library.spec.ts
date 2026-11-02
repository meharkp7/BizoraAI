import { expect, test } from "@playwright/test";

const WORKSPACE_URL = "/g/project-1/graph-1?v=2";

const graph = {
  schema_version: "1.0",
  project_id: "project-1",
  graph_id: "graph-1",
  version: 2,
  title: "Vision transformer",
  source_ids: ["paper-1"],
  nodes: [
    {
      id: "input",
      kind: "input",
      label: "Image",
      description: null,
      config: {},
      input_shape: null,
      output_shape: [null, 768],
      evidence: [],
      provenance: "verified",
      confidence: 0.99,
    },
    {
      id: "encoder",
      kind: "model",
      label: "Transformer encoder",
      description: null,
      config: { layers: 12 },
      input_shape: [null, 768],
      output_shape: [null, 768],
      evidence: [],
      provenance: "extracted",
      confidence: null,
    },
  ],
  edges: [
    {
      id: "e1",
      source: "input",
      target: "encoder",
      relation: "data_flow",
      label: null,
      evidence: [],
      provenance: "extracted",
    },
  ],
  created_by: "test",
  parent_version: 1,
};

const componentDetail = {
  component_id: "npn-2n3904",
  domain: "electronics",
  entity_type: "transistor",
  category: "discrete",
  kind: "component",
  label: "2N3904 NPN transistor",
  generic: false,
  manufacturer: "onsemi",
  part_number: "2N3904",
  headline: "NPN general-purpose amplifier",
  description: "NPN transistor.",
  datasheet_url: null,
  reference_url: null,
  specs: [{ name: "Polarity", value: "NPN", unit: null, typical: false }],
  pinout: [{ designator: "1", name: "Emitter", function: null }],
  interfaces: [{ name: "power", kind: "power", params: {} }],
  constraints: {},
  config_schema: [
    {
      key: "part",
      label: "Part number",
      type: "string",
      default: "2N3904",
      options: [],
      unit: null,
      required: true,
      description: null,
    },
  ],
  default_config: { part: "2N3904" },
  evidence: [],
};

const preflight = {
  compatible: true,
  target_node_id: "encoder",
  component_id: "npn-2n3904",
  missing_interfaces: [],
  preserved_edge_ids: ["e1"],
  warnings: [],
  candidate: {
    node_id: "encoder",
    domain: "electronics",
    entity_type: "transistor",
    display_label: "2N3904 NPN transistor",
    generic: false,
    category: "discrete",
    interfaces: [],
    matched_terms: [],
    confidence: 0.75,
  },
  candidate_label: "2N3904 NPN transistor",
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/layout") || route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    if (url.endsWith("/entities")) {
      await route.fulfill({
        json: {
          project_id: "project-1",
          graph_id: "graph-1",
          version: 2,
          classification: { domain: "electronics", confidence: 0.8, signals: [] },
          entities: [],
        },
      });
      return;
    }
    await route.fulfill({ json: graph });
  });
  await page.route("**/api/v1/graphs/**/diff*", async (route) => {
    await route.fulfill({
      json: {
        project_id: "project-1",
        graph_id: "graph-1",
        base_version: 2,
        target_version: 2,
        added_nodes: [],
        removed_nodes: [],
        changed_nodes: [],
        added_edges: [],
        removed_edges: [],
        changed_edges: [],
      },
    });
  });
  await page.route("**/api/v1/graphs/project-1/graph-1/revisions", async (route) => {
    await route.fulfill({
      json: [
        {
          version: 1,
          parent_version: null,
          title: "Vision transformer",
          created_by: "test",
          created_at: "2026-01-01T00:00:00Z",
        },
        {
          version: 2,
          parent_version: 1,
          title: "Vision transformer",
          created_by: "test",
          created_at: "2026-01-02T00:00:00Z",
        },
      ],
    });
  });
  await page.route("**/api/v1/graphs/**/patches", async (route) => {
    await route.fulfill({
      status: 201,
      json: { ...graph, version: 3, parent_version: 2 },
    });
  });
  await page.route("**/api/v1/components", async (route) => {
    await route.fulfill({ json: [componentDetail] });
  });
  await page.route("**/api/v1/components/*", async (route) => {
    await route.fulfill({ json: componentDetail });
  });
  await page.route("**/nodes/*/preflight", async (route) => {
    await route.fulfill({ json: preflight });
  });
  await page.route("**/revisions/*/copilot", async (route) => {
    await route.fulfill({
      json: {
        reply: "Closest library matches: 2N3904 NPN transistor.",
        cards: [
          {
            kind: "component",
            title: "2N3904 NPN transistor",
            body: "Exact part 2N3904 (onsemi)",
            component_ids: ["npn-2n3904"],
            node_id: null,
          },
        ],
        proposal: null,
      },
    });
  });
  await page.route("**/api/v1/experiments/adapters", async (route) => {
    await route.fulfill({
      json: [
        {
          adapter_id: "bizora.deterministic-test",
          adapter_version: "0.1.0",
          description: "Deterministic validation.",
          available: true,
          unavailable_reason: null,
        },
      ],
    });
  });
});

test("library tab searches and previews a replacement", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  await page.getByRole("list", { name: "Graph nodes" }).getByRole("button", { name: /Transformer encoder/ }).click();
  await page.getByRole("tab", { name: "Library" }).click();
  await page.getByLabel("Search components").fill("2N3904");
  await page.getByRole("button", { name: /2N3904 NPN transistor/ }).first().click();

  await expect(page.getByText("Polarity")).toBeVisible();
  await expect(page.getByText(/Compatible: all known interfaces/)).toBeVisible();
  await expect(page.getByText(/Preserved connections \(1\)/)).toBeVisible();
});

test("palette adds a library component as a new node", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  await page.getByRole("tab", { name: "Library" }).click();
  await page.getByLabel("Search components").fill("2N3904");
  await page.getByRole("button", { name: /2N3904 NPN transistor/ }).first().click();

  const section = page.getByRole("region", { name: "Add to graph" });
  await expect(section.getByLabel("Node ID")).toHaveValue("2n3904-npn-transistor");
  await section.getByRole("button", { name: "Add to graph (new revision)" }).click();

  await expect(page.getByText("Saved as revision 3.")).toBeVisible();
  await expect(page).toHaveURL(/v=3/);
});

test("library offers the method-pipeline domain", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  await page.getByRole("tab", { name: "Library" }).click();

  const domain = page.getByLabel("Domain");
  await expect(domain.getByRole("option", { name: "Method pipeline" })).toBeAttached();
  await domain.selectOption("method-pipeline");
  await expect(domain).toHaveValue("method-pipeline");
});

test("run panel names unavailable adapters", async ({ page }) => {
  await page.route("**/api/v1/experiments/adapters", async (route) => {
    await route.fulfill({
      json: [
        {
          adapter_id: "bizora.deterministic-test",
          adapter_version: "0.1.0",
          description: "Deterministic validation.",
          available: true,
          unavailable_reason: null,
        },
        {
          adapter_id: "bizora.torch-train",
          adapter_version: "0.1.0",
          description: "Torch training.",
          available: false,
          unavailable_reason: "torch is not installed in the execution environment.",
        },
      ],
    });
  });

  await page.goto(WORKSPACE_URL);
  const panel = page.getByRole("region", { name: "Run revision" });
  await expect(panel.getByText(/Connected adapters:/)).toBeVisible();
  await expect(panel.getByText(/bizora\.torch-train/)).toBeVisible();
  await expect(panel.getByText(/torch is not installed/)).toBeVisible();
});

test("copilot answers with a library card", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  await page.getByRole("button", { name: "Open research copilot" }).click();
  await page.getByLabel("Copilot message").fill("find NPN transistor");
  await page.getByRole("button", { name: "Ask" }).click();

  await expect(page.getByText(/Closest library matches/)).toBeVisible();
  await page.getByRole("button", { name: "Open in library" }).click();
  await expect(page.getByText("Polarity")).toBeVisible();
});
