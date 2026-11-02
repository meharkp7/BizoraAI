import { useQueryClient } from "@tanstack/react-query";
import { Link, NavLink, Outlet, useNavigate, useParams } from "react-router";
import { accountKeys, useMe } from "../app/queries.ts";
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

export function AppShell() {
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <Link to="/" className={styles.brand}>
          <span className={styles.mark} aria-hidden="true">
            Bz
          </span>
          Bizora
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
    </div>
  );
}
