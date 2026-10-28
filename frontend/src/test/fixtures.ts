import { HttpResponse } from "msw";
import type {
  AdapterSummary,
  CompatibilityPreflight,
  ComponentDetail,
  ComponentSummary,
  CopilotResponse,
  ExperimentRun,
  ExtractedTable,
  GraphEntities,
  GraphLayout,
  GraphRevisionDiff,
  MethodologyGraph,
  MetricRecord,
  NodeRenderSpec,
  PaperExtractionResponse,
  PaperReportedMetric,
  ParsedPaper,
  RunComparison,
  SimulationPreview,
} from "../lib/types.ts";

export const entitiesFixture: GraphEntities = {
  project_id: "project-1",
  graph_id: "graph-1",
  version: 2,
  classification: {
    domain: "electronics",
    confidence: 0.83,
    signals: ["sram", "transistor", "bias"],
  },
  entities: [
    {
      node_id: "input",
      domain: "electronics",
      entity_type: "memory-cell",
      display_label: "Memory cell",
      generic: false,
      category: "package",
      interfaces: [
        { name: "power", kind: "power", params: {} },
        { name: "data", kind: "data", params: {} },
      ],
      matched_terms: ["sram"],
      confidence: 0.75,
    },
    {
      node_id: "encoder",
      domain: "electronics",
      entity_type: "generic-component",
      display_label: "Transformer encoder",
      generic: true,
      category: "generic",
      interfaces: [],
      matched_terms: [],
      confidence: 0,
    },
  ],
};

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
  brief: {
    problem: "Transformers need huge labeled datasets.",
    objectives: ["Match CNNs with less supervision"],
    findings: [],
    limitations: ["Quadratic attention cost"],
  },
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
export const pendingRun = runFixture("run-pending", "pending");

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

export const reportedMetricsFixture: PaperReportedMetric[] = [
  {
    name: "accuracy",
    raw_value: "0.89",
    value: 0.89,
    unit: null,
    source_id: "paper-1",
    table_id: "table-1",
    page: 4,
    quote: "Ours: 0.89 (Accuracy)",
    locator: "Table table-1: column 'Accuracy' row 1 ('Ours')",
  },
];

export function notFound(code = "RESOURCE_NOT_FOUND", message = "Not found.") {
  return HttpResponse.json({ error: { code, message, details: {} } }, { status: 404 });
}

export const tableFixture: ExtractedTable = {
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
};

export const tableFixture2: ExtractedTable = {
  table_id: "table-2",
  project_id: "project-1",
  graph_id: "graph-1",
  source_id: "paper-1",
  caption: "Ablation study.",
  columns: ["Variant", "RMSD"],
  rows: [["Full model", "1.4"]],
  page: null,
  quote: null,
  created_by: "researcher-1",
};

export const parsedPaperFixture: ParsedPaper = {
  filename: "paper.pdf",
  title: "Vision transformer",
  authors: ["A. Researcher"],
  page_count: 12,
  chars: 42000,
  sha256: "0".repeat(64),
  truncated: false,
  suggested: {
    project_id: "vision-transformer-00000000",
    graph_id: "vision-transformer-graph-00000000",
    source_id: "paper-00000000",
  },
};

export const paperExtractionFixture: PaperExtractionResponse = {
  graph: graphFixture,
  tables: [tableFixture],
  warnings: [],
  page_count: 12,
  truncated: false,
};

export const componentSummaryFixture: ComponentSummary = {
  component_id: "npn-2n3904",
  domain: "electronics",
  entity_type: "transistor",
  category: "discrete",
  kind: "component",
  label: "2N3904 NPN transistor",
  generic: false,
  manufacturer: "onsemi",
  part_number: "2N3904",
  headline: "NPN general-purpose amplifier, 40 V / 200 mA, TO-92",
};

export const componentGenericFixture: ComponentSummary = {
  component_id: "resistor-generic",
  domain: "electronics",
  entity_type: "passive",
  category: "passive",
  kind: "component",
  label: "Resistor (generic)",
  generic: true,
  manufacturer: null,
  part_number: null,
  headline: "Generic resistor with settable resistance and footprint",
};

export const componentDetailFixture: ComponentDetail = {
  ...componentSummaryFixture,
  description: "2N3904 NPN general-purpose transistor for switching and small-signal amplification.",
  datasheet_url: null,
  reference_url: null,
  specs: [
    { name: "Polarity", value: "NPN", unit: null, typical: false },
    { name: "Collector current (max)", value: "200", unit: "mA", typical: false },
  ],
  pinout: [
    { designator: "1", name: "Emitter", function: "NPN emitter terminal" },
    { designator: "2", name: "Base", function: "Control terminal" },
    { designator: "3", name: "Collector", function: "NPN collector terminal" },
  ],
  interfaces: [
    { name: "power", kind: "power", params: {} },
    { name: "gate", kind: "signal", params: {} },
  ],
  constraints: { max_current_mA: "200" },
  config_schema: [
    {
      key: "part",
      label: "Part number",
      type: "string",
      default: "2N3904",
      options: [],
      unit: null,
      required: true,
      description: "Exact manufacturer part number.",
    },
  ],
  default_config: { part: "2N3904" },
  evidence: [{ source: "onsemi 2N3904 datasheet (2N3903/D)", note: "Electrical ratings." }],
};

export const preflightFixture: CompatibilityPreflight = {
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
    interfaces: [{ name: "power", kind: "power", params: {} }],
    matched_terms: ["transistor"],
    confidence: 0.75,
  },
  candidate_label: "2N3904 NPN transistor",
};

export const copilotFixture: CopilotResponse = {
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
};

export const adaptersFixture: AdapterSummary[] = [
  {
    adapter_id: "bizora.deterministic-test",
    adapter_version: "0.1.0",
    description: "Validate inputs and echo reproducibility fields without external effects.",
  },
];

export const renderSpecsFixture: NodeRenderSpec[] = [
  {
    node_id: "r1",
    label: "Passive component",
    asset_uri: null,
    fallback_package: "resistor-generic",
    illustrative: true,
    mesh: {
      parts: [
        {
          name: "body",
          vertices: [
            [-0.8, 0, -0.4],
            [0.8, 0, -0.4],
            [0.8, 0.8, -0.4],
            [-0.8, 0.8, -0.4],
            [-0.8, 0, 0.4],
            [0.8, 0, 0.4],
            [0.8, 0.8, 0.4],
            [-0.8, 0.8, 0.4],
          ],
          faces: [
            [0, 1, 2],
            [0, 2, 3],
            [4, 6, 5],
            [4, 7, 6],
            [0, 4, 5],
            [0, 5, 1],
            [2, 6, 7],
            [2, 7, 3],
            [0, 3, 7],
            [0, 7, 4],
            [1, 5, 6],
            [1, 6, 2],
          ],
        },
      ],
    },
  },
];

export const simulationPreviewFixture: SimulationPreview = {
  pack_id: "electronics",
  title: "SPICE circuit preview",
  sections: [
    { heading: "Netlist", lines: ["V1 in 0 DC 5", "R1 in out 1k", "R2 out 0 1k"] },
    { heading: "Bill of materials (3 parts)", lines: ["V1: Supply voltage x1", "R1, R2: Resistor x2"] },
  ],
  warnings: ["WARN: electronics_missing_pullup: node d1 wants a pull-up"],
};
