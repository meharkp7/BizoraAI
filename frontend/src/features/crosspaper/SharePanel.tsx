import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";
import {
  useAcceptInvite,
  useCreateInvite,
  useProjectInvites,
  useRevokeInvite,
} from "../../app/queries.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import { useSession } from "../../lib/store.ts";
import type { ProjectInviteRole } from "../../lib/types.ts";
import styles from "./CrossPaperPage.module.css";
import type { TrayEntry } from "./tray.ts";

function projectIdsOf(tray: TrayEntry[]): string[] {
  return Array.from(new Set(tray.map((entry) => entry.project_id))).sort();
}

function InviteList({ projectId }: { projectId: string }) {
  const { token } = useSession();
  const invites = useProjectInvites(projectId, token !== null);
  const create = useCreateInvite(projectId);
  const revoke = useRevokeInvite(projectId);
  const accept = useAcceptInvite(projectId);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<ProjectInviteRole>("viewer");
  const [createdToken, setCreatedToken] = useState<string | null>(null);
  const [createdEmail, setCreatedEmail] = useState("");
  const [createdId, setCreatedId] = useState("");
  const [acceptId, setAcceptId] = useState("");
  const [acceptToken, setAcceptToken] = useState("");

  function submit(event: FormEvent): void {
    event.preventDefault();
    const address = email.trim();
    if (!address || create.isPending) return;
    create.mutate(
      { email: address, role },
      {
        onSuccess: (response) => {
          setEmail("");
          setCreatedEmail(response.invite.email);
          setCreatedId(response.invite.invite_id);
          // Shown once: the token is never listed again.
          setCreatedToken(response.token);
        },
      },
    );
  }

  function submitAccept(event: FormEvent): void {
    event.preventDefault();
    if (!acceptId.trim() || !acceptToken.trim() || accept.isPending) return;
    accept.mutate(
      { inviteId: acceptId.trim(), token: acceptToken.trim() },
      {
        onSuccess: () => {
          setAcceptId("");
          setAcceptToken("");
        },
      },
    );
  }

  if (invites.isPending) return <LoadingState label="Loading invites…" />;
  if (invites.isError || !invites.data) {
    return (
      <ErrorState
        title="Could not load invites."
        detail={invites.error instanceof Error ? invites.error.message : undefined}
        onRetry={() => void invites.refetch()}
      />
    );
  }

  return (
    <div className={styles.arena}>
      <form className={styles.arenaForm} onSubmit={submit} aria-label="Invite a collaborator">
        <label>
          Email
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="teammate@example.com"
            maxLength={320}
            aria-label="Invitee email"
          />
        </label>
        <label>
          Role
          <select
            value={role}
            onChange={(event) => setRole(event.target.value as ProjectInviteRole)}
            aria-label="Invitee role"
          >
            <option value="viewer">viewer</option>
            <option value="editor">editor</option>
            <option value="owner">owner</option>
          </select>
        </label>
        <button type="submit" disabled={create.isPending || email.trim() === ""}>
          {create.isPending ? "…" : "Invite"}
        </button>
      </form>
      {create.isError && (
        <p role="alert">
          {create.error instanceof Error ? create.error.message : "Could not create the invite."}
        </p>
      )}
      {createdToken && (
        <p role="status">
          Invite for {createdEmail} (copy now — it is shown once): id <code>{createdId}</code>{" "}
          token <code>{createdToken}</code>
        </p>
      )}

      {invites.data.length === 0 ? (
        <EmptyState
          title="No invites yet."
          detail="Invite a teammate above; they accept with the one-time link."
        />
      ) : (
        <ul className={styles.plain}>
          {invites.data.map((entry) => (
            <li key={entry.invite_id} className={styles.memoryRow}>
              <span>{entry.email}</span>
              <span className={styles.meta}>
                {entry.role} · {entry.status}
              </span>
              {entry.status === "pending" && (
                <button
                  type="button"
                  disabled={revoke.isPending}
                  onClick={() => revoke.mutate(entry.invite_id)}
                  aria-label={`Revoke invite for ${entry.email}`}
                >
                  Revoke
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <form className={styles.arenaForm} onSubmit={submitAccept} aria-label="Accept an invite">
        <label>
          Invite ID
          <input
            value={acceptId}
            onChange={(event) => setAcceptId(event.target.value)}
            placeholder="invite id from the link"
            aria-label="Invite ID"
          />
        </label>
        <label>
          Token
          <input
            value={acceptToken}
            onChange={(event) => setAcceptToken(event.target.value)}
            placeholder="paste the one-time token"
            aria-label="Invite token"
          />
        </label>
        <button
          type="submit"
          disabled={accept.isPending || acceptId.trim() === "" || acceptToken.trim() === ""}
        >
          {accept.isPending ? "…" : "Accept"}
        </button>
      </form>
      {accept.isError && (
        <p role="alert">
          {accept.error instanceof Error ? accept.error.message : "Could not accept the invite."}
        </p>
      )}
      {accept.isSuccess && <p role="status">Welcome to {projectId}.</p>}
    </div>
  );
}

export function SharePanel({ tray }: { tray: TrayEntry[] }) {
  const { token } = useSession();
  const projects = projectIdsOf(tray);
  const [projectId, setProjectId] = useState<string>("");

  if (!token) {
    return (
      <section className={styles.arena} aria-label="Share project">
        <p className={styles.hint}>
          <Link to="/login">Log in</Link> to invite collaborators to a project.
        </p>
      </section>
    );
  }

  if (projects.length === 0) {
    return (
      <EmptyState
        title="Add a graph to the tray to share its project."
        detail="Invites belong to a project, so pick one from the tray first."
      />
    );
  }
  const active = projectId || projects[0]!;

  return (
    <div className={styles.arena}>
      <form className={styles.arenaForm} aria-label="Pick shared project">
        <label>
          Project
          <select value={active} onChange={(event) => setProjectId(event.target.value)}>
            {projects.map((project) => (
              <option key={project} value={project}>
                {project}
              </option>
            ))}
          </select>
        </label>
      </form>
      <InviteList key={active} projectId={active} />
    </div>
  );
}
