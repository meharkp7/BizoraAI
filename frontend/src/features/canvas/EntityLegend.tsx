import type { GraphEntities, MeasuredOverlay } from "../../lib/types.ts";
import { EMPTY_OVERLAY } from "../../lib/types.ts";
import type { AssetSummary, PartLegendEntry } from "./assetModels.ts";
import { measuredSummary } from "./flowElements.ts";
import { SymbolGlyph } from "./SymbolGlyph.tsx";
import { domainLabel, legendEntries } from "./graph3d.ts";
import styles from "./EntityLegend.module.css";

export function DomainBadge({ entities }: { entities: GraphEntities | null }) {
  if (!entities) return null;
  const { classification } = entities;
  const generic = classification.domain === "generic";
  return (
    <p className={styles.badge} aria-live="polite">
      <span className={styles.badgeDot} data-generic={generic} aria-hidden="true" />
      {generic ? (
        <>Generic domain — the paper did not match a known system vocabulary.</>
      ) : (
        <>
          {domainLabel(classification.domain)} ·{" "}
          {Math.round(classification.confidence * 100)}% confidence
        </>
      )}
    </p>
  );
}

export function AssetProvenanceBadge({ summary }: { summary: AssetSummary | null | undefined }) {
  if (!summary || summary.total === 0) return null;
  return (
    <p
      className={styles.badge}
      role="status"
      aria-label={`${summary.measured} measured models, ${summary.illustrative} illustrative stand-ins`}
    >
      <span className={styles.badgeDot} data-generic={summary.measured === 0} aria-hidden="true" />
      3D models: {summary.measured} measured · {summary.illustrative} illustrative
    </p>
  );
}

export function EntityLegend({
  entities,
  title = "Symbol key",
  inline = false,
}: {
  entities: GraphEntities | null;
  title?: string;
  /** Stack in the page flow instead of overlaying the stage corner. */
  inline?: boolean;
}) {
  const entries = legendEntries(entities);
  if (entries.length === 0) return null;
  return (
    <aside
      className={inline ? `${styles.legend} ${styles.legendInline}` : styles.legend}
      aria-label={title}
    >
      <DomainBadge entities={entities} />
      <ul className={styles.list}>
        {entries.map((entry) => (
          <li key={entry.symbol} className={styles.row}>
            <SymbolGlyph symbol={entry.symbol} />
            <span className={styles.name}>
              {entry.label}
              <span className={styles.count} aria-label={`${entry.count} components`}>
                ×{entry.count}
              </span>
            </span>
            <span className={styles.types}>{entry.entityTypes.join(" · ")}</span>
          </li>
        ))}
      </ul>
    </aside>
  );
}

export function PartLegend({
  entities,
  parts,
  assetSummary = null,
  unmodeled = 0,
  overlay = EMPTY_OVERLAY,
}: {
  entities: GraphEntities | null;
  parts: PartLegendEntry[];
  assetSummary?: AssetSummary | null;
  unmodeled?: number;
  overlay?: MeasuredOverlay;
}) {
  if (parts.length === 0) return null;
  const measuredCount = parts.reduce(
    (sum, part) => sum + (overlay.nodes[part.nodeId]?.length ?? 0),
    0,
  );
  return (
    <aside className={styles.legend} aria-label="3D part key">
      <DomainBadge entities={entities} />
      <AssetProvenanceBadge summary={assetSummary} />
      {measuredCount > 0 ? (
        <p className={styles.badge} role="note">
          {measuredCount} measured {measuredCount === 1 ? "value" : "values"} from run{" "}
          {overlay.run_id ?? "unknown"}.
        </p>
      ) : null}
      {unmodeled > 0 ? (
        <p className={styles.badge} role="note">
          {unmodeled} more {unmodeled === 1 ? "component has" : "components have"} no part model
          and {unmodeled === 1 ? "stays" : "stay"} in the 2D views.
        </p>
      ) : null}
      <ul className={styles.list}>
        {parts.map((part) => {
          const summary = measuredSummary(overlay.nodes[part.nodeId]);
          return (
            <li key={part.nodeId} className={styles.row}>
              <span
                className={styles.badgeDot}
                data-generic={part.provenance === "illustrative"}
                aria-hidden="true"
              />
              <span className={styles.name}>
                {part.partLabel}
                <span className={styles.count}>{part.provenance}</span>
                {summary ? <span className={styles.count}>measured: {summary}</span> : null}
              </span>
              <span className={styles.types}>
                {[part.nodeLabel, part.entityType].filter(Boolean).join(" · ")}
              </span>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
