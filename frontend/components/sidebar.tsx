"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import type { ModuleDefinition } from "@/lib/access";
import type { Identity } from "@/lib/session";

/**
 * Navigation and the signed-in identity.
 *
 * The module list arrives already filtered by the server layout, so this component
 * never has to reason about roles — and a link the role cannot use is not in the DOM at
 * all. Hiding it is convenience: the API re-checks the role on every request.
 */
export function Sidebar({
  identity,
  modules,
}: {
  identity: Identity;
  modules: ModuleDefinition[];
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);

  async function signOut() {
    setSigningOut(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      // Navigate regardless: if the request failed, the cookie may still be set, and
      // the login page will bounce a live session back to the dashboard rather than
      // leaving the user on a half-signed-out screen.
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <aside className="sidebar">
      <div className="brand">
        AI Revenue Recovery
        <small>Control Centre</small>
      </div>

      <div className="identity">
        <dl>
          <dt>User</dt>
          <dd>{identity.username}</dd>
          <dt>Role</dt>
          <dd>{identity.role}</dd>
          <dt>Tenant</dt>
          <dd>{identity.tenantId}</dd>
        </dl>
        <button type="button" className="secondary full" onClick={signOut} disabled={signingOut}>
          {signingOut ? "Signing out…" : "Sign out"}
        </button>
      </div>

      <nav className="nav" aria-label="Control centre modules">
        {modules.map((module) => {
          const active = pathname === module.href || pathname.startsWith(`${module.href}/`);
          return (
            <Link
              key={module.href}
              href={module.href}
              className="nav-link"
              aria-current={active ? "page" : undefined}
            >
              <span aria-hidden="true">{module.icon}</span>
              <span>{module.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <span>
          Figures from synthetic data are simulated and are not commercial results.
        </span>
        <span>Session ends {new Date(identity.expiresAt).toISOString().slice(11, 16)} UTC.</span>
      </div>
    </aside>
  );
}
