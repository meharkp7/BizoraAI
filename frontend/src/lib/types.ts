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
  /** Model-produced domain label from extraction; null when unclear. */
  domain_hint?: string | null;
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

export interface InterfaceSpec {
  name: string;
  kind: string;
  params: Record<string, string>;
}

export interface EntityResolution {
  node_id: string;
  domain: string;
  entity_type: string;
  display_label: string;
  generic: boolean;
  category: string;
  /** False for process/data entities, which never render as hardware. */
  physical: boolean;
  /** Pack-declared 2D symbol id for legends, process views, and schematics. */
  symbol: string;
  /** Representative 3D visual key, or null when only catalog parts render. */
  model_3d: string | null;
  interfaces: InterfaceSpec[];
  matched_terms: string[];
  confidence: number;
}

export interface DomainClassification {
  domain: string;
  confidence: number;
  signals: string[];
}

export interface GraphEntities {
  project_id: string;
  graph_id: string;
  version: number;
  classification: DomainClassification;
  entities: EntityResolution[];
}

/** One live measurement on a node or an edge (Stage 2 fills this). */
export interface OverlayValue {
  signal: string;
  value: number;
  unit: string | null;
}

/** Measured-overlay channel: live run values keyed by node and edge id.
 *  Empty until a real run exists; every view renders from the graph plus
 *  this channel and decorates nodes/edges when values arrive. */
export interface MeasuredOverlay {
  run_id: string | null;
  nodes: Record<string, OverlayValue[]>;
  edges: Record<string, OverlayValue[]>;
}

export const EMPTY_OVERLAY: MeasuredOverlay = { run_id: null, nodes: {}, edges: {} };

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

export interface GraphSummary {
  project_id: string;
  graph_id: string;
  version: number;
  title: string;
  source_ids: string[];
  node_count: number;
  edge_count: number;
  created_by: string;
  created_at: string;
}

export interface ArenaSideRef {
  project_id: string;
  graph_id: string;
  version?: number | null;
}

export interface ArenaSideSummary {
  project_id: string;
  graph_id: string;
  version: number;
  title: string;
}

export interface ArenaStructureSide {
  node_count: number;
  edge_count: number;
  kinds: Record<string, number>;
}

export interface ArenaLabelOverlap {
  label: string;
  a_node_ids: string[];
  b_node_ids: string[];
}

export interface ArenaUniqueLabel {
  label: string;
  node_ids: string[];
}

export interface ArenaMetricValue {
  raw_value: string;
  value: number | null;
  unit: string | null;
}

export interface ArenaMetricRow {
  name: string;
  a: ArenaMetricValue | null;
  b: ArenaMetricValue | null;
}

export interface ArenaComparison {
  a: ArenaSideSummary;
  b: ArenaSideSummary;
  structure_a: ArenaStructureSide;
  structure_b: ArenaStructureSide;
  shared_labels: ArenaLabelOverlap[];
  unique_a: ArenaUniqueLabel[];
  unique_b: ArenaUniqueLabel[];
  metrics: ArenaMetricRow[];
}

export interface TransplantRequest {
  source_project_id: string;
  source_graph_id: string;
  source_version?: number | null;
  node_ids: string[];
  created_by: string;
}

export interface TransplantResponse {
  project_id: string;
  graph_id: string;
  version: number;
  title: string;
  added_node_ids: string[];
  renamed: Record<string, string>;
  copied_edge_count: number;
  dropped_edge_count: number;
}

export interface MemoryFact {
  id: number;
  project_id: string;
  fact: string;
  created_by: string;
  created_at: string;
}

export type ProjectInviteRole = "viewer" | "editor" | "owner";
export type ProjectInviteStatus = "pending" | "accepted" | "revoked";

export interface ProjectInviteSummary {
  invite_id: string;
  project_id: string;
  email: string;
  role: ProjectInviteRole;
  status: ProjectInviteStatus;
  created_by: string;
  created_at: string;
  expires_at: string;
}

export interface ProjectInviteCreateResponse {
  invite: ProjectInviteSummary;
  token: string;
}

export interface ExportBundle {
  bundle_version: string;
  exported_at: string;
  project_id: string;
  graph_id: string;
  version: number;
  graph: MethodologyGraph;
  memory: MemoryFact[];
}

