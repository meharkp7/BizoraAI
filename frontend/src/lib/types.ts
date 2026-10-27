/* API contract types. Field names mirror the backend JSON verbatim;
   keep in sync with src/bizora/contracts. */

export type NodeKind =
  | "input"
  | "preprocessing"
  | "model"
  | "operation"
  | "loss"
  | "optimizer"
  | "evaluation"
  | "output"
  | "dataset"
  | "component";

export type RelationKind =
  | "data_flow"
  | "control_flow"
  | "optimizes"
  | "evaluates"
  | "depends_on";

export type Provenance = "extracted" | "inferred" | "verified" | "unresolved";

export type EvidenceStatus =
  | "supported"
  | "partial"
  | "conflicting"
  | "unverified";

export interface EvidenceRef {
  source_id: string;
  page: number | null;
  quote: string | null;
  figure_label: string | null;
  bbox: [number, number, number, number] | null;
  locator: string | null;
  status: EvidenceStatus;
}

export interface GraphNode {
  id: string;
  kind: NodeKind;
  label: string;
  description: string | null;
  config: Record<string, unknown>;
  input_shape: (number | null)[] | null;
  output_shape: (number | null)[] | null;
  evidence: EvidenceRef[];
  provenance: Provenance;
  confidence: number | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relation: RelationKind;
  label: string | null;
  evidence: EvidenceRef[];
  provenance: Provenance;
}

export interface ResearchBrief {
  problem: string | null;
  objectives: string[];
  findings: string[];
  limitations: string[];
}

export interface MethodologyGraph {
  schema_version: string;
  project_id: string;
  graph_id: string;
  version: number;
  title: string;
  source_ids: string[];
  nodes: GraphNode[];
  edges: GraphEdge[];
  created_by: string;
  parent_version: number | null;
  brief?: ResearchBrief | null;
}

export type PatchOperation =
  | "add_node"
  | "update_node_config"
  | "replace_node"
  | "add_edge"
  | "remove_edge"
  | "remove_node";

export interface GraphPatch {
  patch_id: string;
  base_graph_id: string;
  base_version: number;
  operation: PatchOperation;
  target_id: string | null;
  payload: Record<string, unknown>;
  rationale: string;
  requested_by: string;
}

export interface NodePosition {
  node_id: string;
  x: number;
  y: number;
  z: number;
}

export interface ViewportState {
  x: number;
  y: number;
  zoom: number;
}

export interface CameraState {
  target_x: number;
  target_y: number;
  target_z: number;
  distance: number;
  azimuth: number;
  polar: number;
}

export interface GraphLayout {
  project_id: string;
  graph_id: string;
  version: number;
  positions: NodePosition[];
  viewport: ViewportState | null;
  camera: CameraState | null;
  updated_by: string;
}

export interface ChangedNode {
  node_id: string;
  before: GraphNode;
  after: GraphNode;
}

export interface ChangedEdge {
  edge_id: string;
  before: GraphEdge;
  after: GraphEdge;
}

export interface GraphRevisionDiff {
  project_id: string;
  graph_id: string;
  base_version: number;
  target_version: number;
  added_nodes: GraphNode[];
  removed_nodes: GraphNode[];
  changed_nodes: ChangedNode[];
  added_edges: GraphEdge[];
  removed_edges: GraphEdge[];
  changed_edges: ChangedEdge[];
}

export type ResultKind = "measured" | "estimated" | "hypothesis";

export interface DatasetSplit {
  train: number;
  validation: number;
  test: number;
}

export interface ExperimentConfig {
  experiment_id: string;
  project_id: string;
  graph_id: string;
  graph_version: number;
  adapter_id: string;
  adapter_version: string;
  dataset_id: string;
  dataset_revision: string;
  seed: number;
  epochs: number;
  batch_size: number;
  learning_rate: number;
  split: DatasetSplit;
  code_revision: string;
  max_runtime_seconds: number;
  max_gpu_count: number;
  network_access: boolean;
}

export type RunState =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface ExperimentRun {
  run_id: string;
  config: ExperimentConfig;
  state: RunState;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface MetricRecord {
  metric_id: string;
  run_id: string;
  name: string;
  value: number;
  result_kind: ResultKind;
}

export interface ArtifactRecord {
  artifact_id: string;
  run_id: string;
  kind: string;
  uri: string;
  sha256: string | null;
  result_kind: ResultKind;
}

export type ComparisonVerdict = "valid" | "confounded" | "invalid";

export interface MetricComparison {
  name: string;
  baseline_value: number;
  variant_value: number;
  absolute_change: number;
  relative_change: number | null;
  relative_undefined_reason: string | null;
}

export interface SkippedMetric {
  name: string;
  reason: string;
}

export interface ConfigDifference {
  field: string;
  baseline: unknown;
  variant: unknown;
}

export interface GraphPair {
  baseline_graph_id: string;
  baseline_graph_version: number;
  variant_graph_id: string;
  variant_graph_version: number;
}

export interface RunComparison {
  baseline_run_id: string;
  variant_run_id: string;
  verdict: ComparisonVerdict;
  reasons: string[];
  graph: GraphPair;
  metrics: MetricComparison[];
  skipped_metrics: SkippedMetric[];
  config_differences: ConfigDifference[];
}

export interface GraphPatchBatch {
  patches: GraphPatch[];
}

export interface BizoraErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}

export interface ExtractedTable {
  table_id: string;
  project_id: string;
  graph_id: string;
  source_id: string;
  caption: string;
  columns: string[];
  rows: string[][];
  page: number | null;
  quote: string | null;
  created_by: string;
}

export interface PaperExtractionResponse {
  graph: MethodologyGraph;
  tables: ExtractedTable[];
  warnings: string[];
  page_count: number;
  truncated: boolean;
}

export interface SuggestedIds {
  project_id: string;
  graph_id: string;
  source_id: string;
}

export interface ParsedPaper {
  filename: string;
  title: string | null;
  authors: string[];
  page_count: number;
  chars: number;
  sha256: string;
  truncated: boolean;
  suggested: SuggestedIds;
}

export interface PaperUpload {
  file: File;
  project_id?: string;
  graph_id?: string;
  source_id?: string;
  created_by?: string;
  title?: string;
}
