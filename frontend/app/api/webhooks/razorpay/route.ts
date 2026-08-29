import { createHmac } from "node:crypto";

import { NextResponse } from "next/server";

import { BackendError, callBackend } from "@/lib/backend";
import { allowed } from "@/lib/access";
import { readSession } from "@/lib/session-server";

/**
 * Simulate a signed Razorpay webhook.
 *
 * The HMAC is computed here, on the server, over the exact bytes that are forwarded.
 * The secret is therefore never sent to the browser — which is the whole reason this
 * route exists rather than the page signing the payload itself.
 *
 * The backend's `/webhooks/razorpay` is authenticated by signature alone, because a
 * gateway cannot hold a password. That makes this route a way to reach it using the
 * server's secret, so it requires an `OPERATOR` session: without that check, any
 * visitor could inject payment events with the deployment's own credential.
 *
 * If no secret is configured the request is refused. Falling back to the publicly known
 * development value would mean anyone could forge a call to a production API.
 */
export async function POST(request: Request): Promise<NextResponse> {
  const session = await readSession();
  if (!session) {
    return NextResponse.json({ detail: "Not signed in." }, { status: 401 });
  }
  if (!allowed(session.role, "OPERATOR")) {
    return NextResponse.json(
      { detail: "Sending a simulated webhook requires the OPERATOR role or higher." },
      { status: 403 },
    );
  }

  const secret = process.env.RAZORPAY_WEBHOOK_SECRET ?? "";
  if (!secret) {
    return NextResponse.json(
      {
        detail:
          "RAZORPAY_WEBHOOK_SECRET is not set on the frontend server, so this request cannot be signed.",
      },
      { status: 503 },
    );
  }

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ detail: "Expected a JSON body." }, { status: 400 });
  }

  // Sign the same string that is sent. Re-serializing downstream would change the
  // bytes and the signature would no longer verify.
  const raw = JSON.stringify(payload);
  const signature = createHmac("sha256", secret).update(raw, "utf8").digest("hex");

  try {
    const processed = await callBackend<unknown>({
      method: "POST",
      path: "/webhooks/razorpay",
      rawBody: raw,
      headers: { "X-Razorpay-Signature": signature },
    });
    return NextResponse.json(processed ?? null, { status: 201 });
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json({ detail: error.detail }, { status: error.status });
    }
    throw error;
  }
}
