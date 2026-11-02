import { usePaperText } from "../../app/queries.ts";
import type { CopilotCardSource } from "../../lib/types.ts";
import styles from "./CopilotPanel.module.css";
import { findPassage } from "./paperPassage.ts";

/** Render one cited passage with the quote highlighted in context. */
export function CitationPassage({ source }: { source: CopilotCardSource }) {
  const paper = usePaperText(source.source_id, true);

  if (paper.isLoading) {
    return <p className={styles.passageNote}>Loading paper text…</p>;
  }
  if (paper.isError || !paper.data) {
    return (
      <p className={styles.error} role="alert">
        The paper text is not available for {source.source_id}.
      </p>
    );
  }
  const match = findPassage(paper.data.text, source.page, source.quote);
  const heading =
    match.page !== null
      ? `Page ${match.page} of ${source.source_id}`
      : `Start of ${source.source_id}`;
  return (
    <div className={styles.passage}>
      <p className={styles.passageHead}>{heading}</p>
      <p className={styles.passageBody}>
        {match.before}
        {match.quoteFound ? <mark>{match.quote}</mark> : null}
        {match.after}
      </p>
      {!match.quoteFound ? (
        <p className={styles.passageNote}>
          The exact quote was not found; showing the{" "}
          {match.page !== null ? `start of page ${match.page}` : "start of the paper"}.
        </p>
      ) : null}
      {source.page !== null && !match.pageFound ? (
        <p className={styles.passageNote}>
          Page {source.page} has no marker in the extraction; searched the whole paper.
        </p>
      ) : null}
    </div>
  );
}
