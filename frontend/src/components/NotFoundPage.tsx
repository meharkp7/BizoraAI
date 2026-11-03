import { Link } from "react-router";
import styles from "./NotFoundPage.module.css";

export function NotFoundPage() {
  return (
    <div className={`bz-enter ${styles.page}`}>
      <div className={styles.card}>
        <p className={styles.code} aria-hidden="true">
          404
        </p>
        <h1>Page not found</h1>
        <p>This corner of the studio doesn&rsquo;t exist — yet.</p>
        <p>
          <Link to="/" className="bz-btn bz-btn-primary">
            Back to home
          </Link>
        </p>
      </div>
    </div>
  );
}
