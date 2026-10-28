import { useSimulationPreview } from "../../app/queries.ts";
import { ErrorState, LoadingState } from "../../components/states.tsx";
import styles from "./SimulationPreview.module.css";

export function SimulationPreview({
  projectId,
  graphId,
  version,
}: {
  projectId: string;
  graphId: string;
  version: number;
}) {
  const preview = useSimulationPreview(projectId, graphId, version);

  if (preview.isPending) return <LoadingState label="Loading simulation preview…" />;
  if (preview.isError)
    return (
      <ErrorState
        title="Could not load the simulation preview."
        detail={preview.error instanceof Error ? preview.error.message : undefined}
        onRetry={() => void preview.refetch()}
      />
    );
  if (!preview.data) return null;

  return (
    <section className={styles.panel} aria-label="Simulation preview">
      <h2>{preview.data.title}</h2>
      <p className={styles.hint}>Pack: {preview.data.pack_id}</p>
      {preview.data.sections.map((section) => (
        <div key={section.heading}>
          <h3 className={styles.heading}>{section.heading}</h3>
          <pre className={styles.code}>{section.lines.join("\n")}</pre>
        </div>
      ))}
      {preview.data.warnings.length > 0 ? (
        <ul className={styles.warnings} aria-label="Simulation warnings">
          {preview.data.warnings.map((warning, index) => (
            // Warnings carry no ids; the API order is deterministic.
            <li key={`${warning.slice(0, 48)}-${index}`}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
