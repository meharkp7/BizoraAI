/* Shared client constants. */

/** Actor recorded on patches and layouts saved through the workspace UI. */
export const WORKSPACE_ACTOR = "workspace-ui";

/** Component kinds offered by the canvas toolbar and the replace form. */
export const NODE_KINDS = [
  "input",
  "preprocessing",
  "model",
  "operation",
  "loss",
  "optimizer",
  "evaluation",
  "output",
  "dataset",
  "component",
] as const;
