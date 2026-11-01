import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";
import {
  useCreateNote,
  useDeleteNote,
  usePaperNotes,
  useUpdateNote,
} from "../../app/queries.ts";
import { BizoraApiError } from "../../lib/api.ts";
import { useSession } from "../../lib/store.ts";
import type { PaperNote } from "../../lib/types.ts";
import styles from "./NotesPanel.module.css";

function NoteItem({ note, paperId }: { note: PaperNote; paperId: string }) {
  const update = useUpdateNote(paperId);
  const remove = useDeleteNote(paperId);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(note.body);

  function save(event: FormEvent): void {
    event.preventDefault();
    if (draft.trim() === "") return;
    update.mutate(
      { noteId: note.id, body: draft.trim() },
      { onSuccess: () => setEditing(false) },
    );
  }

  if (editing) {
    return (
      <li className={styles.note}>
        <form onSubmit={save} aria-label={`Edit note ${note.id}`}>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={3}
            aria-label="Note text"
          />
          <div className={styles.actions}>
            <button type="submit" disabled={update.isPending || draft.trim() === ""}>
              {update.isPending ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              className={styles.secondary}
              onClick={() => {
                setDraft(note.body);
                setEditing(false);
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li className={styles.note}>
      <p className={styles.body}>{note.body}</p>
      <div className={styles.actions}>
        <button type="button" className={styles.secondary} onClick={() => setEditing(true)}>
          Edit
        </button>
        <button
          type="button"
          className={styles.secondary}
          disabled={remove.isPending}
          onClick={() => remove.mutate(note.id)}
          aria-label={`Delete note ${note.id}`}
        >
          {remove.isPending ? "…" : "Delete"}
        </button>
      </div>
      {update.error || remove.error ? (
        <p className={styles.error} role="alert">
          That change did not save. Try again.
        </p>
      ) : null}
    </li>
  );
}

export function NotesPanel({ paperId }: { paperId: string | null }) {
  const { token } = useSession();
  const notes = usePaperNotes(paperId, token !== null);
  const create = useCreateNote(paperId ?? "");
  const [draft, setDraft] = useState("");

  if (paperId === null) return null;

  if (!token) {
    return (
      <section className={styles.panel} aria-label="My notes">
        <h2>My notes</h2>
        <p className={styles.hint}>
          <Link to="/login">Log in</Link> to keep notes on this paper.
        </p>
      </section>
    );
  }

  function add(event: FormEvent): void {
    event.preventDefault();
    if (draft.trim() === "") return;
    create.mutate(draft.trim(), {
      onSuccess: () => setDraft(""),
    });
  }

  return (
    <section className={styles.panel} aria-label="My notes">
      <h2>My notes</h2>
      {notes.isPending ? (
        <p className={styles.hint} role="status">
          Loading notes…
        </p>
      ) : notes.isError ? (
        <p className={styles.error} role="alert">
          {notes.error instanceof BizoraApiError
            ? notes.error.message
            : "Notes did not load."}
        </p>
      ) : notes.data.length === 0 ? (
        <p className={styles.hint}>No notes yet — jot down the first one below.</p>
      ) : (
        <ul className={styles.list}>
          {notes.data.map((note) => (
            <NoteItem key={note.id} note={note} paperId={paperId} />
          ))}
        </ul>
      )}
      <form onSubmit={add} aria-label="Add a note" className={styles.add}>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="A note on this paper…"
          rows={2}
          aria-label="New note"
        />
        <button type="submit" disabled={create.isPending || draft.trim() === ""}>
          {create.isPending ? "Adding…" : "Add note"}
        </button>
      </form>
      {create.error ? (
        <p className={styles.error} role="alert">
          That note did not save. Try again.
        </p>
      ) : null}
    </section>
  );
}
