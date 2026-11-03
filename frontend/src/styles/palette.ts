/** Single numeric source for diagram part colors.
 *
 * The 3D renderer needs concrete numbers (three.js materials, canvas
 * plates), so CSS variables cannot serve it directly. Keep these values
 * in sync with the `--color-part-*` tokens in `./tokens.css`, which mirror
 * the same palette for diagram chrome (legend swatches). */

export const PART_TINTS: Readonly<Record<string, number>> = {
  decision: 0x9a6234,
  evaluation: 0x9a6234,
  process: 0x5f7052,
  input: 0x3f5a66,
  output: 0x3f5a66,
  nmos: 0x4a6a8a,
  pmos: 0x4a6a8a,
  resistor: 0x8a7350,
  capacitor: 0x8a7350,
  inductor: 0x8a7350,
  diode: 0x8a7350,
  inverter: 0x5f7052,
  buffer: 0x5f7052,
  amp: 0x2e343b,
  comparator: 0x2e343b,
  vsource: 0x2e343b,
  isource: 0x2e343b,
  ground: 0x2e343b,
};

export const SLATE_BODY = 0x5a6470;
export const SLAB_BODY = 0x3a4250;
export const STEEL_BODY = 0x9aa4ae;

/** Engraved identity-plate colors, per color scheme. */
export const PLATE_COLORS = {
  dark: { bg: "#222a33", fg: "#f0e9d8", rule: "#8a94a0" },
  light: { bg: "#f3ead8", fg: "#2a2620", rule: "#8a7d5f" },
} as const;

/** Fallback when the `--color-surface` token is unreadable (tests). */
export const SURFACE_FALLBACK = "#faf7ec";

/** Fallback mesh tint when no part color is found. */
export const MESH_FALLBACK = "#999999";
