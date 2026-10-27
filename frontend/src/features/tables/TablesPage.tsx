import { useState } from "react";
import { useGraphTables } from "../../app/queries.ts";
import type { ExtractedTable } from "../../lib/types.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import styles from "./TablesPage.module.css";

function ResultsTable({ table }: { table: ExtractedTable }) {
  return (
    <figure className={styles.figure}>
      {table.caption ? <figcaption className={styles.caption}>{table.caption}</figcaption> : null}
      {table.page !== null && table.page !== undefined ? (
        <p className={styles.pageBadge}>p. {table.page}</p>
      ) : null}
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              {table.columns.map((column) => (
                <th key={column} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, index) => (
              <tr key={`${table.table_id}-row-${index}`}>
                {row.map((cell, cellIndex) => (
                  <td key={`${table.table_id}-cell-${index}-${cellIndex}`}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table.quote ? <blockquote className={styles.quote}>{table.quote}</blockquote> : null}
    </figure>
  );
}

export function TablesPage({ projectId, graphId }: { projectId: string; graphId: string }) {
  const tables = useGraphTables(projectId, graphId);
  const [activeId, setActiveId] = useState<string | null>(null);

  if (tables.isPending) {
    return <LoadingState label="Loading results tables…" />;
  }
  if (tables.isError) {
    return (
      <ErrorState
        title="Could not load the results tables."
        detail={tables.error instanceof Error ? tables.error.message : undefined}
        onRetry={() => void tables.refetch()}
      />
    );
  }
  if (tables.data.length === 0) {
    return (
      <EmptyState
        title="No results tables."
        detail="No tables were extracted for this graph. Re-uploading creates a separate graph instead."
      />
    );
  }

  const active = tables.data.find((table) => table.table_id === activeId) ?? tables.data[0];
  return (
    <div className={styles.page}>
      <h1>Results tables</h1>
      <div className={styles.layout}>
        <nav className={styles.index} aria-label="Tables">
          <ul>
            {tables.data.map((table) => (
              <li key={table.table_id}>
                <button
                  type="button"
                  className={table.table_id === active.table_id ? styles.selected : undefined}
                  onClick={() => setActiveId(table.table_id)}
                  aria-pressed={table.table_id === active.table_id}
                >
                  <span className={styles.tableId}>{table.table_id}</span>
                  {table.caption ? (
                    <span className={styles.tableCaption}>{table.caption}</span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <ResultsTable key={active.table_id} table={active} />
      </div>
    </div>
  );
}
