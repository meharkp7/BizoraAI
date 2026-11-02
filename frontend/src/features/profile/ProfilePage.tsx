import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { accountKeys, useMe, useMyPapers, useUsageSummary } from "../../app/queries.ts";
import { useSession } from "../../lib/store.ts";
import styles from "./ProfilePage.module.css";

function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`;
}

function UsageSection() {
  const usage = useUsageSummary(7);
  const today = usage.data?.days.at(-1) ?? null;
  return (
    <section className={styles.card} aria-label="Usage and spend">
      <h2>Usage &amp; spend</h2>
      {usage.isPending ? (
        <p role="status">Loading spend…</p>
      ) : usage.isError || !usage.data ? (
        <p>Spend is unavailable right now.</p>
      ) : (
        <>
          <p className={styles.hint}>
            All costs are estimates from configured per-token rates; unmetered
            calls ran but reported no usage.
          </p>
          <dl className={styles.facts}>
            <div>
              <dt>Today (estimated)</dt>
              <dd>
                {today ? formatUsd(today.cost_usd_estimated) : "—"}
                {today && today.unmetered_calls > 0
                  ? ` · ${today.unmetered_calls} unmetered`
                  : ""}
              </dd>
            </div>
            <div>
              <dt>Last 7 days (estimated)</dt>
              <dd>
                {formatUsd(usage.data.totals.cost_usd_estimated)}
                {usage.data.totals.unmetered_calls > 0
                  ? ` · ${usage.data.totals.unmetered_calls} unmetered`
                  : ""}
              </dd>
            </div>
            <div>
              <dt>Daily cap</dt>
              <dd>
                {usage.data.caps.daily_cap_usd > 0
                  ? formatUsd(usage.data.caps.daily_cap_usd)
                  : "Off"}
              </dd>
            </div>
            <div>
              <dt>Run cap</dt>
              <dd>
                {usage.data.caps.run_cap_usd > 0
                  ? formatUsd(usage.data.caps.run_cap_usd)
                  : "Off"}
              </dd>
            </div>
            <div>
              <dt>Max runs / day</dt>
              <dd>
                {usage.data.caps.max_runs_per_day > 0
                  ? usage.data.caps.max_runs_per_day
                  : "Off"}
              </dd>
            </div>
          </dl>
        </>
      )}
    </section>
  );
}

export function ProfilePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { token, clearToken } = useSession();
  const me = useMe(token !== null);
  const papers = useMyPapers(token !== null);

  function logout(): void {
    clearToken();
    void queryClient.removeQueries({ queryKey: accountKeys.me() });
    void queryClient.removeQueries({ queryKey: accountKeys.papers() });
    void navigate("/");
  }

  if (!token) {
    return (
      <div className={styles.page}>
        <section className={styles.card} aria-label="My profile">
          <h1>My profile</h1>
          <p>
            Log in to see your papers and notes. <Link to="/login">Log in</Link>
          </p>
        </section>
      </div>
    );
  }

  if (me.isPending) {
    return (
      <div className={styles.page}>
        <section className={styles.card} aria-label="My profile">
          <h1>My profile</h1>
          <p role="status">Loading your account…</p>
        </section>
      </div>
    );
  }

  if (me.isError || !me.data) {
    return (
      <div className={styles.page}>
        <section className={styles.card} aria-label="My profile">
          <h1>My profile</h1>
          <p role="alert">
            This session is no longer valid.{" "}
            <button type="button" className={styles.linkButton} onClick={logout}>
              Log in again
            </button>
          </p>
        </section>
      </div>
    );
  }

  const user = me.data;
  const library = papers.data ?? [];
  return (
    <div className={styles.page}>
      <section className={styles.card} aria-label="My profile">
        <h1>My profile</h1>
        <dl className={styles.facts}>
          <div>
            <dt>Name</dt>
            <dd>{user.name}</dd>
          </div>
          <div>
            <dt>Email</dt>
            <dd>{user.email}</dd>
          </div>
          <div>
            <dt>Papers</dt>
            <dd>{papers.isPending ? "…" : library.length}</dd>
          </div>
        </dl>
        <button type="button" onClick={logout}>
          Log out
        </button>
      </section>
      <section className={styles.card} aria-label="My papers">
        <h2>My papers</h2>
        {papers.isPending ? (
          <p role="status">Loading your papers…</p>
        ) : library.length === 0 ? (
          <p>
            Nothing here yet — <Link to="/">upload a paper</Link> and it lands here
            automatically.
          </p>
        ) : (
          <ul className={styles.papers}>
            {library.map((paper) => (
              <li key={`${paper.project_id}/${paper.graph_id}`}>
                <Link
                  to={`/g/${encodeURIComponent(paper.project_id)}/${encodeURIComponent(paper.graph_id)}`}
                >
                  {paper.title}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      <UsageSection />
    </div>
  );
}
