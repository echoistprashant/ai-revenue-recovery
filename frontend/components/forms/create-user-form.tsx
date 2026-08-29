"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { apiPost, messageOf } from "@/lib/client";
import type { Role, UserResponse } from "@/lib/types";

const ROLES: readonly { value: Role; caption: string }[] = [
  { value: "VIEWER", caption: "Reads dashboards, cases, and audit trails." },
  { value: "OPERATOR", caption: "Also ingests events, resolves escalations, and sends copy." },
  { value: "ADMIN", caption: "Also manages accounts. Still cannot override a guardrail." },
];

/**
 * Create an account.
 *
 * The password is sent once and never comes back: the API stores a bcrypt hash and its
 * responses carry no credential. This form clears the field as soon as the request
 * succeeds so it is not left sitting in the page's state.
 */
export function CreateUserForm({ defaultTenant }: { defaultTenant: string }) {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("VIEWER");
  const [tenant, setTenant] = useState(defaultTenant);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<UserResponse | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setCreated(null);
    try {
      const result = await apiPost<UserResponse>("/auth/users", {
        username,
        password,
        role,
        tenant_id: tenant || null,
      });
      setCreated(result);
      setUsername("");
      setPassword("");
      router.refresh();
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <div className="form-row">
        <div className="field">
          <label htmlFor="nu-username">Username</label>
          <input
            id="nu-username"
            value={username}
            minLength={3}
            autoComplete="off"
            onChange={(change) => setUsername(change.target.value)}
            required
          />
          <span className="field-hint">At least 3 characters.</span>
        </div>
        <div className="field">
          <label htmlFor="nu-role">Role</label>
          <select id="nu-role" value={role} onChange={(change) => setRole(change.target.value as Role)}>
            {ROLES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.value}
              </option>
            ))}
          </select>
          <span className="field-hint">{ROLES.find((option) => option.value === role)?.caption}</span>
        </div>
        <div className="field">
          <label htmlFor="nu-tenant">Tenant</label>
          <input id="nu-tenant" value={tenant} onChange={(change) => setTenant(change.target.value)} />
          <span className="field-hint">Accounts and their payment data are isolated per tenant.</span>
        </div>
      </div>

      <div className="field">
        <label htmlFor="nu-password">Password</label>
        <input
          id="nu-password"
          type="password"
          value={password}
          minLength={12}
          autoComplete="new-password"
          onChange={(change) => setPassword(change.target.value)}
          required
        />
        <span className="field-hint">
          At least 12 characters. Stored only as a bcrypt hash and never echoed back — if it is
          lost, the account needs a new one rather than a recovery.
        </span>
      </div>
      <button type="submit" disabled={busy}>
        {busy ? "Creating…" : "Create account"}
      </button>

      {error ? (
        <div className="callout bad section-gap" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      {created ? (
        <div className="callout good section-gap">
          <strong>
            Created <code>{created.username}</code>
          </strong>
          <p className="inline-note">
            Role <code>{created.role}</code> · tenant <code>{created.tenant_id}</code> · user id{" "}
            <code>{created.user_id}</code>. Give them the password over a channel you trust; it
            cannot be read back from here.
          </p>
        </div>
      ) : null}
    </form>
  );
}
