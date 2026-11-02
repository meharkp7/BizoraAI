import { HttpResponse } from "msw";
import type {
  AdapterSummary,
  ArenaComparison,
  AuthResponse,
  CompatibilityPreflight,
  LibraryPaper,
  ComponentDetail,
  ComponentSummary,
  CopilotResponse,
  CopilotThread,
  CopilotThreadSummary,
  ExperimentRun,
  ExtractedTable,
  GraphEntities,
  GraphLayout,
  GraphRevisionDiff,
  GraphRevisionSummary,
  MethodologyGraph,
  MetricRecord,
  NodeRenderSpec,
  PaperDiagramsResponse,
  PaperExtractionResponse,
  PaperFigure,
  PaperNote,
  PaperReportedMetric,
  PaperText,
  PaperWhatIfResponse,
  PaperImportResponse,
  ParsedPaper,
  QualitySummary,
  RemovalPreflight,
  RunComparison,
  RunUsage,
  UsageSummary,
  SamplePaper,
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
      physical: true,
      symbol: "bitcell",
      model_3d: null,
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
      physical: true,
      symbol: "generic",
      model_3d: null,
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

export const revisionHistoryFixture: GraphRevisionSummary[] = [
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

export const removalPreflightFixture: RemovalPreflight = {
  target_node_id: "encoder",
  neighbor_node_ids: ["input"],
  dropped_edge_ids: ["e1"],
  evidence: [],
};

export function notFound(code = "RESOURCE_NOT_FOUND", message = "Not found.") {
  return HttpResponse.json({ error: { code, message, details: {} } }, { status: 404 });
}

export const figuresFixture: PaperFigure[] = [
  {
    figure_id: "paper-1-p2-f1-a1b2c3d4",
    project_id: "project-1",
    graph_id: "graph-1",
    source_id: "paper-1",
    created_by: "researcher-1",
    page: 2,
    label: "Figure 1",
    caption: "Model overview.",
    kind: "diagram",
    mime_type: "image/png",
    sha256: "1".repeat(64),
    byte_size: 42000,
    width: 800,
    height: 600,
    confidence: 0.9,
    regions: [
      {
        region_id: "paper-1-p2-f1-a1b2c3d4-r1",
        figure_id: "paper-1-p2-f1-a1b2c3d4",
        bbox: [0.1, 0.2, 0.3, 0.25],
        node_id: "encoder",
        label: "encoder stack",
        confidence: 0.8,
      },
      {
        region_id: "paper-1-p2-f1-a1b2c3d4-r2",
        figure_id: "paper-1-p2-f1-a1b2c3d4",
        bbox: [0.6, 0.6, 0.2, 0.2],
        node_id: null,
        label: "legend",
        confidence: 0.4,
      },
    ],
  },
];

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
  duplicate_of: null,
};

export const samplePaperFixture: SamplePaper = {
  project_id: "project-1",
  graph_id: "graph-1",
  source_id: "paper-1",
  title: "Vision transformer",
  workspace_path: "/g/project-1/graph-1",
  available: true,
};

export const paperExtractionFixture: PaperExtractionResponse = {
  graph: graphFixture,
  tables: [tableFixture],
  warnings: [],
  page_count: 12,
  truncated: false,
};

export const paperImportFixture: PaperImportResponse = {
  source: "1706.03762v7",
  source_url: "https://arxiv.org/pdf/1706.03762v7",
  filename: "1706.03762v7.pdf",
  extraction: paperExtractionFixture,
};

export const usageSummaryFixture: UsageSummary = {
  generated_at: "2026-11-02T10:00:00+00:00",
  currency: "USD",
  estimated: true,
  days: [
    {
      date: "2026-11-02",
      calls: 3,
      input_tokens: 1200,
      output_tokens: 300,
      cost_usd_estimated: 0.0081,
      unmetered_calls: 1,
    },
  ],
  totals: {
    calls: 3,
    input_tokens: 1200,
    output_tokens: 300,
    cost_usd_estimated: 0.0081,
    unmetered_calls: 1,
  },
  caps: { daily_cap_usd: 25.0, run_cap_usd: 5.0, max_runs_per_day: 50 },
};

export const runUsageFixture: RunUsage[] = [
  {
    run_id: "run-1",
    project_id: "project-1",
    graph_id: "graph-1",
    calls: 1,
    input_tokens: 0,
    output_tokens: 0,
    cost_usd_estimated: null,
    unmetered: true,
    last_used_at: "2026-11-02T09:00:00+00:00",
  },
  {
    run_id: "run-2",
    project_id: "project-1",
    graph_id: "graph-1",
    calls: 2,
    input_tokens: 5000,
    output_tokens: 1000,
    cost_usd_estimated: 0.03,
    unmetered: false,
    last_used_at: "2026-11-01T09:00:00+00:00",
  },
];

export const qualitySummaryFixture: QualitySummary = {
  generated_at: "2026-11-02T10:00:00+00:00",
  diagram_evals: [
    {
      paper_id: "sram-puf-tilting",
      recorded_at: "2026-10-30T07:53:10+00:00",
      validator_pass_rate: 1.0,
      error_count: 0,
      warning_count: 1,
      input_tokens: 37603,
      output_tokens: 15160,
      provider_calls: 4,
      gold_present: false,
      classification_kind: "circuit",
    },
  ],
  copilot_eval: {
    total: 30,
    passed: 30,
    citation_accuracy: 1.0,
    citation_recall: 1.0,
    writes_detected: false,
    input_tokens: 0,
    output_tokens: 0,
    recorded_at: "2026-11-01T18:25:35+00:00",
  },
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
  symbol: "transistor",
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
  symbol: "passive",
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
    physical: true,
    symbol: "transistor",
    model_3d: null,
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

export const copilotThreadFixture: CopilotThreadSummary = {
  thread_id: "thread-1",
  title: "Earlier chat",
  turn_count: 2,
  updated_at: "2026-10-01T00:00:00+00:00",
};

export const copilotThreadDetailFixture: CopilotThread = {
  thread_id: "thread-1",
  title: "Earlier chat",
  turns: [
    { seq: 0, role: "user", message: "find NPN transistor", response: null },
    {
      seq: 1,
      role: "assistant",
      message: "Closest library matches: 2N3904 NPN transistor.",
      response: copilotFixture,
    },
  ],
};

export const graphSummariesFixture = [
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

export const arenaFixture: ArenaComparison = {
  a: {
    project_id: "project-1",
    graph_id: "graph-1",
    version: 2,
    title: "Vision transformer",
  },
  b: {
    project_id: "project-2",
    graph_id: "graph-2",
    version: 1,
    title: "SRAM PUF",
  },
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

export const memoryFixture = [
  {
    id: 1,
    project_id: "project-1",
    fact: "The tapeout uses 65nm.",
    created_by: "cross-paper-ui",
    created_at: "2026-11-02T00:00:00+00:00",
  },
];

export const transplantFixture = {
  project_id: "project-2",
  graph_id: "graph-2",
  version: 2,
  title: "Transplant 1 block from graph-1",
  added_node_ids: ["encoder"],
  renamed: {},
  copied_edge_count: 0,
  dropped_edge_count: 1,
};

export const paperTextFixture: PaperText = {
  source_id: "paper-1",
  page_count: 2,
  sha256: "0".repeat(64),
  text: "[Page 1]\nIntro words about the design.\n[Page 2]\nThe filter corner is 4 kHz per the paper, measured at room temperature.",
};

/** Encode one copilot turn as SSE frames, mirroring the backend stream. */
export function copilotStreamBody(
  response: CopilotResponse,
  statuses: string[] = ["Answering from the workspace graph…"],
): string {
  const frames = statuses.map(
    (message) => `event: status\ndata: ${JSON.stringify({ message })}\n\n`,
  );
  frames.push(`event: done\ndata: ${JSON.stringify({ response })}\n\n`);
  return frames.join("");
}

export const adaptersFixture: AdapterSummary[] = [
  {
    adapter_id: "bizora.deterministic-test",
    adapter_version: "0.1.0",
    description: "Validate inputs and echo reproducibility fields without external effects.",
    available: true,
    unavailable_reason: null,
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

const DIAGRAM_FIGURE_ID = "paper-1-p2-f1-a1b2c3d4";

/** Diagram IRs for paper-1. Test data only: every view renders them
 *  through the real engine, including one low-confidence node and one
 *  component drawn dashed to exercise the assumed labels. */
export const diagramsFixture: PaperDiagramsResponse = {
  methodology: {
    version: 1,
    title: "Test methodology",
    groups: [{ id: "train", label: "Training", parent: null }],
    nodes: [
      {
        id: "m-input",
        label: "Patch embedding input",
        kind: "input",
        group: null,
        detail: null,
        params: {},
        confidence: 0.9,
        evidence: { page: 2, figure_id: null, quote: "Images are split into patches." },
      },
      {
        id: "m-encode",
        label: "Transformer encoder",
        kind: "model",
        group: "train",
        detail: "Twelve stacked blocks.",
        params: { layers: 12 },
        confidence: 0.95,
        evidence: { page: 4, figure_id: null, quote: "The encoder stacks twelve blocks." },
      },
      {
        id: "m-check",
        label: "Converged?",
        kind: "decision",
        group: "train",
        detail: null,
        params: {},
        confidence: 0.45,
        evidence: null,
      },
      {
        id: "m-output",
        label: "Class token output",
        kind: "output",
        group: null,
        detail: null,
        params: {},
        confidence: 0.8,
        evidence: { page: 5, figure_id: null, quote: null },
      },
    ],
    edges: [
      { from: "m-input", to: "m-encode", label: "patches", kind: "data" },
      { from: "m-encode", to: "m-check", label: null, kind: "data" },
      { from: "m-check", to: "m-output", label: "yes", kind: "control" },
    ],
  },
  circuits: [
    {
      version: 1,
      title: "Test cell",
      source: { figure_id: DIAGRAM_FIGURE_ID, page: 2 },
      components: [
        {
          id: "m1",
          type: "nmos",
          label: "M1",
          value: null,
          pins: { d: "n-out", g: "n-in", s: "n-vss" },
          pin_sides: null,
          placement: { x: 30, y: 40, rot: 0, mirror: false, flip: false },
          confidence: 0.9,
          evidence: { figure_id: DIAGRAM_FIGURE_ID, bbox: [10, 20, 30, 40], quote: null },
        },
        {
          id: "r1",
          type: "resistor",
          label: "R1",
          value: "1k",
          pins: { a: "n-vdd", b: "n-out" },
          pin_sides: null,
          placement: { x: 30, y: 15, rot: 0, mirror: false, flip: false },
          confidence: 0.5,
          evidence: null,
        },
        {
          id: "g1",
          type: "ground",
          label: "GND",
          value: null,
          pins: { g: "n-vss" },
          pin_sides: null,
          placement: { x: 30, y: 65, rot: 0, mirror: false, flip: false },
          confidence: 0.99,
          evidence: { figure_id: DIAGRAM_FIGURE_ID, bbox: null, quote: null },
        },
      ],
      nets: [
        { id: "n-vdd", label: "VDD", role: "supply", global: true },
        { id: "n-vss", label: "VSS", role: "ground", global: true },
        { id: "n-in", label: "IN", role: "input", global: false },
        { id: "n-out", label: "OUT", role: "signal", global: false },
      ],
      ports: [],
      subcircuits: [],
      layout: null,
    },
  ],
  structure: {
    version: 1,
    title: "Test chip",
    root: {
      id: "chip",
      label: "test chip",
      kind: "chip",
      count: null,
      dims: null,
      pos: null,
      part: null,
      tensor_shape: null,
      children: [
        {
          id: "arr",
          label: "cell array",
          kind: "array",
          count: { rows: 2, cols: 3 },
          dims: null,
          pos: null,
          part: null,
          tensor_shape: null,
          children: [
            {
              id: "cell",
              label: "cell",
              kind: "cell",
              count: null,
              dims: { w: 1, h: 1, d: 1, unit: null },
              pos: null,
              part: null,
              tensor_shape: null,
              children: [],
              confidence: 0.9,
              evidence: { page: 5, figure_id: null, quote: "Each cell occupied 12 um2." },
            },
          ],
          confidence: 0.9,
          evidence: { page: 5, figure_id: null, quote: "Array of 2000 cells." },
        },
        {
          id: "peri",
          label: "row decoder",
          kind: "periphery",
          count: null,
          dims: null,
          pos: "left",
          part: null,
          tensor_shape: null,
          children: [],
          confidence: 0.4,
          evidence: null,
        },
      ],
      confidence: 1,
      evidence: null,
    },
  },
  validation: {
    methodology: { errors: [], warnings: [], stats: { nodes: 4, edges: 3, groups: 1 } },
    [`circuit:${DIAGRAM_FIGURE_ID}`]: {
      errors: [],
      warnings: [],
      stats: { components: 3, nets: 4, ports: 0 },
    },
    structure: { errors: [], warnings: [], stats: { blocks: 4 } },
  },
  sources: {
    methodology: "text",
    [`circuit:${DIAGRAM_FIGURE_ID}`]: `figure:${DIAGRAM_FIGURE_ID}`,
    structure: "text",
  },
};

/** A paper whose figures yielded no diagram IRs: every view must fall
 *  back to the paper's own figure, never a placeholder diagram. */
export const thinDiagramsFixture: PaperDiagramsResponse = {
  methodology: null,
  circuits: [],
  structure: null,
  validation: {},
  sources: {},
};

export const whatIfFixture: PaperWhatIfResponse = {
  node_id: "fabricate",
  node_label: "Fabricate array",
  params_previous: { cell_count: "2000" },
  params_applied: { cell_count: "5000" },
  outcome: "Estimated 10000 bits from 5000 cells at two bits per cell.",
  basis: [{ quote: "two bits per cell", page: 3 }],
  assumptions: ["Yield holds at the larger array size."],
  confidence: 0.62,
  from_cache: false,
};

export const simulationPreviewFixture: SimulationPreview = {
  pack_id: "electronics",
  title: "SPICE circuit preview",
  sections: [
    { heading: "Netlist", lines: ["V1 in 0 DC 5", "R1 in out 1k", "R2 out 0 1k"] },
    { heading: "Bill of materials (3 parts)", lines: ["V1: Supply voltage x1", "R1, R2: Resistor x2"] },
  ],
  warnings: ["WARN: electronics_missing_pullup: node d1 wants a pull-up"],
};

export const authFixture: AuthResponse = {
  user: {
    user_id: "user-1",
    email: "me@example.com",
    name: "Me",
    created_at: "2026-01-01T00:00:00+00:00",
  },
  token: "test-token",
  expires_at: "2026-01-08T00:00:00+00:00",
};

export const libraryFixture: LibraryPaper[] = [
  {
    project_id: "project-papers",
    graph_id: "graph-papers",
    source_id: "paper-papers",
    title: "AlphaFold paper",
    created_at: "2026-01-02T00:00:00+00:00",
  },
];

export const notesFixture: PaperNote[] = [
  {
    id: 1,
    paper_id: "paper-papers",
    body: "Reproduce the tilt test first.",
    created_at: "2026-01-03T00:00:00+00:00",
    updated_at: "2026-01-03T00:00:00+00:00",
  },
];
