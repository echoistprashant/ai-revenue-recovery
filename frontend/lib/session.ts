/**
 * Session encoding — deliberately free of any Next.js import.
 *
 * The access token lives in an httpOnly cookie set by this app's own route handlers.
 * Browser JavaScript never sees it, so an XSS in a dependency cannot read out a
 * credential that authorizes payment operations; the worst it can do is make requests
 * the user could already make, which same-site cookies and the CSRF check below limit
 * further.
 *
 * Cookie I/O lives in `session-server.ts`. Keeping the codec here means its
 * fail-closed behaviour can be tested without a request scope.
 */

import type { Role } from "./access";

export const SESSION_COOKIE = "rr_session";

export interface SessionData {
  /** The backend's bearer token. Never sent to the browser. */
  readonly token: string;
  readonly username: string;
  readonly role: Role;
  readonly tenantId: string;
  /** Epoch milliseconds at which the backend token expires. */
  readonly expiresAt: number;
}

/** Identity safe to render in the UI — everything except the token. */
export type Identity = Omit<SessionData, "token">;

const KNOWN_ROLES: readonly string[] = ["VIEWER", "OPERATOR", "ADMIN"];

export function encodeSession(data: SessionData): string {
  return Buffer.from(JSON.stringify(data), "utf8").toString("base64url");
}

/**
 * Decode a cookie value, returning `null` for anything that is not a complete,
 * unexpired session. A tampered or truncated cookie is treated as "not signed in"
 * rather than as a partially trusted identity.
 *
 * There is no signature here because there is nothing to forge: the only field the
 * backend trusts is the token, which is itself signed and re-checked on every request.
 * Editing `role` in this cookie changes which links the UI draws and nothing else —
 * the API answers 403 regardless.
 */
export function decodeSession(raw: string | undefined | null, now = Date.now()): SessionData | null {
  if (!raw) {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(Buffer.from(raw, "base64url").toString("utf8"));
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) {
    return null;
  }
  const candidate = parsed as Record<string, unknown>;
  const { token, username, role, tenantId, expiresAt } = candidate;
  if (typeof token !== "string" || token.length === 0) {
    return null;
  }
  if (typeof username !== "string" || username.length === 0) {
    return null;
  }
  if (typeof role !== "string" || !KNOWN_ROLES.includes(role)) {
    return null;
  }
  if (typeof tenantId !== "string" || tenantId.length === 0) {
    return null;
  }
  if (typeof expiresAt !== "number" || !Number.isFinite(expiresAt) || expiresAt <= now) {
    return null;
  }
  return { token, username, role: role as Role, tenantId, expiresAt };
}

export function identityOf(session: SessionData): Identity {
  const { token: _token, ...identity } = session;
  return identity;
}

/**
 * `Secure` is on unless explicitly disabled, because the default has to be the safe
 * one; local development over plain HTTP sets `FRONTEND_COOKIE_SECURE=false`.
 */
export function cookieSecure(env: NodeJS.ProcessEnv = process.env): boolean {
  const configured = env.FRONTEND_COOKIE_SECURE;
  if (configured !== undefined) {
    return configured.toLowerCase() !== "false";
  }
  return env.NODE_ENV === "production";
}

export interface CookieOptions {
  httpOnly: true;
  sameSite: "strict";
  secure: boolean;
  path: "/";
  maxAge: number;
}

/**
 * `SameSite=Strict` is the CSRF control for the cookie itself: a cross-site form post
 * or image tag carries no session at all, so no state-changing route can be reached
 * from another origin.
 */
export function sessionCookieOptions(maxAgeSeconds: number, env?: NodeJS.ProcessEnv): CookieOptions {
  return {
    httpOnly: true,
    sameSite: "strict",
    secure: cookieSecure(env),
    path: "/",
    maxAge: Math.max(0, Math.floor(maxAgeSeconds)),
  };
}
