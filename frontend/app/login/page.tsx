import { redirect } from "next/navigation";

import { LoginForm } from "@/components/forms/login-form";
import { landingPathFor } from "@/lib/access";
import { readSession } from "@/lib/session-server";

/**
 * The only page reachable without a session.
 *
 * An already-signed-in visitor is sent on to their landing module rather than shown a
 * second login form.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ expired?: string }>;
}) {
  const session = await readSession();
  if (session) {
    redirect(landingPathFor(session.role));
  }
  const { expired } = await searchParams;

  return (
    <main className="login-shell">
      <div className="login-card">
        <h1>AI Revenue Recovery</h1>
        <p className="lede">Payment Intelligence Control Centre</p>
        <LoginForm expired={expired === "1"} />
        <p className="login-footnote">
          Accounts are created from the command line — <code>python scripts/create_user.py</code>.
          There is no default password. Roles are ranked: <code>VIEWER</code> reads,{" "}
          <code>OPERATOR</code> also ingests events and resolves escalations, <code>ADMIN</code>{" "}
          also manages accounts. No role can override a guardrail.
        </p>
      </div>
    </main>
  );
}
