import { useState } from "react";
import { useComponentSearch } from "../../app/queries.ts";
import { useLibrarySelection } from "../../lib/store.ts";
import type { ComponentSummary } from "../../lib/types.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import { SymbolGlyph } from "../canvas/SymbolGlyph.tsx";
import { categoryLabel, domainLabel } from "../canvas/graph3d.ts";
import styles from "./LibraryPanel.module.css";

const DOMAINS = ["electronics", "iot", "quantization", "signal-processing", "distributed-systems"];

const CATEGORIES = [
  "package",
  "discrete",
  "passive",
  "power",
  "sensor",
  "compute",
  "network",
  "format",
  "signal",
  "service",
  "storage",
  "generic",
];

function IdentityBadge({ generic }: { generic: boolean }) {
  return generic ? (
    <span className={`${styles.badge} ${styles.generic}`}>generic</span>
  ) : (
    <span className={`${styles.badge} ${styles.exact}`}>exact part</span>
  );
}

function ResultCard({
  entry,
  selected,
  onOpen,
}: {
  entry: ComponentSummary;
  selected: boolean;
  onOpen: (componentId: string) => void;
}) {
  return (
    <li>
      <button
        type="button"
        className={selected ? styles.selected : undefined}
        onClick={() => onOpen(entry.component_id)}
        aria-pressed={selected}
      >
        <span className={styles.cardHead}>
          <SymbolGlyph symbol={entry.symbol || "generic"} />
          <span className={styles.cardLabel}>{entry.label}</span>
          <IdentityBadge generic={entry.generic} />
        </span>
        <span className={styles.cardMeta}>
          {entry.part_number ?? "no part number"} · {domainLabel(entry.domain)} ·{" "}
          {categoryLabel(entry.category)}
        </span>
        <span className={styles.cardHeadline}>{entry.headline}</span>
      </button>
    </li>
  );
}

export function LibraryPanel() {
  const [query, setQuery] = useState("");
  const [domain, setDomain] = useState("");
  const [category, setCategory] = useState("");
  const [identity, setIdentity] = useState<"all" | "exact" | "generic">("all");
  const { selectedComponentId, openComponent } = useLibrarySelection();
  const search = useComponentSearch({
    q: query.trim() === "" ? undefined : query.trim(),
    domain: domain === "" ? undefined : domain,
    category: category === "" ? undefined : category,
    generic: identity === "all" ? undefined : identity === "generic",
  });

  return (
    <div className={styles.library}>
      <form
        className={styles.filters}
        aria-label="Search the component library"
        onSubmit={(event) => event.preventDefault()}
      >
        <label className={styles.searchField}>
          Search components
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. NPN transistor, BME280, NF4"
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <div className={styles.filterRow}>
          <label>
            Domain
            <select value={domain} onChange={(event) => setDomain(event.target.value)}>
              <option value="">All domains</option>
              {DOMAINS.map((option) => (
                <option key={option} value={option}>
                  {domainLabel(option)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Category
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="">All categories</option>
              {CATEGORIES.map((option) => (
                <option key={option} value={option}>
                  {categoryLabel(option)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Identity
            <select
              value={identity}
              onChange={(event) => setIdentity(event.target.value as typeof identity)}
            >
              <option value="all">Exact + generic</option>
              <option value="exact">Exact parts only</option>
              <option value="generic">Generics only</option>
            </select>
          </label>
        </div>
      </form>
      {search.isPending ? <LoadingState label="Searching the library…" /> : null}
      {search.isError ? (
        <ErrorState
          title="Could not search the library."
          detail={search.error instanceof Error ? search.error.message : undefined}
          onRetry={() => void search.refetch()}
        />
      ) : null}
      {search.data !== undefined ? (
        search.data.length === 0 ? (
          <EmptyState title="No components match these filters." />
        ) : (
          <ul className={styles.results} aria-label="Library results">
            {search.data.map((entry) => (
              <ResultCard
                key={entry.component_id}
                entry={entry}
                selected={entry.component_id === selectedComponentId}
                onOpen={openComponent}
              />
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}
