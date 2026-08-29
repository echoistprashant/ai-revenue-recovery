/**
 * Browser-side calls, which go to this app's proxy rather than to FastAPI.
 *
 * There is no token here to forget to attach: the proxy reads it from the httpOnly
 * cookie. A 401 means the session ended, and the only useful response is to land on
 * the login page — so that is handled once, here, rather than in every form.
 */

export class ClientError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ClientError";
  }
}

async function send<T>(method: "GET" | "POST", path: string, init: RequestInit): Promise<T> {
  return request<T>(method, `/api/backend${path.startsWith("/") ? path : `/${path}`}`, init);
}

async function request<T>(method: "GET" | "POST", url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, {
    method,
    ...init,
    headers: { Accept: "application/json", ...(init.headers ?? {}) },
  });

  const text = await response.text();
  if (response.status === 401 && typeof window !== "undefined") {
    window.location.href = "/login?expired=1";
    // The navigation is asynchronous, so the caller still needs an outcome; a thrown
    // error keeps it from rendering a success state during the redirect.
    throw new ClientError(401, "Your session has ended — signing in again.");
  }
  if (!response.ok) {
    throw new ClientError(response.status, detailFrom(text) ?? response.statusText);
  }
  if (!text) {
    return undefined as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ClientError(502, "The API returned a response this page could not read.");
  }
}

function detailFrom(text: string): string | null {
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
    return text.slice(0, 300);
  }
  return text.slice(0, 300);
}

export function apiGet<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  }
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return send<T>("GET", `${path}${suffix}`, {});
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return send<T>("POST", path, {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

/**
 * POST to one of this app's own route handlers rather than through the API proxy.
 *
 * Used by the webhook simulator, whose whole point is that the signing secret stays on
 * the server: the browser sends an unsigned payload to a local route and never sees the
 * key. Session handling and error shapes are shared with the proxy calls above.
 */
export function postLocal<T>(url: string, body?: unknown): Promise<T> {
  return request<T>("POST", url, {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

/** Turn an unknown thrown value into something safe to render. */
export function messageOf(error: unknown): string {
  if (error instanceof ClientError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}
