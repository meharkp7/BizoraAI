import { provenanceDescription, provenanceLabel } from "./provenance.ts";
import type { VisualProvenance } from "./telemetryTypes.ts";
import styles from "./ProvenanceBadge.module.css";

/**
 * Honesty badge for a visual run element: Measured (observed from a
 * real run), Assumed (depends on an unverified assumption), or
 * Illustrative (a placeholder or stand-in).
 */
export function ProvenanceBadge({
  provenance,
  reason,
}: {
  provenance: VisualProvenance;
  reason?: string | null;
}) {
  return (
    <span
      className={`${styles.badge} ${styles[provenance]}`}
      title={reason ?? provenanceDescription(provenance)}
    >
      {provenanceLabel(provenance)}
    </span>
  );
}
