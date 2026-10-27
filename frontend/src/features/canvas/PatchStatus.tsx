import { BizoraApiError } from "../../lib/api.ts";
import styles from "./PatchStatus.module.css";

export function PatchStatus({
  pending,
  error,
  savedVersion,
  onDismiss,
}: {
  pending: boolean;
  error: BizoraApiError | null;
  savedVersion: number | null;
  onDismiss: () => void;
}) {
  if (pending) {
    return (
      <div className={styles.status} role="status" aria-live="polite">
        Saving change…
      </div>
    );
  }
  if (error) {
    return (
      <div className={`${styles.status} ${styles.error}`} role="alert">
        <div>
          <strong>
            Change rejected ({error.code}).
          </strong>{" "}
          {error.message}
          {Object.keys(error.details).length > 0 ? (
            <details className={styles.details}>
              <summary>Details</summary>
              <pre className="mono">{JSON.stringify(error.details, null, 2)}</pre>
            </details>
          ) : null}
        </div>
        <button type="button" onClick={onDismiss}>
          Dismiss
        </button>
      </div>
    );
  }
  if (savedVersion !== null) {
    return (
      <div className={`${styles.status} ${styles.saved}`} role="status">
        <span>Saved as revision {savedVersion}.</span>
        <button type="button" onClick={onDismiss}>
          Dismiss
        </button>
      </div>
    );
  }
  return null;
}
