import { NextResponse } from "next/server";

import { clearSession } from "@/lib/session-server";

/**
 * Drop the session cookie.
 *
 * There is nothing to revoke on the backend — the access token is stateless and
 * short-lived — so signing out is exactly "forget the credential". The account's
 * `is_active` flag is the server-side kill switch, and an administrator sets it from
 * the user-administration page.
 */
export async function POST(): Promise<NextResponse> {
  await clearSession();
  return NextResponse.json({ signedOut: true });
}
