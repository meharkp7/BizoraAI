import { useState } from "react";
import { useCopilot } from "../../app/queries.ts";
import { NODE_KINDS } from "../../lib/constants.ts";
import { useLibrarySelection, useWorkspaceSelection } from "../../lib/store.ts";
import type {
  CopilotCard,
  CopilotProposal,
  CopilotResponse,
  GraphPatch,
  MethodologyGraph,
  NodeKind,
} from "../../lib/types.ts";
import { replaceNodePatch, updateConfigPatch } from "../workspace/patchBuilders.ts";
import styles from "./CopilotPanel.module.css";

interface Turn {
  id: number;
  message: string;
  response: CopilotResponse | null;
  error: string | null;
}

function isNodeKind(value: string): value is NodeKind {
  return (NODE_KINDS as readonly string[]).includes(value);
}

function ProposalActions({
  proposal,
  graph,
  disabled,
  dismissed,
  onApprove,
  onDismiss,
}: {
  proposal: CopilotProposal;
  graph: MethodologyGraph;
  disabled: boolean;
  dismissed: boolean;
  onApprove: (patches: GraphPatch[]) => void;
  onDismiss: () => void;
}) {
  if (dismissed) return <p className={styles.dismissed}>Proposal dismissed.</p>;
  const node = graph.nodes.find((candidate) => candidate.id === proposal.node_id);
  if (!node) return <p className={styles.dismissed}>The proposed node is no longer here.</p>;
  return (
    <div className={styles.proposalActions}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => {
          if (proposal.component_id) {
            onApprove([
              replaceNodePatch(graph, node, {
                kind: isNodeKind(proposal.kind) ? proposal.kind : node.kind,
                label: proposal.label,
                description: proposal.description,
                config: proposal.config,
              }),
            ]);
          } else {
            onApprove([updateConfigPatch(graph, node, proposal.config)]);
          }
          onDismiss();
        }}
      >
        Approve and apply
      </button>
      <button type="button" className={styles.secondary} onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}

function CardView({
  card,
  graph,
  disabled,
  proposal,
  dismissed,
  onApprove,
  onDismissProposal,
}: {
  card: CopilotCard;
  graph: MethodologyGraph;
  disabled: boolean;
  proposal: CopilotProposal | null;
  dismissed: boolean;
  onApprove: (patches: GraphPatch[]) => void;
  onDismissProposal: () => void;
}) {
  const { openComponent } = useLibrarySelection();
  return (
    <div className={styles.card}>
      <div className={styles.cardTitle}>{card.title}</div>
      <p className={styles.cardBody}>{card.body}</p>
      {card.component_ids.length > 0 ? (
        <div className={styles.cardLinks}>
          {card.component_ids.map((componentId) => (
            <button key={componentId} type="button" onClick={() => openComponent(componentId)}>
              Open in library
            </button>
          ))}
        </div>
      ) : null}
      {card.kind === "proposal" && proposal ? (
        <ProposalActions
          proposal={proposal}
          graph={graph}
          disabled={disabled}
          dismissed={dismissed}
          onApprove={onApprove}
          onDismiss={onDismissProposal}
        />
      ) : null}
    </div>
  );
}

export function CopilotPanel({
  projectId,
  graph,
  disabled,
  onSubmit,
}: {
  projectId: string;
  graph: MethodologyGraph;
  disabled: boolean;
  onSubmit: (patches: GraphPatch[]) => void;
}) {
  const copilot = useCopilot(projectId, graph.graph_id, graph.version);
  const { selectedNodeIds } = useWorkspaceSelection();
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [dismissed, setDismissed] = useState<Set<number>>(new Set());
  const selectedNode = graph.nodes.find((node) => node.id === selectedNodeIds[0]) ?? null;

  function ask(message: string): void {
    const text = message.trim();
    if (text === "" || copilot.isPending) return;
    const id = Date.now() + Math.random();
    setTurns((current) => [...current, { id, message: text, response: null, error: null }]);
    setInput("");
    copilot.mutate(
      { message: text, selectedNodeId: selectedNode?.id ?? null },
      {
        onSuccess: (response) =>
          setTurns((current) =>
            current.map((turn) => (turn.id === id ? { ...turn, response } : turn)),
          ),
        onError: (error) =>
          setTurns((current) =>
            current.map((turn) =>
              turn.id === id
                ? {
                    ...turn,
                    error: error instanceof Error ? error.message : "The copilot failed.",
                  }
                : turn,
            ),
          ),
      },
    );
  }

  return (
    <section className={styles.panel} aria-label="Research copilot">
      <h2>Research copilot</h2>
      <p className={styles.context}>
        {selectedNode ? (
          <>
            Talking about <strong>{selectedNode.label}</strong>
          </>
        ) : (
          "Select a node to discuss replacements and configuration."
        )}
      </p>
      <div className={styles.turns} aria-live="polite">
        {turns.length === 0 ? (
          <p className={styles.hint}>
            Ask to find, compare, or replace components — for example, “compare NF4 vs FP16”.
            Proposals wait for your approval.
          </p>
        ) : null}
        {turns.map((turn) => (
          <div key={turn.id} className={styles.turn}>
            <p className={styles.user}>{turn.message}</p>
            {turn.response ? (
              <>
                <p className={styles.reply}>{turn.response.reply}</p>
                {turn.response.cards.map((card, index) => (
                  <CardView
                    key={`${card.kind}-${index}`}
                    card={card}
                    graph={graph}
                    disabled={disabled}
                    proposal={turn.response?.proposal ?? null}
                    dismissed={dismissed.has(turn.id)}
                    onApprove={onSubmit}
                    onDismissProposal={() =>
                      setDismissed((current) => new Set(current).add(turn.id))
                    }
                  />
                ))}
              </>
            ) : turn.error ? (
              <p className={styles.error} role="alert">
                {turn.error}
              </p>
            ) : (
              <p className={styles.reply}>Thinking…</p>
            )}
          </div>
        ))}
      </div>
      <form
        className={styles.form}
        aria-label="Ask the copilot"
        onSubmit={(event) => {
          event.preventDefault();
          ask(input);
        }}
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Find, compare, or replace a component…"
          autoComplete="off"
          spellCheck={false}
          aria-label="Copilot message"
        />
        <button type="submit" disabled={copilot.isPending || input.trim() === ""}>
          {copilot.isPending ? "…" : "Ask"}
        </button>
      </form>
    </section>
  );
}
