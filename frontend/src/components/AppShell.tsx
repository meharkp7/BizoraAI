import { Link, NavLink, Outlet, useParams } from "react-router";
import { useTheme } from "../lib/store.ts";
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

function WorkspaceNav() {
  const { projectId, graphId } = useParams();
  if (!projectId || !graphId) return null;
  const base = `/g/${projectId}/${graphId}`;
  return (
    <nav className={styles.subnav} aria-label="Workspace">
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
        <WorkspaceNav />
        <ThemeToggle />
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}
