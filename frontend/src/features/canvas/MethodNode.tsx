import { Handle, Position } from "@xyflow/react";
import type { Node, NodeProps } from "@xyflow/react";
import type { Provenance } from "../../lib/types.ts";
import styles from "./MethodNode.module.css";

export type NodeDiffStatus = "added" | "changed";

export interface MethodNodeData extends Record<string, unknown> {
  label: string;
  kind: string;
  provenance: Provenance;
  confidence: number | null;
  diffStatus: NodeDiffStatus | null;
}

export type MethodNodeType = Node<MethodNodeData, "method">;

const KIND_SHORT: Record<string, string> = {
  input: "in",
  preprocessing: "prep",
  model: "model",
  operation: "op",
  loss: "loss",
  optimizer: "opt",
  evaluation: "eval",
  output: "out",
  dataset: "data",
  component: "comp",
};

export function MethodNode({ data, selected }: NodeProps<MethodNodeType>) {
  const diffClass =
    data.diffStatus === "added"
      ? styles.added
      : data.diffStatus === "changed"
        ? styles.changed
        : "";
  return (
    <div
      className={`${styles.node} ${selected ? styles.selected : ""} ${diffClass}`}
      data-provenance={data.provenance}
    >
      <Handle type="target" position={Position.Top} className={styles.handle} />
      <div className={styles.head}>
        <span className={styles.kind}>{KIND_SHORT[data.kind] ?? data.kind}</span>
        <span className={styles.label}>{data.label}</span>
      </div>
      <div className={styles.meta}>
        <span
          className={`${styles.prov} ${styles[data.provenance]}`}
          title={`Provenance: ${data.provenance}`}
        >
          {data.provenance}
        </span>
        {data.confidence !== null ? (
          <span className={styles.conf}>{data.confidence.toFixed(2)}</span>
        ) : null}
        {data.diffStatus ? <span className={styles.diff}>{data.diffStatus}</span> : null}
      </div>
      <Handle type="source" position={Position.Bottom} className={styles.handle} />
    </div>
  );
}
