import type { CopilotResponse, CopilotThread } from "../../lib/types.ts";

export interface Turn {
  id: number;
  message: string;
  response: CopilotResponse | null;
  status: string | null;
  error: string | null;
}

/** Pair one thread's stored turns back into panel turns, oldest first. */
export function turnsFromThread(thread: CopilotThread): Turn[] {
  const turns: Array<Omit<Turn, "id">> = [];
  let pending: Omit<Turn, "id"> | null = null;
  for (const stored of thread.turns) {
    if (stored.role === "user") {
      if (pending) turns.push(pending);
      pending = { message: stored.message, response: null, status: null, error: null };
    } else if (pending) {
      pending.response = stored.response;
      turns.push(pending);
      pending = null;
    }
  }
  if (pending) turns.push(pending);
  return turns.map((turn, index) => ({ ...turn, id: index + 1 }));
}
