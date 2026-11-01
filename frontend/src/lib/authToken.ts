/* Bearer [REDACTED] storage for JWT login. The API client reads this
on every request; the same token works from curl, so the web login
and terminal flows share one credential. */

const STORAGE_KEY = "bizora.auth.token";

export function getAuthToken(): string | null {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored && stored !== "" ? stored : null;
  } catch {
    return null;
  }
}

export function setAuthToken(token: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, token);
  } catch {
    // Private mode: the session just doesn't persist.
  }
}

export function clearAuthToken(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
}
