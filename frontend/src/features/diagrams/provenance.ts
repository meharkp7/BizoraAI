/* Provenance labels for diagram elements. from paper: traced to a
   figure, page, or quote with decent confidence. assumed: low
   confidence or no evidence. illustrative: reserved for computed
   layout/geometry the paper does not state (schematic auto-layout,
   structure boxes), shown at the view level, never per element. */

export type DiagramProvenance = "from-paper" | "assumed";

export interface EvidenceLike {
  figure_id?: string | null;
  page?: number | null;
  quote?: string | null;
}

/** 0.6 matches the engine: it draws lower-confidence elements dashed. */
export const ASSUMED_CONFIDENCE_BELOW = 0.6;

export function hasEvidence(evidence: EvidenceLike | null | undefined): boolean {
  if (!evidence) return false;
  return Boolean(evidence.figure_id ?? evidence.page ?? evidence.quote);
}

export function elementProvenance(
  evidence: EvidenceLike | null | undefined,
  confidence: number | null | undefined,
): DiagramProvenance {
  if (!hasEvidence(evidence)) return "assumed";
  return (confidence ?? 1) < ASSUMED_CONFIDENCE_BELOW ? "assumed" : "from-paper";
}

export interface ProvenanceCounts {
  fromPaper: number;
  assumed: number;
}

export function countProvenance(
  items: readonly { evidence: EvidenceLike | null; confidence: number | null }[],
): ProvenanceCounts {
  let fromPaper = 0;
  let assumed = 0;
  for (const item of items) {
    if (elementProvenance(item.evidence, item.confidence) === "from-paper") fromPaper += 1;
    else assumed += 1;
  }
  return { fromPaper, assumed };
}

/** "figure:<id>" -> "<id>"; "text" and anything else -> null. */
export function figureIdFromSource(source: string | undefined): string | null {
  if (!source || !source.startsWith("figure:")) return null;
  const id = source.slice("figure:".length);
  return id === "" ? null : id;
}
