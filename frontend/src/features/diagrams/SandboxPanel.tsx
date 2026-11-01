import { useRef, useState } from "react";
import { useSchematicSandbox } from "../../lib/store.ts";
import type { DiagramNet } from "../../lib/types.ts";
import {
  parseTrialsExport,
  sandboxPinMap,
  sandboxWarnings,
  serializeTrials,
} from "./schematicSandbox.ts";
import styles from "./SandboxPanel.module.css";

/** Trial parts on this schematic: which library part, each pin wired to
 *  which paper net (or unconnected), and removal. Local only — the
 *  endpoint data is untouched and trials vanish on refresh. */
export function SandboxPanel({
  figureId,
  nets,
}: {
  figureId: string;
  nets: DiagramNet[];
}) {
  const items = useSchematicSandbox((state) => state.items);
  const removeSandboxItem = useSchematicSandbox((state) => state.removeSandboxItem);
  const setSandboxPinNet = useSchematicSandbox((state) => state.setSandboxPinNet);
  const clearSandboxFigure = useSchematicSandbox((state) => state.clearSandboxFigure);
  const addSandboxItem = useSchematicSandbox((state) => state.addSandboxItem);
  const [importError, setImportError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const mine = items.filter((item) => item.figureId === figureId);
  if (mine.length === 0) return null;

  function download(): void {
    const blob = new Blob([serializeTrials(mine)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `schematic-trials-${figureId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function importFile(file: File): void {
    setImportError(null);
    void file
      .text()
      .then((text) => {
        for (const item of parseTrialsExport(text, figureId)) addSandboxItem(item);
      })
      .catch(() => setImportError("That file isn't a trial export."));
  }

  return (
    <section className={styles.panel} aria-label="Trying in schematic">
      <div className={styles.head}>
        <h3>Trying in schematic ({mine.length})</h3>
        <div className={styles.actions}>
          <button type="button" onClick={download}>
            Export
          </button>
          <button type="button" onClick={() => fileRef.current?.click()}>
            Import
          </button>
          <button type="button" onClick={() => clearSandboxFigure(figureId)}>
            Remove all
          </button>
        </div>
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="application/json,.json"
        className={styles.fileInput}
        aria-label="Import trial export"
        onChange={(event) => {
          const [file] = event.target.files ?? [];
          event.target.value = "";
          if (file) importFile(file);
        }}
      />
      {importError ? (
        <p className={styles.importError} role="alert">
          {importError}
        </p>
      ) : null}
      <p className={styles.note}>
        Local trial only — these parts are not from the paper. Trials persist in this
        browser; export them to share.
      </p>
      <ul className={styles.items}>
        {mine.map((item) => {
          const warnings = sandboxWarnings(item, nets);
          return (
          <li key={item.key} className={styles.item}>
            <div className={styles.itemHead}>
              <span className={styles.itemLabel}>{item.label}</span>
              <button type="button" onClick={() => removeSandboxItem(item.key)}>
                Remove
              </button>
            </div>
            {warnings.length > 0 ? (
              <ul className={styles.warnings} aria-label={`${item.label} warnings`}>
                {warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
            {item.pinout.length === 0 ? (
              <p className={styles.note}>The catalog lists no pins: drawn unconnected.</p>
            ) : (
              <div className={styles.pins}>
                {sandboxPinMap(item.engineType, item.pinout).map(({ designator, symbolPin }) => (
                  <label key={designator} className={styles.pin}>
                    <span className={styles.pinName} title={symbolPin}>
                      {designator}
                      {designator !== symbolPin ? ` → ${symbolPin}` : ""}
                    </span>
                    <select
                      value={item.pinNets[designator] ?? ""}
                      onChange={(event) =>
                        setSandboxPinNet(
                          item.key,
                          designator,
                          event.target.value === "" ? null : event.target.value,
                        )
                      }
                      aria-label={`${item.label} pin ${designator} net`}
                    >
                      <option value="">Unconnected</option>
                      {nets.map((net) => (
                        <option key={net.id} value={net.id}>
                          {net.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            )}
          </li>
          );
        })}
      </ul>
    </section>
  );
}
