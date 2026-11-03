import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  copilotKeys,
  useCopilotThread,
  useCopilotThreads,
  useCreateCopilotThread,
} from "../../app/queries.ts";
import { useCopilotStream } from "./useCopilotStream.ts";
import { useVoiceAgent, type VoiceAgentState } from "./useVoiceAgent.ts";
import { useVoiceInput } from "./useVoiceInput.ts";
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

const VOICE_ERROR_REPLY = "Sorry, I could not reach the agent just now.";

const VOICE_STATUS: Record<VoiceAgentState, string> = {
  idle: "Voice chat is off.",
  listening: "Listening — just talk.",
  thinking: "Thinking…",
  speaking: "Speaking — talk any time to interrupt.",
};

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
  detached,
  dismissed,
  onApprove,
  onDismiss,
}: {
  proposal: CopilotProposal;
  graph: MethodologyGraph;
  disabled: boolean;
  detached: boolean;
  dismissed: boolean;
  onApprove: (patches: GraphPatch[]) => void;
  onDismiss: () => void;
}) {
  if (dismissed) return <p className={styles.dismissed}>Proposal dismissed.</p>;
  const node = graph.nodes.find((candidate) => candidate.id === proposal.node_id);
  if (!node) return <p className={styles.dismissed}>The proposed node is no longer here.</p>;
  if (detached) {
    return (
      <>
        <p className={styles.gateNote}>Open the workspace to apply this proposal.</p>
        <div className={styles.proposalActions}>
          <button type="button" className={styles.secondary} onClick={onDismiss}>
            Dismiss
          </button>
        </div>
      </>
    );
  }
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
  detached,
  proposal,
  dismissed,
  onApprove,
  onDismissProposal,
  onSelectDiagram,
}: {
  card: CopilotCard;
  graph: MethodologyGraph;
  disabled: boolean;
  detached: boolean;
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
          detached={detached}
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
  detached = false,
}: {
  projectId: string;
  graph: MethodologyGraph;
  disabled: boolean;
  view: CanvasView;
  selection: DiagramSelection | null;
  diagramElements?: CopilotDiagramElement[];
  onSubmit: (patches: GraphPatch[]) => void;
  onSelectDiagram?: ((ref: CopilotDiagramRef) => void) | null;
  /**
   * Site-wide mode: chatting about a graph from outside the workspace.
   * Workspace selection is ignored (it belongs to another page) and
   * proposals stay visible but apply from the workspace.
   */
  detached?: boolean;
}) {
  const copilot = useCopilotStream(projectId, graph.graph_id, graph.version);
  const queryClient = useQueryClient();
  const threadsQuery = useCopilotThreads(projectId, graph.graph_id);
  const createThread = useCreateCopilotThread(projectId, graph.graph_id);
  const [threadId, setThreadId] = useState<string | null>(null);
  const { selectedNodeIds } = useWorkspaceSelection();
  const [input, setInput] = useState("");
  const voice = useVoiceInput("en-IN", (transcript) =>
    setInput((current) => {
      const clean = transcript.trim();
      if (!clean) return current;
      return current.trim() === "" ? clean : `${current.trimEnd()} ${clean}`;
    }),
  );
  const [turns, setTurns] = useState<Turn[]>([]);
  const [dismissed, setDismissed] = useState<Set<number>>(new Set());
  const [voiceMode, setVoiceMode] = useState(false);
  const voiceModeRef = useRef(false);
  const voiceGenRef = useRef(0);
  const agent = useVoiceAgent("en-IN", {
    // askVoice is hoisted, so the live transcript reuses the same path
    // as typed follow-ups in voice mode. The agent refreshes its
    // callbacks every render, so this always reaches the latest agent.
    onUserTurn: (transcript) => askVoice(transcript),
    onInterrupted: () => {
      voiceGenRef.current += 1;
    },
  });
  const selectedNode =
    detached ? null : (graph.nodes.find((node) => node.id === selectedNodeIds[0]) ?? null);
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

  async function ask(
    message: string,
    voiceOptions?: { onVoiceAnswer: (reply: string | null) => void },
  ): Promise<void> {
    const voiceTurn = voiceOptions !== undefined;
    const text = message.trim();
    if (text === "" || copilot.isPending || createThread.isPending || loadingThread) {
      // null settles voice bookkeeping without speaking.
      voiceOptions?.onVoiceAnswer(null);
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
        voiceOptions?.onVoiceAnswer(VOICE_ERROR_REPLY);
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
          voiceOptions?.onVoiceAnswer(response.reply);
        },
        onError: (error) => {
          setTurns((current) =>
            current.map((turn) =>
              turn.id === id
                ? {
                    ...turn,
                    status: null,
                    error: error instanceof Error ? error.message : "The agent failed.",
                  }
                : turn,
            ),
          );
          voiceOptions?.onVoiceAnswer(VOICE_ERROR_REPLY);
        },
      },
      activeId,
      diagramElements,
      voiceTurn,
    );
  }

  /** One hands-free turn: ask with the spoken style and read the answer aloud. */
  function askVoice(message: string): void {
    const generation = voiceGenRef.current;
    agent.setThinking(true);
    void ask(message, {
      onVoiceAnswer: (reply) => {
        if (!voiceModeRef.current || generation !== voiceGenRef.current) return;
        agent.setThinking(false);
        if (reply) agent.speak(reply);
      },
    });
  }

  function toggleVoiceMode(): void {
    if (voiceMode) {
      voiceModeRef.current = false;
      voiceGenRef.current += 1;
      setVoiceMode(false);
      agent.stop();
      return;
    }
    voice.stop();
    voiceModeRef.current = true;
    setVoiceMode(true);
    agent.start();
  }

  return (
    <section className={styles.panel} aria-label="Bizora agent">
      <h2>Bizora agent</h2>
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
        {agent.supported ? (
          <button
            type="button"
            className={voiceMode ? styles.voiceActive : undefined}
            aria-pressed={voiceMode}
            onClick={toggleVoiceMode}
          >
            {voiceMode ? "End voice chat" : "Voice chat"}
          </button>
        ) : null}
      </div>
      {voiceMode ? (
        <p className={styles.voiceStatus} aria-live="polite">
          {VOICE_STATUS[agent.state]}
          {agent.interim ? ` “${agent.interim}”` : null}
          {agent.state === "speaking" ? (
            <button
              type="button"
              className={styles.interruptButton}
              onClick={() => agent.interrupt()}
            >
              Interrupt
            </button>
          ) : null}
        </p>
      ) : null}
      {voiceMode && agent.error ? (
        <p className={styles.error} role="alert">
          {agent.error}
        </p>
      ) : null}
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
        ) : detached ? (
          <>
            Chatting about <strong>{graph.title}</strong> — open the workspace to
            apply proposals.
          </>
        ) : (
          <>Viewing the {tabName(view)} tab — select a node to discuss it with the agent.</>
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
                      detached={detached}
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
                      onClick={() => {
                        if (voiceMode) askVoice(chip);
                        else void ask(chip);
                      }}
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
        aria-label="Ask the agent"
        onSubmit={(event) => {
          event.preventDefault();
          if (voiceMode) {
            const text = input;
            setInput("");
            askVoice(text);
            return;
          }
          voice.stop();
          void ask(input);
        }}
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Find, compare, or replace a component…"
          autoComplete="off"
          spellCheck={false}
          aria-label="Agent message"
        />
        {voice.supported && !voiceMode ? (
          <button
            type="button"
            className={styles.voiceButton}
            aria-label={voice.listening ? "Stop dictation" : "Dictate message"}
            aria-pressed={voice.listening}
            onClick={voice.toggle}
          >
            {voice.listening ? "Stop" : "Mic"}
          </button>
        ) : null}
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
      {voice.listening ? (
        <p className={styles.hint} aria-live="polite">
          Listening… {voice.interim}
        </p>
      ) : null}
      {voice.error && !voice.listening ? (
        <p className={styles.error} role="alert">
          {voice.error}
        </p>
      ) : null}
    </section>
  );
}
