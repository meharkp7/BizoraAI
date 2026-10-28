import type { CopilotCard } from "../../lib/types.ts";
import styles from "./CopilotPanel.module.css";

const BADGES: Record<string, string> = {
  evidence: "Grounded in paper",
  info: "Measured",
  proposal: "Awaiting your approval",
};

/** Render one grounding card (evidence, run, or technique note). */
export function EvidenceCard({ card }: { card: CopilotCard }) {
  const badge = BADGES[card.kind] ?? "Note";
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <span className={styles.cardTitle}>{card.title}</span>
        <span className={styles.badge}>{badge}</span>
      </div>
      <p className={styles.cardBody}>{card.body}</p>
    </div>
  );
}
