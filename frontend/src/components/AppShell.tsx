import { useQueryClient } from "@tanstack/react-query";
import { Link, NavLink, Outlet, useNavigate, useParams } from "react-router";
import { accountKeys, useMe } from "../app/queries.ts";
import { SiteAgent } from "../features/copilot/SiteAgent.tsx";
import { useSession, useTheme } from "../lib/store.ts";
import styles from "./AppShell.module.css";

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const next = theme === "light" ? "dark" : "light";
  return (
    <button
      type="button"
      className={styles.themeToggle}
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} theme`}
    >
      {theme === "light" ? "Dark" : "Light"}
    </button>
  );
}

function AuthArea() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { token, clearToken } = useSession();
  const me = useMe(token !== null);
  if (!token) {
    return (
      <div className={styles.authArea}>
        <Link to="/login" className={styles.authLink}>
          Log in
        </Link>
      </div>
    );
  }
  function logout(): void {
    clearToken();
    void queryClient.removeQueries({ queryKey: accountKeys.me() });
    void queryClient.removeQueries({ queryKey: accountKeys.papers() });
    void navigate("/");
  }
  return (
    <div className={styles.authArea}>
      <Link to="/profile" className={styles.authLink}>
        {me.data?.name ?? "Profile"}
      </Link>
      <button type="button" className={styles.authButton} onClick={logout}>
        Log out
      </button>
    </div>
  );
}

function WorkspaceNav() {
  const { projectId, graphId } = useParams();
  if (!projectId || !graphId) return null;
  const base = `/g/${projectId}/${graphId}`;
  return (
    <nav className={styles.subnav} aria-label="Workspace">
      <Link to="/papers" className={styles.uploadAnother}>
        Upload another
      </Link>
      <NavLink
        to={base}
        end
        className={({ isActive }) => (isActive ? styles.active : undefined)}
      >
        Graph
      </NavLink>
      <NavLink
        to={`${base}/runs`}
        className={({ isActive }) => (isActive ? styles.active : undefined)}
      >
        Runs
      </NavLink>
      <NavLink
        to={`${base}/compare`}
        className={({ isActive }) => (isActive ? styles.active : undefined)}
      >
        Compare
      </NavLink>
      <NavLink
        to={`${base}/tables`}
        className={({ isActive }) => (isActive ? styles.active : undefined)}
      >
        Tables
      </NavLink>
      <NavLink
        to={`${base}/notebook`}
        className={({ isActive }) => (isActive ? styles.active : undefined)}
      >
        Notebook
      </NavLink>
    </nav>
  );
}

function BrandMark() {
  return (
    <svg
      className={styles.mark}
      aria-hidden="true"
      viewBox="0 0 24 24"
      focusable="false"
    >
      <rect x="0.5" y="0.5" width="23" height="23" rx="5" fill="#8a4d26" />
      <g stroke="#fffdf6" strokeWidth="1.6" fill="none">
        <path d="M6 16.5 10.5 12 6 7.5" />
        <path d="M10.5 12H18" />
      </g>
      <g fill="#fffdf6">
        <circle cx="6" cy="16.5" r="2" />
        <circle cx="6" cy="7.5" r="2" />
        <circle cx="18" cy="12" r="2" />
      </g>
    </svg>
  );
}

export function AppShell() {
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <Link to="/" className={styles.brand}>
          <BrandMark />
          <span className={styles.wordmark}>
            Bizora
            <span className={styles.tagline}>papers, testable</span>
          </span>
        </Link>
        <nav className={styles.mainnav} aria-label="Primary">
          <NavLink
            to="/papers"
            className={({ isActive }) => (isActive ? styles.active : undefined)}
          >
            Papers
          </NavLink>
          <NavLink
            to="/cross-paper"
            className={({ isActive }) => (isActive ? styles.active : undefined)}
          >
            Cross-paper
          </NavLink>
        </nav>
        <WorkspaceNav />
        <AuthArea />
        <ThemeToggle />
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <p className={styles.footerBrand}>
            <BrandMark />
            Bizora — evidence-grounded methodology, made testable.
          </p>
          <nav className={styles.footerNav} aria-label="Footer">
            <Link to="/papers">Papers</Link>
            <Link to="/cross-paper">Cross-paper</Link>
            <Link to="/quality">Eval quality</Link>
          </nav>
        </div>
      </footer>
      <SiteAgent />
    </div>
  );
}
