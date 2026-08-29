import Link from "next/link";

import { AuditTrail } from "@/components/audit-trail";
import { ResolveCaseForm } from "@/components/forms/resolve-case-form";
import {
  Badge,
  Callout,
  Card,
  EmptyState,
  ErrorNote,
  KeyValues,
  Metric,
  PageHeader,
  TableWrap,
} from "@/components/ui";
import { allowed } from "@/lib/access";
import { apiGet, attempt, requireRole } from "@/lib/api";
import { formatCurrency, formatNumber, formatPercent, formatScore, formatTimestamp } from "@/lib/format";
import type { AuditEntry, ReviewCase } from "@/lib/types";

export const metadata = { title: "Human Review Queue — AI Revenue Recovery" };

const LIMITS = [10, 20, 50];

/**
 * Cases the high-value guardrail escalated instead of acting on.
 *
 * Reading the queue needs `VIEWER`; resolving needs `OPERATOR`, and the resolve form is
 * only rendered for a role that has it. The backend enforces the same rule — a viewer
 * who posts the request anyway gets 403.
 */
export default async function ReviewPage({
  searchParams,
}: {
  searchParams: Promise<{ limit?: string; case?: string }>;
}) {
  const session = await requireRole("VIEWER");
  const { limit: rawLimit, case: rawCase } = await searchParams;
  const limit = LIMITS.includes(Number(rawLimit)) ? Number(rawLimit) : 20;
  const selectedId = Number(rawCase);

  const queue = await attempt(() => apiGet<ReviewCase[]>("/review-queue", { limit }));
  const selected =
    queue.ok && Number.isInteger(selectedId)
      ? queue.data.find((item) => item.event_id === selectedId)
      : undefined;
  const trail = selected
    ? await attempt(() => apiGet<AuditEntry[]>("/audit-log", { event_id: selected.event_id }))
    : null;

  return (
    <>
      <PageHeader
        title="🧑‍⚖️ Human Review Queue"
        subtitle="High-value cases the guardrails escalated, ordered by priority score."
      />

      <Callout tone="warn" title="A reviewer's approval is an input, not an authority">
        Choosing <code>MANUAL_RETRY</code> re-submits the case to the deterministic decision
        engine, which can still withhold it. A fraud decline, a capped retry, or an active
        gateway incident is refused no matter who approves it — including an{" "}
        <code>ADMIN</code>. A fraud-risk decline never reaches this queue at all.
      </Callout>

      <Card>
        <form method="get" className="actions">
          <label htmlFor="limit">Cases to load</label>
          <select id="limit" name="limit" defaultValue={String(limit)}>
            {LIMITS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <button type="submit" className="secondary">
            Apply
          </button>
        </form>
      </Card>

      {!queue.ok ? (
        <ErrorNote message={queue.message} />
      ) : queue.data.length === 0 ? (
        <Card>
          <Callout tone="good">Nothing is waiting for a human. The escalation queue is empty.</Callout>
        </Card>
      ) : (
        <Card title="Escalated cases">
          <TableWrap>
            <table>
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Payment</th>
                  <th>Customer</th>
                  <th className="numeric">Amount</th>
                  <th>Category</th>
                  <th className="numeric">P(recovery)</th>
                  <th className="numeric">Priority</th>
                  <th>Reason</th>
                  <th>Escalated</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {queue.data.map((item) => (
                  <tr key={item.event_id}>
                    <td className="mono">{item.event_id}</td>
                    <td className="mono">{item.payment_id}</td>
                    <td className="mono">{item.customer_id}</td>
                    <td className="numeric">{formatCurrency(item.amount, item.currency)}</td>
                    <td>
                      <Badge value={item.failure_category} />
                    </td>
                    <td className="numeric">{formatScore(item.recovery_probability)}</td>
                    <td className="numeric">{formatNumber(item.priority_score, 2)}</td>
                    <td>{item.reason}</td>
                    <td className="mono">{formatTimestamp(item.created_at)}</td>
                    <td>
                      <Link href={`/review?limit=${limit}&case=${item.event_id}`}>Review</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </Card>
      )}

      {rawCase && !selected && queue.ok ? (
        <Card title="Case review">
          <EmptyState>
            Event <code>{rawCase}</code> is not in the loaded queue — it may already have been
            resolved. Raise the limit or clear the selection.
          </EmptyState>
        </Card>
      ) : null}

      {selected ? (
        <Card title={`Case review — event ${selected.event_id}`}>
          <div className="grid grid-4">
            <Metric label="Amount" value={formatCurrency(selected.amount, selected.currency)} />
            <Metric
              label="Recovery probability"
              value={formatPercent(selected.recovery_probability, 2)}
            />
            <Metric label="Churn risk" value={formatScore(selected.churn_risk, 2)} />
            <Metric label="Priority score" value={formatNumber(selected.priority_score, 2)} />
          </div>

          <div className="section-gap">
            <KeyValues
              rows={[
                ["Why it escalated", selected.reason],
                ["Current state", <Badge key="s" value={selected.final_state} />],
                ["Engine action", <Badge key="a" value={selected.action} />],
                ["Payment / attempt", <code key="p">{`${selected.payment_id} / ${selected.attempt_id}`}</code>],
                ["Customer", <code key="c">{selected.customer_id}</code>],
                ["Revenue at risk", formatCurrency(selected.revenue_at_risk, selected.currency)],
              ]}
            />
          </div>

          <div className="section-gap">
            <h3 className="card-title">Audit trail for this case</h3>
            {trail?.ok ? <AuditTrail entries={trail.data} /> : <ErrorNote message={trail?.message ?? "Not loaded."} />}
          </div>

          <div className="section-gap">
            <h3 className="card-title">Resolve</h3>
            {allowed(session.role, "OPERATOR") ? (
              <ResolveCaseForm eventId={selected.event_id} />
            ) : (
              <Callout>
                Resolving a case requires the <code>OPERATOR</code> role. You can read the queue
                and its audit trail.
              </Callout>
            )}
          </div>
        </Card>
      ) : null}
    </>
  );
}
