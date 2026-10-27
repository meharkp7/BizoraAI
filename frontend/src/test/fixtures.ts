import { HttpResponse } from "msw";
import type {
  ExperimentRun,
  GraphLayout,
  GraphRevisionDiff,
  MethodologyGraph,
  MetricRecord,
  RunComparison,
} from "../lib/types.ts";

export const graphFixture: MethodologyGraph = {
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
      description: "Patch embedding plus transformer blocks.",
      config: { layers: 12 },
      input_shape: [null, 768],
      output_shape: [null, 768],
      evidence: [
        {
          source_id: "paper-1",
          page: 4,
          quote: "The encoder stacks twelve blocks.",
          figure_label: null,
          bbox: null,
          locator: null,
          status: "supported",
        },
      ],
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

export const layoutFixture: GraphLayout = {
  project_id: "project-1",
  graph_id: "graph-1",
  version: 2,
  positions: [{ node_id: "input", x: 10, y: 20, z: 0 }],
  viewport: { x: 0, y: 0, zoom: 1 },
  camera: null,
  updated_by: "test",
};

export const diffFixture: GraphRevisionDiff = {
  project_id: "project-1",
  graph_id: "graph-1",
  base_version: 1,
  target_version: 2,
  added_nodes: [],
  removed_nodes: [],
  changed_nodes: [
    {
      node_id: "encoder",
      before: { ...graphFixture.nodes[1], config: { layers: 6 } },
      after: graphFixture.nodes[1],
    },
  ],
  added_edges: [],
  removed_edges: [],
  changed_edges: [],
};

function runFixture(runId: string, state: ExperimentRun["state"]): ExperimentRun {
  return {
    run_id: runId,
    config: {
      experiment_id: "exp-1",
      project_id: "project-1",
      graph_id: "graph-1",
      graph_version: 2,
      adapter_id: "bizora.deterministic-test",
      adapter_version: "0.1.0",
      dataset_id: "dataset-1",
      dataset_revision: "rev-1",
      seed: 7,
      epochs: 1,
      batch_size: 8,
      learning_rate: 0.001,
      split: { train: 0.8, validation: 0.1, test: 0.1 },
      code_revision: "abcdef1234567",
      max_runtime_seconds: 60,
      max_gpu_count: 0,
      network_access: false,
    },
    state,
    created_at: "2026-01-01T00:00:00Z",
    started_at: state === "pending" ? null : "2026-01-01T00:01:00Z",
    finished_at:
      state === "succeeded" || state === "failed" || state === "cancelled"
        ? "2026-01-01T00:02:00Z"
        : null,
    error: state === "failed" ? "adapter_failed: boom" : null,
  };
}

export const succeededRun = runFixture("run-ok", "succeeded");
export const failedRun = runFixture("run-bad", "failed");

export const metricsFixture: MetricRecord[] = [
  {
    metric_id: "metric-1",
    run_id: "run-ok",
    name: "accuracy",
    value: 0.92,
    result_kind: "measured",
  },
];

export const comparisonFixture: RunComparison = {
  baseline_run_id: "run-ok",
  variant_run_id: "run-ok-2",
  verdict: "valid",
  reasons: [],
  graph: {
    baseline_graph_id: "graph-1",
    baseline_graph_version: 2,
    variant_graph_id: "graph-1",
    variant_graph_version: 2,
  },
  metrics: [
    {
      name: "accuracy",
      baseline_value: 0.9,
      variant_value: 0.92,
      absolute_change: 0.02,
      relative_change: 0.0222,
      relative_undefined_reason: null,
    },
  ],
  skipped_metrics: [],
  config_differences: [],
};

export function notFound(code = "RESOURCE_NOT_FOUND", message = "Not found.") {
  return HttpResponse.json({ error: { code, message, details: {} } }, { status: 404 });
}
