/* Local "try in schematic" sandbox: library components merged into a
paper circuit client-side so a part can be auditioned in context. Pure
derivation from the circuit IR plus the trial list — nothing here
touches the endpoint data or persists. Trial parts carry no evidence,
so the existing provenance mechanics mark them assumed (dashed), and
their illustrative placements sit below the paper's own. */

import type { CircuitComponent as EngineComponent } from "../../diagram-engine/ir.js";
import { getSymbol } from "../../diagram-engine/symbols.js";
import type {
  CircuitIRJson,
  ComponentDetail,
  ComponentPin,
  DiagramComponent,
} from "../../lib/types.ts";

/** One library part on trial in a schematic. */
export interface SandboxItem {
  key: string;
  figureId: string;
  componentId: string;
  label: string;
  engineType: string;
  value: string | null;
  /** Library pinout in order; the sandbox UI maps each to a net. */
  pinout: Pick<ComponentPin, "designator" | "name">[];
  /** Designator -> net id; absent means unconnected. */
  pinNets: Record<string, string>;
}

/** Engine symbol types with real drawings (see symbols.ts). */
const KNOWN_ENGINE_TYPES = new Set([
  "nmos",
  "pmos",
  "resistor",
  "capacitor",
  "inductor",
  "diode",
  "vsource",
  "isource",
  "ground",
  "inverter",
  "buffer",
  "amp",
  "comparator",
]);

const ALIASES: Record<string, string> = {
  nmosfet: "nmos",
  nfet: "nmos",
  pmosfet: "pmos",
  pfet: "pmos",
  res: "resistor",
  cap: "capacitor",
  ind: "inductor",
  coil: "inductor",
  inv: "inverter",
  not: "inverter",
  gnd: "ground",
};

function normalizeToken(value: string | null | undefined): string {
  return (value ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

/** Map a library entry to an engine symbol type. Exact and alias
 *  matches draw the real symbol; anything else draws the engine's
 *  generic block (which lays out every pin), never a wrong symbol. */
export function sandboxEngineType(
  detail: Pick<ComponentDetail, "kind" | "label" | "entity_type" | "category">,
): string {
  const candidates = [
    detail.kind,
    detail.entity_type,
    detail.category,
    ...detail.label.toLowerCase().split(/[^a-z0-9]+/),
  ].map(normalizeToken);
  for (const candidate of candidates) {
    if (KNOWN_ENGINE_TYPES.has(candidate)) return candidate;
    const alias = ALIASES[candidate];
    if (alias) return alias;
  }
  return `trial:${normalizeToken(detail.kind) || "part"}`;
}

/** Symbol pin names for an engine type, in layout order. */
export function sandboxSymbolPins(engineType: string): string[] {
  return Object.keys(getSymbol({ type: engineType } as EngineComponent).pins);
}

/** Map library pinout entries onto the symbol's pins: positionally for
 *  real symbols (extras have nowhere to land), one-to-one for the
 *  generic block (which draws every pin it is given). */
export function sandboxPinMap(
  engineType: string,
  pinout: Pick<ComponentPin, "designator" | "name">[],
): { designator: string; symbolPin: string }[] {
  if (!KNOWN_ENGINE_TYPES.has(engineType)) {
    return pinout.map((pin) => ({ designator: pin.designator, symbolPin: pin.designator }));
  }
  const symbols = sandboxSymbolPins(engineType);
  return pinout.slice(0, symbols.length).map((pin, index) => ({
    designator: pin.designator,
    symbolPin: symbols[index],
  }));
}

/** A display value from the catalog specs (resistance, capacitance,
 *  …), or null when no spec reads as one. */
export function sandboxValue(detail: Pick<ComponentDetail, "specs">): string | null {
  const spec = detail.specs.find((entry) =>
    /resistance|capacitance|inductance|forward.?voltage|\bvalue\b|\brating\b/i.test(entry.name),
  );
  if (!spec) return null;
  return `${spec.value}${spec.unit ? ` ${spec.unit}` : ""}`;
}

function trialId(key: string): string {
  return `try-${key.replace(/[^a-zA-Z0-9_-]/g, "")}`;
}

function netKind(role: string): "supply" | "ground" | "other" {
  const key = role.toLowerCase();
  if (key.includes("supply") || key.includes("power") || key === "vdd" || key === "vcc") {
    return "supply";
  }
  if (key.includes("ground") || key === "gnd" || key === "vss") return "ground";
  return "other";
}

/** Sanity warnings for one trial part: supply shorted to ground, two
 *  supply rails tied together. Unwired pins are normal (open stubs),
 *  so silence there. */
export function sandboxWarnings(
  item: SandboxItem,
  nets: Pick<CircuitIRJson["nets"][number], "id" | "role">[],
): string[] {
  const roles = new Map(nets.map((net) => [net.id, netKind(net.role)]));
  const wired = Object.values(item.pinNets).filter((net) => roles.has(net));
  const kinds = wired.map((net) => roles.get(net));
  const warnings: string[] = [];
  if (kinds.includes("supply") && kinds.includes("ground")) {
    warnings.push("Shorts a supply net to ground.");
  }
  if (kinds.filter((kind) => kind === "supply").length > 1) {
    warnings.push("Ties two supply rails together.");
  }
  return warnings;
}

const TRIAL_EXPORT_VERSION = 1;

/** Serialize one figure's trials for download (shareable, restorable). */
export function serializeTrials(items: SandboxItem[]): string {
  return JSON.stringify(
    {
      version: TRIAL_EXPORT_VERSION,
      items: items.map((item) => ({
        componentId: item.componentId,
        label: item.label,
        engineType: item.engineType,
        value: item.value,
        pinout: item.pinout,
        pinNets: item.pinNets,
      })),
    },
    null,
    2,
  );
}

/** Parse an export file back into trials for this figure. Throws on
 *  anything that isn't a trial export. */
export function parseTrialsExport(text: string, figureId: string): SandboxItem[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("not a trial export");
  }
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    (parsed as { version?: unknown }).version !== TRIAL_EXPORT_VERSION ||
    !Array.isArray((parsed as { items?: unknown }).items)
  ) {
    throw new Error("not a trial export");
  }
  const stamp = Date.now();
  return ((parsed as { items: unknown[] }).items).map((entry, index) => {
    const item = entry as Partial<SandboxItem>;
    if (
      typeof item.componentId !== "string" ||
      typeof item.label !== "string" ||
      typeof item.engineType !== "string" ||
      !Array.isArray(item.pinout) ||
      typeof item.pinNets !== "object" ||
      item.pinNets === null
    ) {
      throw new Error("not a trial export");
    }
    return {
      key: `import-${stamp}-${index}`,
      figureId,
      componentId: item.componentId,
      label: item.label,
      engineType: item.engineType,
      value: typeof item.value === "string" ? item.value : null,
      pinout: item.pinout
        .filter((pin) => typeof pin?.designator === "string")
        .map((pin) => ({ designator: pin.designator, name: String(pin.name ?? "") })),
      pinNets: Object.fromEntries(
        Object.entries(item.pinNets).filter(
          (pair): pair is [string, string] => typeof pair[1] === "string",
        ),
      ),
    };
  });
}

