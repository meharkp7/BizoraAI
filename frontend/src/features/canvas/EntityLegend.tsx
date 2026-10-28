import type { GraphEntities } from "../../lib/types.ts";
import type { AssetSummary } from "./assetModels.ts";
import { CategoryGlyph } from "./CategoryGlyph.tsx";
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
  assetSummary = null,
}: {
  entities: GraphEntities | null;
  assetSummary?: AssetSummary | null;
}) {
  const entries = legendEntries(entities);
  if (entries.length === 0) return null;
  return (
    <aside className={styles.legend} aria-label="3D shape key">
      <DomainBadge entities={entities} />
      <AssetProvenanceBadge summary={assetSummary} />
      <ul className={styles.list}>
        {entries.map((entry) => (
          <li key={entry.category} className={styles.row}>
            <CategoryGlyph category={entry.category} />
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
