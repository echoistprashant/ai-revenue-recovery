"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { messageOf } from "@/lib/client";

interface LoginResult {
  username: string;
  role: string;
  tenantId: string;
  landing: string;
}

/**
 * The sign-in form.
 *
 * The password is posted to this app's own login route, which exchanges it for a token
 * and stores that token in an httpOnly cookie. Nothing here ever holds a credential
 * after the request completes, and the failure message is whatever the backend said —
 * which does not reveal whether the username exists.
 */
export function LoginForm({ expired }: { expired: boolean }) {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const text = await response.text();
      if (!response.ok) {
        let detail = response.statusText;
        try {
          const parsed = JSON.parse(text) as { detail?: string };
          detail = parsed.detail ?? detail;
        } catch {
          detail = text.slice(0, 200) || detail;
        }
        setError(detail);
        return;
      }
      const result = JSON.parse(text) as LoginResult;
      // Clear the password from React state before navigating.
      setPassword("");
      router.replace(result.landing);
      // The cookie was set by the route handler, so the server components on the next
      // page need a fresh render rather than a cached one.
      router.refresh();
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      {expired ? (
        <div className="callout warn">
          <p>Your session has ended. Sign in again to continue.</p>
        </div>
      ) : null}
      {error ? (
        <div className="callout bad" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      <div className="field">
        <label htmlFor="username">Username</label>
        <input
          id="username"
          name="username"
          type="text"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          required
          value={username}
          onChange={(event) => setUsername(event.target.value)}
        />
      </div>

      <div className="field">
        <label htmlFor="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </div>

      <button type="submit" className="full" disabled={busy || !username || !password}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