/** Merge trial items into a circuit copy: illustrative placements
 *  below the paper's lowest row, wired pins to nets the circuit has,
 *  no evidence (so assumed/dashed by the existing rules). Pins left
 *  unwired land on private single-pin nets, which the engine draws as
 *  honest open stubs (and which keep required-pin validation green).
 *  Items for other figures pass through untouched. */
export function applySandboxItems(
  circuit: CircuitIRJson,
  items: SandboxItem[],
): CircuitIRJson {
  const mine = items.filter((item) => item.figureId === circuit.source.figure_id);
  if (mine.length === 0) return circuit;
  const nets = new Set(circuit.nets.map((net) => net.id));
  const placed = circuit.components
    .map((component) => component.placement)
    .filter((placement) => placement !== null);
  const baseX = placed.length > 0 ? Math.min(...placed.map((p) => p.x)) : 0;
  const baseY = placed.length > 0 ? Math.max(...placed.map((p) => p.y)) : 0;
  const openNets: CircuitIRJson["nets"] = [];
  const trials: DiagramComponent[] = mine.map((item, index) => {
    const id = trialId(item.key);
    const pins: Record<string, string> = {};
    for (const { designator, symbolPin } of sandboxPinMap(item.engineType, item.pinout)) {
      const net = item.pinNets[designator];
      if (net && nets.has(net)) {
        pins[symbolPin] = net;
      } else {
        const open = `try-open-${id}-${symbolPin}`;
        pins[symbolPin] = open;
        openNets.push({ id: open, label: "open", role: "signal", global: false });
      }
    }
    return {
      id,
      type: item.engineType,
      label: `${item.label} · trial`,
      value: item.value,
      pins,
      pin_sides: null,
      placement:
        placed.length > 0
          ? { x: baseX, y: baseY + 14 + index * 14, rot: 0, mirror: false, flip: false }
          : null,
      confidence: 0,
      evidence: null,
    };
  });
  return {
    ...circuit,
    components: [...circuit.components, ...trials],
    nets: [...circuit.nets, ...openNets],
  };
}
