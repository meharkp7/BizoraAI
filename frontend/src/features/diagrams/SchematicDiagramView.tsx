import { useEffect, useMemo, useState } from "react";
import { dark, light } from "../../diagram-engine/index.js";
import { useSchematicSandbox, useTheme } from "../../lib/store.ts";
import type {
  CircuitIRJson,
  DiagramValidationReportJson,
} from "../../lib/types.ts";
import { circuitHasPaperLayout, renderCircuitDiagram } from "./adapters.ts";
import { CircuitPicker } from "./CircuitPicker.tsx";
import { DiagramFallback } from "./DiagramFallback.tsx";
import { SandboxPanel } from "./SandboxPanel.tsx";
import { applySandboxItems } from "./schematicSandbox.ts";
import styles from "./DiagramView.module.css";
import { ProvenanceLegend, ProvenanceTag } from "./ProvenanceTag.tsx";
import { countProvenance } from "./provenance.ts";
import type { DiagramSelection } from "./selection.ts";
import { SignalFlow } from "./SignalFlow.tsx";

/** Schematic tab: the paper's circuit figures, rendered by the engine
 *  from the diagrams endpoint. Clicking a component opens the Inspector. */
export function SchematicDiagramView({
  circuits,
  validation,
  projectId,
  graphId,
  nodeLabels,
  onSelect,
}: {
  circuits: CircuitIRJson[];
  validation: Record<string, DiagramValidationReportJson>;
  projectId: string;
  graphId: string;
  nodeLabels: Map<string, string>;
  onSelect: (selection: DiagramSelection) => void;
}) {
  const theme = useTheme((state) => state.theme);
  const [active, setActive] = useState(0);
  const sandboxItems = useSchematicSandbox((state) => state.items);
  const setActiveFigure = useSchematicSandbox((state) => state.setActiveFigure);
  const base = circuits[Math.min(active, circuits.length - 1)] ?? null;
  // Library trials merge over the endpoint circuit; the endpoint data
  // itself is never mutated.
  const circuit = useMemo(
    () => (base === null ? null : applySandboxItems(base, sandboxItems)),
    [base, sandboxItems],
  );
  useEffect(() => {
    if (base) setActiveFigure(base.source.figure_id);
  }, [base, setActiveFigure]);
  const rendered = useMemo(
    () =>
      circuit === null
        ? null
        : renderCircuitDiagram(circuit, {
            theme: theme === "dark" ? dark : light,
          }),
    [circuit, theme],
  );
  const netLabels = useMemo(
    () => new Map((circuit?.nets ?? []).map((net) => [net.id, net.label] as const)),
    [circuit],
  );

  if (circuit === null) {
    return (
      <DiagramFallback
        viewLabel="Schematic"
        reason="the paper's figures yielded nothing suitable."
        sourceFigureId={null}
        projectId={projectId}
        graphId={graphId}
        nodeLabels={nodeLabels}
      />
    );
  }

  const warnings = validation[`circuit:${circuit.source.figure_id}`]?.warnings ?? [];
  if (rendered === null || !rendered.ok) {
    return (
      <div className={styles.view}>
        <CircuitPicker circuits={circuits} active={active} onPick={setActive} />
        <DiagramFallback
          viewLabel="Schematic"
          reason={rendered === null ? "the diagram could not be rendered." : rendered.reason}
          sourceFigureId={circuit.source.figure_id}
          projectId={projectId}
          graphId={graphId}
          nodeLabels={nodeLabels}
          warnings={warnings}
        />
      </div>
    );
  }

  const counts = countProvenance(circuit.components);
  const paperLayout = circuitHasPaperLayout(circuit);
  return (
    <div className={styles.view}>
      <CircuitPicker circuits={circuits} active={active} onPick={setActive} />
      <div className={styles.head}>
        <h3>{circuit.title}</h3>
        <p className={styles.counts}>
          {counts.fromPaper} from paper · {counts.assumed} assumed
        </p>
        {paperLayout ? null : <ProvenanceTag value="illustrative" />}
      </div>
      <ProvenanceLegend />
      {paperLayout ? null : (
        <p className={styles.counts}>
          Illustrative layout: component positions were not stated, so the engine
          placed them automatically.
        </p>
      )}
      {warnings.length > 0 ? (
        <ul className={styles.warnings} aria-label="Extraction warnings">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
      <SandboxPanel figureId={circuit.source.figure_id} nets={circuit.nets} />
      <SignalFlow
        key={circuit.source.figure_id}
        circuit={circuit}
        svg={rendered.svg}
        netLabels={netLabels}
        onSelect={onSelect}
      />
      <p className={styles.counts}>
        Dashed components are <ProvenanceTag value="assumed" /> — click any component
        for its evidence, or play the walkthrough.
      </p>
    </div>
  );
}

