// Intermediate representations (IRs). The extraction pipeline produces these; the engine only renders them.
export interface Evidence { figure_id?: string; page?: number; bbox?: [number, number, number, number]; quote?: string }

// ---------------- CircuitIR ----------------
export type ComponentType =
  | 'nmos' | 'pmos' | 'resistor' | 'capacitor' | 'inductor' | 'diode'
  | 'vsource' | 'isource' | 'ground' | 'inverter' | 'buffer' | 'amp' | 'comparator' | 'block';
export type Side = 'left' | 'right' | 'up' | 'down';
export interface Placement { x: number; y: number; rot?: 0 | 90 | 180 | 270; mirror?: boolean; flip?: boolean }
export interface CircuitComponent {
  id: string; type: ComponentType | string; label?: string; value?: string;
  pins: Record<string, string>; placement?: Placement; pin_sides?: Record<string, Side>;
  confidence?: number; evidence?: Evidence;
}
export interface CircuitNet { id: string; label?: string; role?: 'supply' | 'ground' | 'signal' | 'clock' | 'input' | 'output'; global?: boolean }
export interface CircuitPort { id: string; net: string; label?: string; dir?: 'in' | 'out' | 'inout'; side?: Side; placement?: { x: number; y: number } }
export interface CircuitIR {
  version: 1; title?: string; source?: { figure_id?: string; page?: number };
  components: CircuitComponent[]; nets: CircuitNet[]; ports?: CircuitPort[];
  subcircuits?: { id: string; label?: string; component_ids: string[] }[];
  layout?: { unit?: number };
}

// ---------------- MethodologyIR ----------------
export type NodeKind = 'input' | 'process' | 'decision' | 'store' | 'model' | 'evaluation' | 'dataset' | 'output';
export interface MethGroup { id: string; label: string; parent?: string }
export interface MethNode {
  id: string; label: string; kind?: NodeKind | string; group?: string; detail?: string;
  params?: Record<string, string | number>; confidence?: number; evidence?: Evidence;
}
export interface MethEdge { from: string; to: string; label?: string; kind?: 'data' | 'control' | 'feedback' }
export interface MethodologyIR { version: 1; title?: string; source?: { figure_id?: string; page?: number }; groups?: MethGroup[]; nodes: MethNode[]; edges: MethEdge[] }

// ---------------- StructureIR ----------------
export type BlockKind = 'chip' | 'array' | 'cell' | 'periphery' | 'module' | 'board' | 'layer' | 'part' | 'region';
export interface Block {
  id: string; label: string; kind: BlockKind | string;
  count?: { rows: number; cols: number } | number;
  dims?: { w?: number; h?: number; d?: number; unit?: string }; // w: x extent, d: y extent, h: vertical height
  pos?: 'left' | 'right' | 'top' | 'bottom' | 'center' | { x: number; y: number };
  part?: string; tensor_shape?: number[]; children?: Block[]; confidence?: number; evidence?: Evidence;
}
export interface StructureIR { version: 1; title?: string; source?: { figure_id?: string; page?: number }; root: Block }

export interface Issue { code: string; message: string; ref?: string }
export interface ValidationResult { errors: Issue[]; warnings: Issue[]; stats: Record<string, number> }
