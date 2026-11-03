import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { useLogin, useRegister } from "../../app/queries.ts";
import { BizoraApiError } from "../../lib/api.ts";
import { useSession } from "../../lib/store.ts";
import styles from "./LoginPage.module.css";

type Mode = "login" | "register";

export function LoginPage() {
  const navigate = useNavigate();
  const login = useLogin();
  const register = useRegister();
  const { setToken, clearToken } = useSession();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const busy = login.isPending || register.isPending;

  function switchMode(next: Mode): void {
    setMode(next);
    setError(null);
    login.reset();
    register.reset();
  }

  function submit(event: FormEvent): void {
    event.preventDefault();
    setError(null);
    const done = (token: string): void => {
      setToken(token);
      void navigate("/papers");
    };
    const failed = (cause: unknown): void => {
      clearToken();
      setError(
        cause instanceof BizoraApiError
          ? cause.message
          : "Login failed. Check the details and try again.",
      );
    };
    if (mode === "login") {
      login.mutate(
        { email: email.trim(), password },
        {
          onSuccess: (response) => done(response.token),
          onError: failed,
        },
      );
    } else {
      register.mutate(
        { email: email.trim(), password, name: name.trim() },
        {
          onSuccess: (response) => done(response.token),
          onError: failed,
        },
      );
    }
  }

  return (
    <div className={`bz-page bz-enter ${styles.page}`}>
      <section className={styles.card} aria-label="Log in to Bizora">
        <div className={styles.formSide}>
          <h1>{mode === "login" ? "Log in" : "Create an account"}</h1>
          <p className={styles.lede}>
            Your papers and notes follow your login: upload once, find everything
            later under My profile. The same account works from the terminal — the
            login returns a JWT Bearer [REDACTED] curl.
          </p>
          <div className={styles.modes} role="group" aria-label="Login or register">
            <button
              type="button"
              aria-pressed={mode === "login"}
              onClick={() => switchMode("login")}
            >
              Log in
            </button>
            <button
              type="button"
              aria-pressed={mode === "register"}
              onClick={() => switchMode("register")}
            >
              Create account
            </button>
          </div>
          <form className={styles.form} onSubmit={submit} aria-label="Login form">
            <label className={styles.field}>
              Email
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
              />
            </label>
            {mode === "register" ? (
              <label className={styles.field}>
                Name
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="What should we call you?"
                  autoComplete="nickname"
                />
              </label>
            ) : null}
            <label className={styles.field}>
              Password{mode === "register" ? " (8+ characters)" : ""}
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                required
              />
            </label>
            <button type="submit" disabled={busy || email.trim() === "" || password === ""}>
              {busy ? "…" : mode === "login" ? "Log in" : "Create account"}
            </button>
          </form>
          {error ? (
            <p className={styles.formError} role="alert">
              {error}
            </p>
          ) : null}
          <p className={styles.back}>
            <Link to="/">Back to the homepage</Link>
          </p>
        </div>
        <div className={styles.artSide} aria-hidden="true">
          <img
            className="bz-art"
            src="/images/login-layers.jpg"
            alt=""
            loading="lazy"
          />
          <p>Upload once, find everything later.</p>
        </div>
      </section>
    </div>
  );
}
