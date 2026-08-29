/**
 * The only place this app talks to FastAPI.
 *
 * Every call happens on the server with the bearer token read from the httpOnly
 * session cookie. The browser calls this app's route handlers instead, so the token
 * is never part of any response body, script bundle, or `document.cookie`.
 */

import "server-only";

export class BackendError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`Backend responded ${status}: ${detail}`);
    this.name = "BackendError";
  }

  /** A dead session: expired token, deactivated account, rotated signing key. */
  get isAuthFailure(): boolean {
    return this.status === 401;
  }
}

export function backendBaseUrl(): string {
  const configured = process.env.REVENUE_RECOVERY_API_URL ?? "http://127.0.0.1:8000";
  return configured.replace(/\/+$/, "");
}

const DEFAULT_TIMEOUT_MS = Number(process.env.BACKEND_TIMEOUT_MS ?? 15000);

export interface BackendRequest {
  method: "GET" | "POST";
  path: string;
  token?: string | undefined;
  /** JSON body for writes. */
  body?: unknown;
  /** Raw body, used only by the webhook signer, which must send exact bytes. */
  rawBody?: string;
  headers?: Record<string, string>;
  searchParams?: Record<string, string | number | undefined>;
}

/**
 * Send one request and turn any failure into a `BackendError`.
 *
 * The status code decides the outcome, not the transport exception type: 401 means
 * the session is gone, 403 is the backend's final word on a permission the caller
 * does not have, and neither is retried here. The UI must not paper over a 403 by
 * re-asking with different framing.
 */
export async function callBackend<T>(request: BackendRequest): Promise<T> {
  const url = new URL(`${backendBaseUrl()}/${request.path.replace(/^\/+/, "")}`);
  for (const [key, value] of Object.entries(request.searchParams ?? {})) {
    if (value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  const headers: Record<string, string> = { Accept: "application/json", ...request.headers };
  if (request.token) {
    headers.Authorization = `Bearer ${request.token}`;
  }
  let payload: string | undefined;
  if (request.rawBody !== undefined) {
    payload = request.rawBody;
    headers["Content-Type"] ??= "application/json";
  } else if (request.body !== undefined) {
    payload = JSON.stringify(request.body);
    headers["Content-Type"] = "application/json";
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: request.method,
      headers,
      ...(payload === undefined ? {} : { body: payload }),
      // Recovery numbers must be current; a cached metrics page would misreport.
      cache: "no-store",
      signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
    });
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new BackendError(
      503,
      `Could not reach the API at ${backendBaseUrl()} (${reason}). Ensure FastAPI is running.`,
    );
  }

  const text = await response.text();
  if (!response.ok) {
    throw new BackendError(response.status, extractDetail(text) ?? response.statusText);
  }
  if (text.length === 0) {
    return undefined as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new BackendError(502, `API returned a non-JSON response for ${request.path}`);
  }
}

function extractDetail(text: string): string | null {
  if (!text) {
    return null;
  }
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
    if (parsed.detail !== undefined) {
      return JSON.stringify(parsed.detail);
    }
  } catch {
    // Not JSON; fall through to the raw text, trimmed so a stack trace cannot fill
    // the page.
  }
  return text.slice(0, 500);
}
