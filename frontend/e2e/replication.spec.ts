import { expect, test } from "@playwright/test";

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
  ],
  edges: [],
  created_by: "test",
  parent_version: 1,
};

const history = [
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
];

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/graphs/project-1/graph-1/revisions", async (route) => {
    await route.fulfill({ json: history });
  });
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    await route.fulfill({ json: graph });
  });
  await page.route("**/api/v1/projects/*/graphs/*/replication-plan", async (route) => {
    await route.fulfill({
      json: {
        project_id: "project-1",
        graph_id: "graph-1",
        version: 2,
        steps: [
          {
            seq: 1,
            node_id: "input",
            label: "Image",
            kind: "input",
            action: "Provide input 'Image' (input).",
            verify: ["Confirm the input format matches the paper's description."],
          },
        ],
      },
    });
  });
});

test("workspace shows the replication checklist and tracks progress", async ({ page }) => {
  await page.goto("/g/project-1/graph-1?v=2");
  await expect(page.getByRole("heading", { name: "Vision transformer" })).toBeVisible();

  const panel = page.getByRole("region", { name: "Replication plan" });
  await expect(panel.getByText("Provide input 'Image' (input).")).toBeVisible();
  await expect(panel.getByText("0 of 1 steps done")).toBeVisible();

  await panel.getByRole("checkbox", { name: "Step 1: Image" }).check();
  await expect(panel.getByText("1 of 1 steps done")).toBeVisible();
});

test("narrate build fetches the spoken guide", async ({ page }) => {
  let narrationRequested = false;
  await page.addInitScript(() => {
    const spoken: string[] = [];
    (globalThis as unknown as Record<string, unknown>)["__spoken"] = spoken;
    class FakeUtterance {
      text: string;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(text: string) {
        this.text = text;
      }
    }
    (globalThis as unknown as Record<string, unknown>)["SpeechSynthesisUtterance"] =
      FakeUtterance;
    (globalThis as unknown as Record<string, unknown>)["speechSynthesis"] = {
      speak: (utterance: FakeUtterance) => {
        spoken.push(utterance.text);
        utterance.onend?.();
      },
      cancel: () => {},
    };
  });
  await page.route("**/api/v1/projects/*/graphs/*/replication-plan/narration", async (route) => {
    narrationRequested = true;
    await route.fulfill({
      json: {
        project_id: "project-1",
        graph_id: "graph-1",
        version: 2,
        intro: "Replication guide: 1 step.",
        lines: [
          { seq: 1, node_id: "input", text: "Step 1 of 1. Provide input." },
        ],
      },
    });
  });
  await page.goto("/g/project-1/graph-1?v=2");

  const panel = page.getByRole("region", { name: "Replication plan" });
  const narrate = panel.getByRole("button", { name: "Narrate build" });
  await expect(narrate).toBeVisible();
  await narrate.click();

  await expect
    .poll(() => narrationRequested, { message: "narration endpoint requested" })
    .toBe(true);
  await expect(panel.getByText("1 of 1 steps done")).toBeVisible();
  const spoken = await page.evaluate(
    () => (globalThis as unknown as Record<string, string[]>)["__spoken"],
  );
  expect(spoken).toEqual(["Replication guide: 1 step.", "Step 1 of 1. Provide input."]);
});
