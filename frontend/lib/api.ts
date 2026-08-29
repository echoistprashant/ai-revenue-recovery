/**
 * Server-side data access for pages and layouts.
 *
 * A page calls these directly during rendering. They resolve the session from the
 * cookie, attach the token, and translate a dead session into a redirect to the login
 * page — so no individual page has to handle an expired token, which is the same
 * reasoning as `SessionAPIClient` in the Streamlit dashboard.
 */

import "server-only";

import { redirect } from "next/navigation";

import { BackendError, callBackend } from "./backend";
import { allowed, landingPathFor, type Role } from "./access";
import { readSession } from "./session-server";
import type { SessionData } from "./session";

export async function requireSession(): Promise<SessionData> {
  const session = await readSession();
  if (!session) {
    redirect("/login");
  }
  return session;
}

/**
 * Session plus a minimum role. A user who lacks the role is sent to their own landing
 * page rather than shown an error: the menu already hides the link, so arriving here
 * means a typed URL or a stale bookmark.
 *
 * This is not the security boundary. The backend refuses the underlying call with 403
 * whatever this function decides.
 */
export async function requireRole(minimum: Role): Promise<SessionData> {
  const session = await requireSession();
  if (!allowed(session.role, minimum)) {
    redirect(landingPathFor(session.role));
  }
  return session;
}

export async function apiGet<T>(
  path: string,
  searchParams?: Record<string, string | number | undefined>,
): Promise<T> {
  const session = await requireSession();
  try {
    return await callBackend<T>({
      method: "GET",
      path,
      token: session.token,
      ...(searchParams ? { searchParams } : {}),
    });
  } catch (error) {
    throw rethrowOrRedirect(error);
  }
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const session = await requireSession();
  try {
    return await callBackend<T>({
      method: "POST",
      path,
      token: session.token,
      ...(body === undefined ? {} : { body }),
    });
  } catch (error) {
    throw rethrowOrRedirect(error);
  }
}

/**
 * A 401 during page rendering means the session ended between the cookie being read
 * and the call being made. Clearing it happens on the login page, which is reachable
 * without one.
 */
function rethrowOrRedirect(error: unknown): unknown {
  if (error instanceof BackendError && error.isAuthFailure) {
    redirect("/login?expired=1");
  }
  return error;
}

export type Attempt<T> = { ok: true; data: T } | { ok: false; message: string };

/**
 * Run a fetch and capture a backend failure as a value.
 *
 * Panels use this so one unreachable endpoint degrades to an inline message instead of
 * replacing the whole page with an error boundary. A redirect must still escape, so
 * `BackendError` is the only thing caught — a `NEXT_REDIRECT` is not a `BackendError`
 * and passes straight through.
 */
export async function attempt<T>(work: () => Promise<T>): Promise<Attempt<T>> {
  try {
    return { ok: true, data: await work() };
  } catch (error) {
    if (error instanceof BackendError) {
      return { ok: false, message: error.detail };
    }
    throw error;
  }
}
