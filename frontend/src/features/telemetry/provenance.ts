/* Honesty labels for visual run elements. Mirrors
   src/bizora/streaming/provenance.py: same precedence, same wording. */

import type { ResultKind } from "../../lib/types.ts";
import type { VisualProvenance } from "./telemetryTypes.ts";

export interface ProvenanceInput {
  resultKind?: ResultKind | null;
  assumed?: boolean;
  illustrative?: boolean;
}

/**
 * Resolve the honesty label from existing grounding signals.
 * Illustrative wins over assumed; anything assumed or not measured
 * is never labelled measured.
 */
export function resolveVisualProvenance(input: ProvenanceInput): VisualProvenance {
  if (input.illustrative === true) return "illustrative";
  if (input.assumed === true) return "assumed";
  if (input.resultKind !== undefined && input.resultKind !== null && input.resultKind !== "measured") {
    return "assumed";
  }
  return "measured";
}

/** Short badge text for a provenance label. */
export function provenanceLabel(provenance: VisualProvenance): string {
  if (provenance === "assumed") return "Assumed";
  if (provenance === "illustrative") return "Illustrative";
  return "Measured";
}

/** Tooltip text for a provenance label. */
export function provenanceDescription(provenance: VisualProvenance): string {
  if (provenance === "assumed") return "Depends on an unverified assumption.";
  if (provenance === "illustrative") {
    return "A placeholder or stand-in, not observed data.";
  }
  return "Observed from a real run.";
}
