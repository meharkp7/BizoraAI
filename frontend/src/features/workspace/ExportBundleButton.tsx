import { useState } from "react";
import { BizoraApiError, api } from "../../lib/api.ts";

function downloadJson(filename: string, payload: unknown): void {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function ExportBundleButton({
  projectId,
  graphId,
  disabled,
}: {
  projectId: string;
  graphId: string;
  disabled: boolean;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onExport(): Promise<void> {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      const bundle = await api.exportBundle(projectId, graphId);
      downloadJson(`${projectId}-${graphId}-v${bundle.version}.json`, bundle);
    } catch (cause) {
      setError(
        cause instanceof BizoraApiError ? cause.message : "Could not export the bundle.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <span>
      <button type="button" disabled={disabled || pending} onClick={() => void onExport()}>
        {pending ? "Exporting…" : "Export bundle"}
      </button>
      {error && (
        <span role="alert">
          {" "}
          {error}
        </span>
      )}
    </span>
  );
}
