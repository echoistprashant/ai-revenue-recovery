import { NextResponse } from "next/server";

import { BackendError, callBackend } from "@/lib/backend";
import { landingPathFor } from "@/lib/access";
import { writeSession } from "@/lib/session-server";
import type { Role } from "@/lib/access";

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  role: Role;
  tenant_id: string;
  username: string;
}

/**
 * Exchange credentials for a session cookie.
 *
 * The backend's token is written into an httpOnly cookie and is never included in the
 * response body, so the browser receives an identity it can render and no credential it
 * can leak. Failures are returned with the backend's own message, which does not say
 * whether the username exists.
 */
export async function POST(request: Request): Promise<NextResponse> {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ detail: "Expected a JSON body." }, { status: 400 });
  }

  const { username, password } = (payload ?? {}) as { username?: unknown; password?: unknown };
  if (typeof username !== "string" || typeof password !== "string" || !username || !password) {
    return NextResponse.json({ detail: "Username and password are required." }, { status: 400 });
  }

  try {
    const token = await callBackend<TokenResponse>({
      method: "POST",
      path: "/auth/token",
      body: { username, password },
      // The backend rate-limits login attempts per client address. Behind this proxy
      // every attempt would otherwise appear to come from the app server, collapsing
      // per-client budgets into one global bucket, so the original address is passed
      // through when the deployment's proxy has supplied it.
      headers: forwardedFor(request),
    });

    await writeSession({
      token: token.access_token,
      username: token.username,
      role: token.role,
      tenantId: token.tenant_id,
      expiresAt: Date.now() + token.expires_in_seconds * 1000,
    });

    return NextResponse.json({
      username: token.username,
      role: token.role,
      tenantId: token.tenant_id,
      expiresInSeconds: token.expires_in_seconds,
      landing: landingPathFor(token.role),
    });
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json({ detail: error.detail }, { status: error.status });
    }
    throw error;
  }
}

function forwardedFor(request: Request): Record<string, string> {
  const forwarded = request.headers.get("x-forwarded-for");
  if (!forwarded) {
    return {};
  }
  const client = forwarded.split(",")[0]?.trim();
  return client ? { "X-Forwarded-For": client } : {};
}
