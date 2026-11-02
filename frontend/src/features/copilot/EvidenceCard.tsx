import { useState } from "react";
import type { CopilotCard } from "../../lib/types.ts";
import { CitationPassage } from "./CitationPassage.tsx";
import styles from "./CopilotPanel.module.css";

const BADGES: Record<string, string> = {
  evidence: "Grounded in paper",
  info: "Measured",
  proposal: "Awaiting your approval",
};

/** Render one grounding card (evidence, run, or technique note). */
export function EvidenceCard({ card }: { card: CopilotCard }) {
  const [open, setOpen] = useState(false);
  // Run citations arrive as kind "info"; the backend titles only genuinely
  // measured runs "Measured run", so anything else must not wear that badge.
  const badge =
    card.kind === "info" && card.title !== "Measured run"
      ? "Not measured"
      : (BADGES[card.kind] ?? "Note");
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <span className={styles.cardTitle}>{card.title}</span>
        <span className={styles.badge}>{badge}</span>
      </div>
      <p className={styles.cardBody}>{card.body}</p>
      {card.source ? (
        <div className={styles.cardLinks}>
          <button type="button" onClick={() => setOpen((current) => !current)}>
            {open ? "Close paper passage" : "Open in paper"}
          </button>
        </div>
      ) : null}
      {open && card.source ? <CitationPassage source={card.source} /> : null}
    </div>
  );
}
