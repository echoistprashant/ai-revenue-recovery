import Link from "next/link";

import { AuditTrail } from "@/components/audit-trail";
import { Badge, Card, EmptyState, ErrorNote, PageHeader, TableWrap } from "@/components/ui";
import { apiGet, attempt, requireRole } from "@/lib/api";
import { formatCurrency, formatNumber, formatTimestamp } from "@/lib/format";
import type { AuditEntry, EventHistoryItem } from "@/lib/types";

export const metadata = { title: "Audit & Decision History — AI Revenue Recovery" };

const LIMITS = [10, 25, 50, 100, 200];

/**
 * Decision history, and the audit trail behind any row of it.
 *
 * Both the limit and the selected event are URL state, so a link to a specific event's
 * trail is a link someone else can open — which matters for an audit surface.
 */
export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<{ limit?: string; event?: string }>;
}) {
  await requireRole("VIEWER");
  const { limit: rawLimit, event: rawEvent } = await searchParams;
  const limit = LIMITS.includes(Number(rawLimit)) ? Number(rawLimit) : 50;
  const eventId = Number(rawEvent);
  const hasEvent = rawEvent !== undefined && Number.isInteger(eventId);

  const history = await attempt(() => apiGet<EventHistoryItem[]>("/history", { limit }));
  const trail = hasEvent
    ? await attempt(() => apiGet<AuditEntry[]>("/audit-log", { event_id: eventId }))
    : null;

  return (
    <>
      <PageHeader
        title="📜 Audit & Decision History"
        subtitle="Every processed event, the reason for its decision, and the immutable trail behind it."
      />

      <Card>
        <form method="get" className="actions">
          <label htmlFor="limit">Events to display</label>
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

      {!history.ok ? (
        <ErrorNote message={history.message} />
      ) : history.data.length === 0 ? (
        <Card>
          <EmptyState>
            No decision history recorded yet. Ingest an event from Payment Operations and it will
            appear here with its full trail.
          </EmptyState>
        </Card>
      ) : (
        <Card title="Processed events" hint="Most recent first.">
          <TableWrap>
            <table>
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Payment</th>
                  <th>Customer</th>
                  <th className="numeric">Amount</th>
                  <th>Category</th>
                  <th>Action</th>
                  <th>Reason</th>
                  <th>Final state</th>
                  <th>Recovered</th>
                  <th className="numeric">Priority</th>
                  <th>Occurred</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {history.data.map((item) => (
                  <tr key={item.event_id}>
                    <td className="mono">{item.event_id}</td>
                    <td className="mono">{item.payment_id}</td>
                    <td className="mono">{item.customer_id}</td>
                    <td className="numeric">{formatCurrency(item.amount, item.currency)}</td>
                    <td>
                      <Badge value={item.failure_category} />
                    </td>
                    <td>
                      <Badge value={item.action} />
                    </td>
                    <td className="wrap-text">{item.reason}</td>
                    <td className="mono">{item.final_state}</td>
                    <td className="mono">
                      {item.recovered === null || item.recovered === undefined
                        ? "—"
                        : String(item.recovered)}
                    </td>
                    <td className="numeric">{formatNumber(item.priority_score ?? null, 2)}</td>
                    <td className="mono">{formatTimestamp(item.event_timestamp)}</td>
                    <td>
                      <Link href={`/audit?limit=${limit}&event=${item.event_id}`}>Trail</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </Card>
      )}

      {hasEvent ? (
        <Card
          title={`🔍 Audit trail — event ${eventId}`}
          hint="What was classified, what the model scored, which guardrail fired, and what the worker did."
        >
          {trail?.ok ? <AuditTrail entries={trail.data} /> : <ErrorNote message={trail?.message ?? "Not loaded."} />}
        </Card>
      ) : null}
    </>
  );
}
