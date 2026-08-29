import { NextResponse, type NextRequest } from "next/server";

import { BackendError, callBackend } from "@/lib/backend";
import { isProxyable } from "@/lib/proxy-allowlist";
import { readSession } from "@/lib/session-server";

/**
 * The browser's only route to the API.
 *
 * The token comes from the httpOnly cookie, so a page's JavaScript can make a request
 * without ever holding a credential. This adds no authority: the backend re-reads the
 * account row and re-checks the role on every call, and its 403 stands. Requests are
 * restricted to the allowlist in `lib/proxy-allowlist.ts` so this cannot be used as a
 * general tunnel to routes the UI does not use — notably `/auth/token`, whose token must
 * stay server-side, and `/webhooks/razorpay`, whose HMAC secret must never reach a
 * browser.
 */
async function proxy(
  request: NextRequest,
  method: "GET" | "POST",
  segments: string[],
): Promise<NextResponse> {
  const session = await readSession();
  if (!session) {
    return NextResponse.json({ detail: "Not signed in." }, { status: 401 });
  }

  const path = `/${segments.map(encodeURIComponent).join("/")}`;
  if (!isProxyable(method, decodeURIComponent(path))) {
    return NextResponse.json(
      { detail: `This application does not proxy ${method} ${path}.` },
      { status: 403 },
    );
  }

  const searchParams: Record<string, string> = {};
  request.nextUrl.searchParams.forEach((value, key) => {
    searchParams[key] = value;
  });

  let body: unknown;
  if (method === "POST") {
    const text = await request.text();
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        return NextResponse.json({ detail: "Expected a JSON body." }, { status: 400 });
      }
    }
  }

  try {
    const data = await callBackend<unknown>({
      method,
      path,
      token: session.token,
      searchParams,
      // Preserved so the backend's per-client rate limit keys on the real caller
      // rather than on this app server. Only meaningful when a deployment proxy sets
      // the header; the API must strip a client-supplied one at the edge.
      headers: forwardedFor(request),
      ...(body === undefined ? {} : { body }),
    });
    return NextResponse.json(data ?? null);
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json({ detail: error.detail }, { status: error.status });
    }
    throw error;
  }
}

function forwardedFor(request: NextRequest): Record<string, string> {
  const forwarded = request.headers.get("x-forwarded-for");
  if (!forwarded) {
    return {};
  }
  const client = forwarded.split(",")[0]?.trim();
  return client ? { "X-Forwarded-For": client } : {};
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  return proxy(request, "GET", path);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  return proxy(request, "POST", path);
}