export interface GraphRevisionSummary {
  version: number;
  parent_version: number | null;
  title: string;
  created_by: string;
  created_at: string;
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

/** One localized component region inside a paper figure. Bbox is
 *  normalized x, y, width, height in 0..1; node_id is null when the
 *  region depicts no graph node. */
export interface FigureRegion {
  region_id: string;
  figure_id: string;
  bbox: [number, number, number, number];
  node_id: string | null;
  label: string;
  confidence: number | null;
}

/** One persisted paper figure with its regions (no image bytes). */
export interface PaperFigure {
  figure_id: string;
  project_id: string;
  graph_id: string;
  source_id: string;
  created_by: string;
  page: number | null;
  label: string | null;
  caption: string | null;
  kind: string;
  mime_type: string | null;
  sha256: string | null;
  byte_size: number | null;
  width: number | null;
  height: number | null;
  confidence: number | null;
  regions: FigureRegion[];
}

/** Outcome of a figure-overlay ingest. */
export interface FigureIngestResponse {
  figures: PaperFigure[];
  warnings: string[];
  truncated: boolean;
  skipped: number;
}

/** One number quoted from the paper; mirrors backend PaperReportedMetric JSON. */
export interface PaperReportedMetric {
  name: string;
  raw_value: string;
  value: number | null;
  unit: string | null;
  source_id: string;
  table_id: string | null;
  page: number | null;
  quote: string | null;
  locator: string | null;
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

export interface DuplicatePaper {
  project_id: string;
  graph_id: string;
  source_id: string;
  title: string;
  workspace_path: string;
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
  duplicate_of: DuplicatePaper | null;
}

export interface PaperImportRequest {
  source: string;
  title?: string;
  max_tables?: number;
}

export interface PaperImportResponse {
  source: string;
  source_url: string;
  filename: string;
  extraction: PaperExtractionResponse;
}

export interface SamplePaper {
  project_id: string;
  graph_id: string;
  source_id: string;
  title: string;
  workspace_path: string;
  available: boolean;
}

export interface DiagramEvalSummary {
  paper_id: string;
  recorded_at: string;
  validator_pass_rate: number;
  error_count: number;
  warning_count: number;
  input_tokens: number;
  output_tokens: number;
  provider_calls: number;
  gold_present: boolean;
  classification_kind: string | null;
}

export interface CopilotEvalSummary {
  total: number;
  passed: number;
  citation_accuracy: number;
  citation_recall: number;
  writes_detected: boolean;
  input_tokens: number;
  output_tokens: number;
  recorded_at: string;
}

export interface QualitySummary {
  generated_at: string;
  diagram_evals: DiagramEvalSummary[];
  copilot_eval: CopilotEvalSummary | null;
}

export interface UsageDay {
  date: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd_estimated: number;
  unmetered_calls: number;
}

export interface UsageTotals {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd_estimated: number;
  unmetered_calls: number;
}

export interface UsageCaps {
  daily_cap_usd: number;
  run_cap_usd: number;
  max_runs_per_day: number;
}

export interface UsageSummary {
  generated_at: string;
  currency: string;
  estimated: boolean;
  days: UsageDay[];
  totals: UsageTotals;
  caps: UsageCaps;
}

export interface RunUsage {
  run_id: string;
  project_id: string | null;
  graph_id: string | null;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd_estimated: number | null;
  unmetered: boolean;
  last_used_at: string | null;
}

export interface PaperUpload {
  file: File;
  project_id?: string;
  graph_id?: string;
  source_id?: string;
  created_by?: string;
  title?: string;
}

export interface ComponentSpec {
  name: string;
  value: string;
  unit: string | null;
  typical: boolean;
}

export interface ComponentPin {
  designator: string;
  name: string;
  function: string | null;
}

export type ConfigFieldType = "string" | "number" | "boolean" | "enum";

export interface ConfigField {
  key: string;
  label: string;
  type: ConfigFieldType;
  default: unknown;
  options: string[];
  unit: string | null;
  required: boolean;
  description: string | null;
}

export interface ComponentEvidence {
  source: string;
  note: string | null;
}

export interface ComponentSummary {
  component_id: string;
  domain: string;
  entity_type: string;
  category: string;
  kind: string;
  label: string;
  generic: boolean;
  manufacturer: string | null;
  part_number: string | null;
  headline: string;
  /** Pack-declared 2D symbol id, enriched from the entity type. */
  symbol: string;
}

export interface ComponentDetail extends ComponentSummary {
  description: string;
  datasheet_url: string | null;
  reference_url: string | null;
  specs: ComponentSpec[];
  pinout: ComponentPin[];
  interfaces: InterfaceSpec[];
  constraints: Record<string, string>;
  config_schema: ConfigField[];
  default_config: Record<string, unknown>;
  evidence: ComponentEvidence[];
}

export interface MissingInterface {
  kind: string;
  reason: string;
}

export interface ConstraintWarning {
  code: string;
  message: string;
}

export interface CompatibilityPreflight {
  compatible: boolean;
  target_node_id: string;
  component_id: string;
  missing_interfaces: MissingInterface[];
  preserved_edge_ids: string[];
  warnings: ConstraintWarning[];
  candidate: EntityResolution;
  candidate_label: string;
}

export interface RemovalPreflight {
  target_node_id: string;
  neighbor_node_ids: string[];
  dropped_edge_ids: string[];
  evidence: EvidenceRef[];
}

export interface CopilotProposal {
  node_id: string;
  component_id: string | null;
  kind: string;
  label: string;
  description: string | null;
  config: Record<string, unknown>;
  rationale: string;
}

export type CopilotCardKind =
  | "component"
  | "comparison"
  | "proposal"
  | "evidence"
  | "info"
  | "diagram";

export interface CopilotCardSource {
  source_id: string;
  page: number | null;
  quote: string | null;
  figure_label: string | null;
}

export interface CopilotDiagramRef {
  view: "methodology" | "schematic" | "structure";
  element_id: string;
  label: string;
}

export interface CopilotDiagramElement extends CopilotDiagramRef {
  kind: string | null;
  detail: string | null;
}

export interface CopilotCard {
  kind: CopilotCardKind;
  title: string;
  body: string;
  component_ids: string[];
  node_id: string | null;
  source?: CopilotCardSource | null;
  diagram_ref?: CopilotDiagramRef | null;
}

export interface PaperText {
  source_id: string;
  page_count: number | null;
  sha256: string | null;
  text: string;
}

export interface CopilotResponse {
  reply: string;
  cards: CopilotCard[];
  proposal: CopilotProposal | null;
}

export interface CopilotThreadSummary {
  thread_id: string;
  title: string;
  turn_count: number;
  updated_at: string;
}

export interface CopilotTurn {
  seq: number;
  role: "user" | "assistant";
  message: string;
  response: CopilotResponse | null;
}

export interface CopilotThread {
  thread_id: string;
  title: string;
  turns: CopilotTurn[];
}

export interface AdapterSummary {
  adapter_id: string;
  adapter_version: string;
  description: string;
  available: boolean;
  unavailable_reason: string | null;
}

export interface SimulationPreviewSection {
  heading: string;
  lines: string[];
}

export interface SimulationPreview {
  pack_id: string;
  title: string;
  sections: SimulationPreviewSection[];
  warnings: string[];
}

/** One generated solid, mirroring backend MeshPart JSON. */
export interface ProceduralPartData {
  name: string;
  vertices: [number, number, number][];
  faces: [number, number, number][];
}

/** Generated fallback mesh; mirrors the parts of backend ProceduralMesh JSON. */
export interface ProceduralMeshData {
  parts: ProceduralPartData[];
}

/** One node's 3D visual, mirroring backend NodeRenderSpec JSON. */
export interface NodeRenderSpec {
  node_id: string;
  label: string;
  asset_uri: string | null;
  fallback_package: string | null;
  illustrative: boolean;
  mesh: ProceduralMeshData | null;
}

/* Diagram IRs served by GET /papers/{paper_id}/diagrams. Field names
   mirror the backend JSON verbatim; keep in sync with
   src/bizora/contracts/diagram_ir.py and the PaperDiagramsResponse
   in src/bizora/api.py. The vendored engine consumes normalized
   versions of these (see features/diagrams/adapters.ts). */

export interface DiagramPlacement {
  x: number;
  y: number;
  rot: 0 | 90 | 180 | 270;
  mirror: boolean;
  flip: boolean;
}

export interface DiagramPoint {
  x: number;
  y: number;
}

export interface CircuitEvidenceJson {
  figure_id: string;
  bbox: [number, number, number, number] | null;
  quote: string | null;
}

export interface DiagramComponent {
  id: string;
  type: string;
  label: string;
  value: string | null;
  pins: Record<string, string>;
  pin_sides: Record<string, string> | null;
  placement: DiagramPlacement | null;
  confidence: number;
  evidence: CircuitEvidenceJson | null;
}

export interface DiagramNet {
  id: string;
  label: string;
  role: string;
  global: boolean;
}

export interface DiagramPort {
  id: string;
  net: string;
  label: string;
  dir: string;
  side: string;
  placement: DiagramPoint | null;
}

export interface DiagramSubcircuit {
  id: string;
  label: string;
  component_ids: string[];
}

export interface CircuitIRJson {
  version: 1;
  title: string;
  source: { figure_id: string; page: number };
  components: DiagramComponent[];
  nets: DiagramNet[];
  ports: DiagramPort[];
  subcircuits: DiagramSubcircuit[];
  layout: { unit: number | null } | null;
}

export interface DiagramGroup {
  id: string;
  label: string;
  parent: string | null;
}

export interface DiagramTextEvidence {
  page: number | null;
  figure_id: string | null;
  quote: string | null;
}

export interface DiagramNode {
  id: string;
  label: string;
  kind: string;
  group: string | null;
  detail: string | null;
  params: Record<string, unknown>;
  confidence: number;
  evidence: DiagramTextEvidence | null;
}

export interface DiagramEdge {
  from: string;
  to: string;
  label: string | null;
  kind: string;
}

export interface MethodologyIRJson {
  version: 1;
  title: string;
  groups: DiagramGroup[];
  nodes: DiagramNode[];
  edges: DiagramEdge[];
}

export interface DiagramBlockDims {
  w: number | null;
  h: number | null;
  d: number | null;
  unit: string | null;
}

export interface DiagramBlock {
  id: string;
  label: string;
  kind: string;
  count: number | { rows: number; cols: number } | null;
  dims: DiagramBlockDims | null;
  pos: string | DiagramPoint | null;
  part: string | null;
  tensor_shape: number[] | null;
  children: DiagramBlock[];
  confidence: number;
  evidence: DiagramTextEvidence | null;
}

export interface StructureIRJson {
  version: 1;
  title: string;
  root: DiagramBlock;
}

export interface DiagramValidationReportJson {
  errors: string[];
  warnings: string[];
  stats: Record<string, number>;
}

export interface PaperDiagramsResponse {
  methodology: MethodologyIRJson | null;
  circuits: CircuitIRJson[];
  structure: StructureIRJson | null;
  validation: Record<string, DiagramValidationReportJson>;
  sources: Record<string, string>;
}

/* What-if outcome served by POST /papers/{paper_id}/whatif. Field names
   mirror the backend JSON verbatim; keep in sync with the
   PaperWhatIfResponse in src/bizora/api.py. */

export interface WhatIfBasisJson {
  quote: string;
  page: number | null;
}

export interface PaperWhatIfParse {
  node_id: string;
  node_label: string;
  params: Record<string, string>;
}

export interface PaperWhatIfResponse {
  node_id: string;
  node_label: string;
  params_previous: Record<string, string>;
  params_applied: Record<string, string>;
  outcome: string;
  basis: WhatIfBasisJson[];
  assumptions: string[];
  confidence: number;
  from_cache: boolean;
}

export interface AuthUser {
  user_id: string;
  email: string;
  name: string;
  created_at: string;
}

export interface AuthResponse {
  user: AuthUser;
  token: string;
  expires_at: string;
}

export interface LibraryPaper {
  project_id: string;
  graph_id: string;
  source_id: string;
  title: string;
  created_at: string;
}

export interface PaperNote {
  id: number;
  paper_id: string;
  body: string;
  created_at: string;
  updated_at: string;
}
