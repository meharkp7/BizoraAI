/** Honest dressing for nested structure blocks.
 *
 * The engine draws only top-level boxes; `layoutNestedParts` in the
 * structure view lays module members in a grid on their parent. These
 * pure helpers size that grid from the paper's own dims and name each
 * floating tag — no three.js here, so tests run without WebGL.
 */

export interface NestedDims {
  w?: number | null;
  h?: number | null;
  d?: number | null;
  unit?: string | null;
}

/** Unitless w*h area (tensor shapes are counts, not lengths): null
 *  unless both extents are positive numbers with no unit. Physical
 *  dims (unit set) never size the grid — the caption already says
 *  arrangement is illustrative, but silently mixing unit systems in
 *  one scale would still mislead. */
export function unitlessArea(dims: NestedDims | null | undefined): number | null {
  if (!dims || dims.unit !== null && dims.unit !== undefined) return null;
  const w = dims.w;
  const h = dims.h;
  if (typeof w !== "number" || typeof h !== "number") return null;
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return null;
  return w * h;
}

/** Footprint scale per sibling: log-area normalized across siblings
 *  that state unitless dims, so a 14336x4096 matrix reads larger than
 *  a 1024x4096 one without the small one vanishing (0.55 floor) or
 *  any child overflowing its grid cell (1.0 cap). Siblings without
 *  dims take the sibling mean; all-unknown grids stay uniform. */
export function nestedFootprintScales(
  dimsList: ReadonlyArray<NestedDims | null | undefined>,
): number[] {
  const areas = dimsList.map(unitlessArea);
  const known = areas.filter((area): area is number => area !== null);
  if (known.length === 0) return dimsList.map(() => 1);
  const logs = known.map((area) => Math.log2(area));
  const min = Math.min(...logs);
  const max = Math.max(...logs);
  const mean = logs.reduce((sum, value) => sum + value, 0) / logs.length;
  return areas.map((area) => {
    const log = area === null ? mean : Math.log2(area);
    const norm = max === min ? 1 : (log - min) / (max - min);
    return 0.55 + 0.45 * norm;
  });
}

function formatExtent(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100);
}

/** "14336x4096", "4x3 um", or null when no usable extents exist. */
export function dimsText(dims: NestedDims | null | undefined): string | null {
  if (!dims) return null;
  const extents = [dims.w, dims.h, dims.d].filter(
    (value): value is number =>
      typeof value === "number" && Number.isFinite(value) && value > 0,
  );
  if (extents.length < 2) return null;
  const text = extents.map(formatExtent).join("×");
  return dims.unit ? `${text} ${dims.unit}` : text;
}

/** Grid columns/rows for nested members on a w-by-d parent: square
 *  parents keep the classic root grid; wide or tall strips balance
 *  columns by aspect so cells stay chunky instead of slivered. */
export function nestedGrid(count: number, w: number, d: number): { cols: number; rows: number } {
  if (count <= 0) return { cols: 1, rows: 1 };
  const aspect = w / Math.max(d, 1e-6);
  const cols =
    aspect >= 0.75 && aspect <= 1.34
      ? Math.ceil(Math.sqrt(count))
      : Math.max(1, Math.min(count, Math.round(Math.sqrt(count * aspect))));
  return { cols, rows: Math.ceil(count / cols) };
}

/** Tag lift above a nested model by sibling slot: dense grids
 *  stagger tags across three heights so neighbors stop overlapping. */
export function nestedTagLift(siblingIndex: number): number {
  return 1.5 + (siblingIndex % 3) * 3.0;
}

/** Floating-tag text for a nested block: its label plus stated dims. */
export function nestedLabel(label: string, dims: NestedDims | null | undefined): string {
  const dimsSuffix = dimsText(dims);
  return dimsSuffix === null ? label : `${label} · ${dimsSuffix}`;
}

/** Stated tensor dims (unitless counts) at or above this read as a
 *  weight matrix. Physical dims carry a unit, so they never qualify
 *  however large. */
const WEIGHT_MIN_EXTENT = 256;

/** Whether a block is a leaf weight matrix: a childless module whose
 *  unitless w/h dims are matrix-sized (Q/K/V projections at 1024+),
 *  not a container. These dress as weight stacks instead of slabs. */
export function isWeightMatrix(
  kind: string,
  dims: NestedDims | null | undefined,
  childCount: number,
): boolean {
  if (kind !== "module" || childCount > 0) return false;
  if (!dims || dims.unit !== null && dims.unit !== undefined) return false;
  const w = dims.w;
  const h = dims.h;
  if (typeof w !== "number" || typeof h !== "number") return false;
  if (!Number.isFinite(w) || !Number.isFinite(h)) return false;
  return Math.min(w, h) >= WEIGHT_MIN_EXTENT;
}
