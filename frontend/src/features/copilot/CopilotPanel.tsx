import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  copilotKeys,
  useCopilotThread,
  useCopilotThreads,
  useCreateCopilotThread,
} from "../../app/queries.ts";
import { useCopilotStream } from "./useCopilotStream.ts";
import type { CanvasView } from "../../app/routeElements.tsx";
import { NODE_KINDS } from "../../lib/constants.ts";
import { useLibrarySelection, useWorkspaceSelection } from "../../lib/store.ts";
import type {
  CopilotCard,
  CopilotDiagramElement,
  CopilotDiagramRef,
  CopilotProposal,
  GraphPatch,
  MethodologyGraph,
  NodeKind,
} from "../../lib/types.ts";
import { turnsFromThread, type Turn } from "./copilotThreads.ts";
import type { DiagramSelection } from "../diagrams/selection.ts";
import { diagramContextFor, tabName } from "./copilotContext.ts";
import { replaceNodePatch, updateConfigPatch } from "../workspace/patchBuilders.ts";
import styles from "./CopilotPanel.module.css";
import { EvidenceCard } from "./EvidenceCard.tsx";

function isNodeKind(value: string): value is NodeKind {
  return (NODE_KINDS as readonly string[]).includes(value);
}

/** Follow-up chips derived from what the last answer actually contained. */
function followUpsFor(turn: Turn): string[] {
  if (!turn.response || turn.error) return [];
  const chips: string[] = [];
  if (turn.response.proposal) chips.push("Why this replacement?");
  if (turn.response.cards.some((card) => card.kind === "evidence")) {
    chips.push("Show me the paper quote");
  } else {
    chips.push("What does the paper say here?");
  }
  if (turn.response.cards.some((card) => card.component_ids.length > 0)) {
    chips.push("Compare the top two options");
  } else {
    chips.push("What are my options?");
  }
  return chips.slice(0, 3);
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
    <>
    <p className={styles.gateNote}>Nothing is applied until you approve.</p>
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
    </>
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
  onSelectDiagram,
}: {
  card: CopilotCard;
  graph: MethodologyGraph;
  disabled: boolean;
  proposal: CopilotProposal | null;
  dismissed: boolean;
  onApprove: (patches: GraphPatch[]) => void;
  onDismissProposal: () => void;
  onSelectDiagram: ((ref: CopilotDiagramRef) => void) | null;
}) {
  const { openComponent } = useLibrarySelection();
  if (card.kind === "evidence" || card.kind === "info") {
    return <EvidenceCard card={card} />;
  }
  if (card.kind === "diagram") {
    return (
      <div className={styles.card}>
        <div className={styles.cardTitle}>{card.title}</div>
        <p className={styles.cardBody}>{card.body}</p>
        {card.diagram_ref && onSelectDiagram ? (
          <div className={styles.cardLinks}>
            <button
              type="button"
              onClick={() => {
                if (card.diagram_ref) onSelectDiagram(card.diagram_ref);
              }}
            >
              Show in diagram
            </button>
          </div>
        ) : null}
      </div>
    );
  }
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
  view,
  selection,
  diagramElements = [],
  onSubmit,
  onSelectDiagram = null,
}: {
  projectId: string;
  graph: MethodologyGraph;
  disabled: boolean;
  view: CanvasView;
  selection: DiagramSelection | null;
  diagramElements?: CopilotDiagramElement[];
  onSubmit: (patches: GraphPatch[]) => void;
  onSelectDiagram?: ((ref: CopilotDiagramRef) => void) | null;
}) {
  const copilot = useCopilotStream(projectId, graph.graph_id, graph.version);
  const queryClient = useQueryClient();
  const threadsQuery = useCopilotThreads(projectId, graph.graph_id);
  const createThread = useCreateCopilotThread(projectId, graph.graph_id);
  const [threadId, setThreadId] = useState<string | null>(null);
  const { selectedNodeIds } = useWorkspaceSelection();
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [dismissed, setDismissed] = useState<Set<number>>(new Set());
  const selectedNode = graph.nodes.find((node) => node.id === selectedNodeIds[0]) ?? null;
  const diagramContext = diagramContextFor(view, selection, selectedNode);
  const turnIdRef = useRef(0);
  const touchedRef = useRef(false);
  const threads = threadsQuery.data ?? [];
  const threadQuery = useCopilotThread(projectId, graph.graph_id, threadId);
  const loadingThread = threadId !== null && threadQuery.isLoading;

  // Resume the most recent conversation until the user picks or starts one.
  useEffect(() => {
    if (touchedRef.current || threadId !== null || turns.length > 0) return;
    const listed = threadsQuery.data ?? [];
    if (listed.length === 0) return;
    setThreadId(listed[0].thread_id);
  }, [threadsQuery.data, threadId, turns.length]);

  // Hydrate the panel from the active thread once its turns arrive.
  // Only an empty panel hydrates: a thread query resolving late must never
  // overwrite turns the user already asked, streamed, or just completed.
  useEffect(() => {
    const thread = threadQuery.data;
    if (threadId === null || !thread || thread.thread_id !== threadId) return;
    if (turns.length > 0) return;
    const hydrated = turnsFromThread(thread);
    turnIdRef.current = hydrated.length;
    setDismissed(new Set());
    setTurns(hydrated);
  }, [threadId, threadQuery.data, turns.length]);

  function refreshThreads(): void {
    void queryClient.invalidateQueries({
      queryKey: copilotKeys.threads(projectId, graph.graph_id),
    });
  }

  function startNewThread(): void {
    if (copilot.isPending || createThread.isPending) return;
    touchedRef.current = true;
    turnIdRef.current = 0;
    setDismissed(new Set());
    setTurns([]);
    setThreadId(null);
  }

  function switchThread(nextId: string): void {
    if (copilot.isPending || nextId === (threadId ?? "")) return;
    touchedRef.current = true;
    turnIdRef.current = 0;
    setDismissed(new Set());
    setTurns([]);
    setThreadId(nextId === "" ? null : nextId);
  }

  async function ask(message: string): Promise<void> {
    const text = message.trim();
    if (text === "" || copilot.isPending || createThread.isPending || loadingThread) {
      return;
    }
    touchedRef.current = true;
    let activeId = threadId;
    if (activeId === null) {
      try {
        const created = await createThread.mutateAsync(null);
        activeId = created.thread_id;
        setThreadId(activeId);
      } catch (error) {
        turnIdRef.current += 1;
        const id = turnIdRef.current;
        setTurns((current) => [
          ...current,
          {
            id,
            message: text,
            response: null,
            status: null,
            error:
              error instanceof Error ? error.message : "Could not start a conversation.",
          },
        ]);
        return;
      }
    }
    turnIdRef.current += 1;
    const id = turnIdRef.current;
    setTurns((current) => [
      ...current,
      { id, message: text, response: null, status: null, error: null },
    ]);
    setInput("");
    await copilot.ask(
      text,
      selectedNode?.id ?? null,
      diagramContext,
      {
        onStatus: (status) =>
          setTurns((current) =>
            current.map((turn) => (turn.id === id ? { ...turn, status } : turn)),
          ),
        onDone: (response) => {
          setTurns((current) =>
            current.map((turn) =>
              turn.id === id ? { ...turn, response, status: null } : turn,
            ),
          );
          refreshThreads();
        },
        onError: (error) => {
          setTurns((current) =>
            current.map((turn) =>
              turn.id === id
                ? {
                    ...turn,
                    status: null,
                    error: error instanceof Error ? error.message : "The copilot failed.",
                  }
                : turn,
            ),
          );
        },
      },
      activeId,
      diagramElements,
    );
  }

  return (
    <section className={styles.panel} aria-label="Research copilot">
      <h2>Research copilot</h2>
      <div className={styles.threadRow}>
        <select
          aria-label="Conversation"
          value={threadId ?? ""}
          disabled={copilot.isPending || createThread.isPending || threadsQuery.isLoading}
          onChange={(event) => switchThread(event.target.value)}
        >
          <option value="">New conversation</option>
          {threads.map((thread) => (
            <option key={thread.thread_id} value={thread.thread_id}>
              {thread.title}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={copilot.isPending || createThread.isPending}
          onClick={startNewThread}
        >
          New
        </button>
      </div>
      <p className={styles.context}>
        {selection ? (
          <>
            Talking about <strong>{selection.label}</strong> ({selection.elementId} ·{" "}
            {tabName(view)} tab)
          </>
        ) : selectedNode ? (
          <>
            Talking about <strong>{selectedNode.label}</strong> ({tabName(view)} tab)
          </>
        ) : (
          <>Viewing the {tabName(view)} tab — select a node to discuss it with the copilot.</>
        )}
      </p>
      <div className={styles.turns} aria-live="polite">
        {turns.length === 0 ? (
          <p className={styles.hint}>
            {loadingThread
              ? "Loading conversation…"
              : "Ask to find, compare, or replace components — for example, “compare NF4 vs FP16” — or ask what the paper or the runs say. Answers cite their evidence, and proposals wait for your approval."}
          </p>
        ) : null}
        {turns.map((turn, turnIndex) => {
          const chips =
            turnIndex === turns.length - 1 && !copilot.isPending ? followUpsFor(turn) : [];
          return (
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
                      onSelectDiagram={onSelectDiagram}
                    />
                  ))}
                </>
              ) : turn.error ? (
                <p className={styles.error} role="alert">
                  {turn.error}
                </p>
              ) : (
                <p className={styles.reply}>{turn.status ?? "Thinking…"}</p>
              )}
              {chips.length > 0 ? (
                <div className={styles.chips} aria-label="Follow-up questions">
                  {chips.map((chip) => (
                    <button
                      key={chip}
                      type="button"
                      className={styles.chip}
                      onClick={() => void ask(chip)}
                    >
                      {chip}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      <form
        className={styles.form}
        aria-label="Ask the copilot"
        onSubmit={(event) => {
          event.preventDefault();
          void ask(input);
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
        <button
          type="submit"
          disabled={
            copilot.isPending ||
            createThread.isPending ||
            loadingThread ||
            input.trim() === ""
          }
        >
          {copilot.isPending || createThread.isPending ? "…" : "Ask"}
        </button>
      </form>
    </section>
  );
}
