import { Link, Navigate } from "react-router";
import { useSession } from "../../lib/store.ts";
import styles from "./HomePage.module.css";

export function HomePage() {
  const { token } = useSession();
  if (token) return <Navigate to="/papers" replace />;
  return (
    <div className={styles.page}>
      <section className={styles.card} aria-label="Welcome to Bizora">
        <h1>Bizora</h1>
        <p>Turn scientific papers into explorable methodology graphs.</p>
        <Link to="/login" className={styles.loginLink}>
          Log in
        </Link>
      </section>
    </div>
  );
}
