import { CreateUserForm } from "@/components/forms/create-user-form";
import { DeactivateUserForm } from "@/components/forms/deactivate-user-form";
import { Badge, Callout, Card, ErrorNote, PageHeader, TableWrap } from "@/components/ui";
import { apiGet, attempt, requireRole } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import type { UserResponse } from "@/lib/types";

export const metadata = { title: "User Administration — AI Revenue Recovery" };

/**
 * Accounts in this tenant.
 *
 * `ADMIN` is the ceiling of the role ranking, and it stops at account management. It does
 * not come with a path around the guardrails — that is the point of the callout below,
 * and of the fact that no endpoint accepts an override flag.
 */
export default async function UsersPage() {
  const session = await requireRole("ADMIN");
  const accounts = await attempt(() => apiGet<UserResponse[]>("/auth/users"));
  const activeNames = accounts.ok
    ? accounts.data.filter((account) => account.is_active).map((account) => account.username)
    : [];

  return (
    <>
      <PageHeader
        title="👥 User Administration"
        subtitle="Roles are ranked: VIEWER reads, OPERATOR also acts on cases, ADMIN also manages accounts."
      />

      <Callout tone="bad" title="No role overrides the fraud hard stop">
        <code>ADMIN</code> manages accounts. It does not gain a way to retry a fraud-risk
        decline, exceed the retry cap, or act on a suppressed route: those refusals sit below
        every role in the guardrail chain, and there is no request field that turns them off. A
        reviewer&apos;s approval is an input to the decision engine, which can still withhold it.
      </Callout>

      {!accounts.ok ? (
        <ErrorNote message={accounts.message} />
      ) : (
        <Card title="Accounts" hint={`Tenant ${session.tenantId}.`}>
          <TableWrap>
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Username</th>
                  <th>Role</th>
                  <th>Tenant</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Last sign-in</th>
                </tr>
              </thead>
              <tbody>
                {accounts.data.map((account) => (
                  <tr key={account.user_id}>
                    <td className="mono">{account.user_id}</td>
                    <td className="mono">
                      {account.username}
                      {account.username === session.username ? " (you)" : ""}
                    </td>
                    <td>
                      <Badge value={account.role} tone="neutral" />
                    </td>
                    <td className="mono">{account.tenant_id}</td>
                    <td>
                      <Badge value={account.is_active ? "ACTIVE" : "INACTIVE"} tone={account.is_active ? "good" : "bad"} />
                    </td>
                    <td className="mono">{formatTimestamp(account.created_at)}</td>
                    <td className="mono">{formatTimestamp(account.last_login_at ?? null)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </Card>
      )}

      <Card title="Create an account" hint="There is no default password and no self-registration.">
        <CreateUserForm defaultTenant={session.tenantId} />
      </Card>

      <Card
        title="Deactivate an account"
        hint="Takes effect on the account's next request, including one made with a token issued before it."
      >
        <DeactivateUserForm candidates={activeNames} currentUsername={session.username} />
      </Card>
    </>
  );
}
