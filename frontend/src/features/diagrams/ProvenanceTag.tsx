import styles from "./ProvenanceTag.module.css";
import type { DiagramProvenance } from "./provenance.ts";

const TAG_HELP: Record<DiagramProvenance | "illustrative", string> = {
  "from-paper": "Traced to a paper figure, page, or quote.",
  assumed: "Low confidence or no evidence: treat as unverified.",
  illustrative: "Computed layout or geometry the paper does not state.",
};

export function ProvenanceTag({ value }: { value: DiagramProvenance | "illustrative" }) {
  return (
    <span className={`${styles.tag} ${styles[value]}`} title={TAG_HELP[value]}>
      {value === "from-paper" ? "from paper" : value}
    </span>
  );
}

/** Defines the three labels once per view so readers can trust them. */
export function ProvenanceLegend() {
  return (
    <dl className={styles.legend} aria-label="Provenance key">
      <div>
        <dt>
          <ProvenanceTag value="from-paper" />
        </dt>
        <dd>traced to a figure, page, or quote</dd>
      </div>
      <div>
        <dt>
          <ProvenanceTag value="assumed" />
        </dt>
        <dd>low confidence or no evidence</dd>
      </div>
      <div>
        <dt>
          <ProvenanceTag value="illustrative" />
        </dt>
        <dd>computed layout, not in the paper</dd>
      </div>
    </dl>
  );
}
