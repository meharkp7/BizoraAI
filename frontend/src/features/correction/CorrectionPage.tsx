import { useState } from "react";
import { Link } from "react-router";
import { useApplyPatchBatch, useGraphRevision } from "../../app/queries.ts";
import { BizoraApiError } from "../../lib/api.ts";
import type { GraphPatch, MethodologyGraph } from "../../lib/types.ts";
import { ErrorState, LoadingState } from "../../components/states.tsx";
import { CorrectionReview } from "./CorrectionReview.tsx";
import styles from "./CorrectionPage.module.css";

export function CorrectionPage({
  projectId,
  graphId,
  version,
}: {
  projectId: string;
  graphId: string;
  version: number;
}) {
  const revision = useGraphRevision(projectId, graphId, version);
  const batch = useApplyPatchBatch(projectId, graphId);
  const [savedVersion, setSavedVersion] = useState<number | null>(null);

  if (revision.isPending) {
    return <LoadingState label={`Loading revision ${version} for review…`} />;
  }

  if (revision.isError) {
    const error = revision.error;
    const notFound = error instanceof BizoraApiError && error.isNotFound;
    return (
      <ErrorState
        title={notFound ? `Revision ${version} does not exist.` : "Could not load the revision."}
        detail={
          notFound
            ? "Step back to an existing revision."
            : error instanceof Error
              ? error.message
              : undefined
        }
        onRetry={() => void revision.refetch()}
      />
    );
  }

  function handleSubmit(patches: GraphPatch[]): void {
    setSavedVersion(null);
    batch.mutate(
      { patches },
      {
        onSuccess: (next: MethodologyGraph) => setSavedVersion(next.version),
      },
    );
  }

  const submitError = batch.error instanceof Error ? batch.error.message : null;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>Review extraction</h1>
          <p className={styles.subtitle}>
            {revision.data.title} · revision {revision.data.version} · accept, edit, or
            reject each extracted component
          </p>
        </div>
        <Link
          className={styles.back}
          to={`/g/${projectId}/${graphId}${savedVersion ? `?v=${savedVersion}` : ""}`}
        >
          Back to workspace
        </Link>
      </header>
      <CorrectionReview
        graph={revision.data}
        pending={batch.isPending}
        error={submitError}
        savedVersion={savedVersion}
        onSubmit={handleSubmit}
      />
    </div>
  );
}
