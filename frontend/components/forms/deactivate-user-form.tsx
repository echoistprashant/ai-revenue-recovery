"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { apiPost, messageOf, postLocal } from "@/lib/client";
import type { UserResponse } from "@/lib/types";

/**
 * Deactivate an account.
 *
 * Deactivation is the kill switch for a stateless token: the backend re-reads the account
 * row on every request, so a token issued before this call stops working on its next use
 * rather than at its expiry.
 *
 * Deactivating your own account signs you out here, because leaving a dead session on
 * screen would just produce a wall of 401s.
 */
export function DeactivateUserForm({
  candidates,
  currentUsername,
}: {
  candidates: string[];
  currentUsername: string;
}) {
  const router = useRouter();
  const [target, setTarget] = useState(candidates[0] ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!target) {
      return;
    }
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const disabled = await apiPost<UserResponse>(
        `/auth/users/${encodeURIComponent(target)}/deactivate`,
      );
      setDone(disabled.username);
      if (disabled.username === currentUsername) {
        await postLocal("/api/auth/logout").catch(() => undefined);
        window.location.href = "/login";
        return;
      }
      router.refresh();
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  }

  if (candidates.length === 0) {
    return <p className="empty-state">No active accounts to deactivate.</p>;
  }

  return (
    <form onSubmit={submit}>
      <div className="field">
        <label htmlFor="da-target">Account</label>
        <select id="da-target" value={target} onChange={(change) => setTarget(change.target.value)}>
          {candidates.map((name) => (
            <option key={name} value={name}>
              {name}
              {name === currentUsername ? " (you)" : ""}
            </option>
          ))}
        </select>
        {target === currentUsername ? (
          <span className="field-hint">
            This is your own account — deactivating it signs you out immediately.
          </span>
        ) : null}
      </div>

      <button type="submit" className="danger" disabled={busy}>
        {busy ? "Deactivating…" : "Deactivate"}
      </button>

      {error ? (
        <div className="callout bad section-gap" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      {done ? (
        <div className="callout good section-gap">
          <strong>
            <code>{done}</code> is now inactive
          </strong>
          <p className="inline-note">
            Any token already issued to that account stops working on its next request.
          </p>
        </div>
      ) : null}
    </form>
  );
}
