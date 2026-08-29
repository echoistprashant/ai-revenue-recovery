/**
 * Cookie I/O for the session. Server-only: importing this from a client component is
 * a build error, which is the point — the token must not be reachable from the browser
 * bundle.
 */

import "server-only";

import { cookies } from "next/headers";

import {
  SESSION_COOKIE,
  type Identity,
  type SessionData,
  decodeSession,
  encodeSession,
  identityOf,
  sessionCookieOptions,
} from "./session";

export async function readSession(): Promise<SessionData | null> {
  const store = await cookies();
  return decodeSession(store.get(SESSION_COOKIE)?.value);
}

/** The signed-in identity, or `null`. Used by layouts and pages to render the shell. */
export async function readIdentity(): Promise<Identity | null> {
  const session = await readSession();
  return session ? identityOf(session) : null;
}

export async function writeSession(data: SessionData): Promise<void> {
  const store = await cookies();
  // The cookie expires with the token rather than outliving it, so a stale cookie
  // does not produce a UI that looks signed in and then 401s on every panel.
  const maxAge = Math.floor((data.expiresAt - Date.now()) / 1000);
  store.set(SESSION_COOKIE, encodeSession(data), sessionCookieOptions(maxAge));
}

export async function clearSession(): Promise<void> {
  const store = await cookies();
  store.set(SESSION_COOKIE, "", sessionCookieOptions(0));
}
