import { Sidebar } from "@/components/sidebar";
import { menuFor } from "@/lib/access";
import { requireSession } from "@/lib/api";
import { identityOf } from "@/lib/session";

/**
 * The gate for every module page.
 *
 * There is no Next.js middleware in this app on purpose. This layout runs for every
 * route beneath it, so the session rule lives in exactly one place instead of being
 * duplicated into a second runtime where the two copies could drift apart.
 */
export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();
  const identity = identityOf(session);

  return (
    <div className="shell">
      <Sidebar identity={identity} modules={menuFor(identity.role)} />
      <main className="main">{children}</main>
    </div>
  );
}
