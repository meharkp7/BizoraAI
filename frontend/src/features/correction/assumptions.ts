/* Assumed-claim helpers for the correction loop.

Mirrors src/bizora/contracts/assumptions.py: assumed flags travel in
node config as `assumed` / `assumption_reason`, so the review UI reads
the same visible marking the backend persists. */

import type { GraphNode } from "../../lib/types.ts";

/** Config key carrying the boolean assumed flag. */
export const ASSUMED_CONFIG_KEY = "assumed";

/** Config key carrying the human-readable assumption reason. */
export const ASSUMPTION_REASON_CONFIG_KEY = "assumption_reason";

/** Actor recorded on patches submitted through the correction UI. */
export const CORRECTION_ACTOR = "correction-ui";

/** True only when the node carries an explicit true flag. */
export function isAssumed(node: GraphNode): boolean {
  return node.config[ASSUMED_CONFIG_KEY] === true;
}

/** The stored assumption reason, or null when absent or blank. */
export function assumptionReason(node: GraphNode): string | null {
  const reason = node.config[ASSUMPTION_REASON_CONFIG_KEY];
  if (typeof reason !== "string" || reason.trim() === "") return null;
  return reason;
}

/** True when the node links to at least one source reference. */
export function hasEvidence(node: GraphNode): boolean {
  return node.evidence.length > 0;
}

/** True when the node wants human review: assumed, or ungrounded. */
export function needsReview(node: GraphNode): boolean {
  return isAssumed(node) || !hasEvidence(node);
}
