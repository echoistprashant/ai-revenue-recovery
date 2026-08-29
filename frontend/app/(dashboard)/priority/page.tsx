import Link from "next/link";

import { Badge, Card, EmptyState, ErrorNote, KeyValues, Metric, PageHeader, TableWrap } from "@/components/ui";
import { apiGet, attempt, requireRole } from "@/lib/api";
import { formatCurrency, formatNumber, formatPercent, formatScore } from "@/lib/format";
import type { PriorityCase } from "@/lib/types";

export const metadata = { title: "Priority Cases — AI Revenue Recovery" };

const LIMITS = [5, 10, 20, 50];

/**
 * Open cases ranked by recoverable value.
 *
 * The limit and the selected case are URL state rather than component state, so a
 * drill-down is a shareable link and the page needs no client JavaScript at all.
 */
export default async function PriorityPage({
  searchParams,
}: {
  searchParams: Promise<{ limit?: string; payment?: string }>;
}) {
  await requireRole("VIEWER");
  const { limit: rawLimit, payment } = await searchParams;
  const limit = LIMITS.includes(Number(rawLimit)) ? Number(rawLimit) : 10;

  const cases = await attempt(() => apiGet<PriorityCase[]>("/priority-cases", { limit }));

  return (
    <>
      <PageHeader
        title="🎯 Priority Cases"
        subtitle="Priority score = recovery probability × churn risk × revenue at risk."
      />

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

      {!cases.ok ? (
        <ErrorNote message={cases.message} />
      ) : cases.data.length === 0 ? (
        <Card>
          <EmptyState>
            No priority cases yet. Ingest payment events first — a case appears once it has
            been scored.
          </EmptyState>
        </Card>
      ) : (
        <>
          <Card title="Ranked cases" hint="Highest recoverable value first.">
            <TableWrap>
              <table>
                <thead>
                  <tr>
                    <th>Payment</th>
                    <th>Attempt</th>
                    <th>Category</th>
                    <th className="numeric">Amount</th>
                    <th className="numeric">P(recovery)</th>
                    <th className="numeric">Churn risk</th>
                    <th className="numeric">Revenue at risk</th>
                    <th className="numeric">Priority</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {cases.data.map((item) => (
                    <tr key={`${item.payment_id}-${item.attempt_id}`}>
                      <td className="mono">{item.payment_id}</td>
                      <td className="mono">{item.attempt_id}</td>
                      <td>
                        <Badge value={item.failure_category} />
                      </td>
                      <td className="numeric">{formatCurrency(item.amount)}</td>
                      <td className="numeric">{formatScore(item.recovery_probability)}</td>
                      <td className="numeric">{formatScore(item.churn_risk, 2)}</td>
                      <td className="numeric">{formatCurrency(item.revenue_at_risk)}</td>
                      <td className="numeric">{formatNumber(item.priority_score, 2)}</td>
                      <td>
                        <Link href={`/priority?limit=${limit}&payment=${encodeURIComponent(item.payment_id)}`}>
                          Inspect
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </Card>

          {payment ? <CaseDetail cases={cases.data} paymentId={payment} /> : null}
        </>
      )}
    </>
  );
}

function CaseDetail({ cases, paymentId }: { cases: PriorityCase[]; paymentId: string }) {
  const detail = cases.find((item) => item.payment_id === paymentId);
  if (!detail) {
    return (
      <Card title="Case drill-down">
        <EmptyState>
          <code>{paymentId}</code> is not in the loaded page of cases. Raise the limit or
          clear the selection.
        </EmptyState>
      </Card>
    );
  }
  return (
    <Card title={`Case drill-down — ${detail.payment_id}`} hint="Signals behind the ranking.">
      <div className="grid grid-4">
        <Metric label="Recovery probability" value={formatPercent(detail.recovery_probability, 2)} />
        <Metric label="Churn risk" value={formatScore(detail.churn_risk, 2)} />
        <Metric label="Revenue at risk" value={formatCurrency(detail.revenue_at_risk)} />
        <Metric label="Priority score" value={formatNumber(detail.priority_score, 2)} />
      </div>
      <div className="section-gap">
        <KeyValues
          rows={[
            ["Payment ID", <code key="p">{detail.payment_id}</code>],
            ["Attempt ID", <code key="a">{detail.attempt_id}</code>],
            ["Failure category", <Badge key="c" value={detail.failure_category} />],
            ["Amount", formatCurrency(detail.amount)],
            ["Model version", <code key="m">{detail.model_version}</code>],
          ]}
        />
      </div>
    </Card>
  );
}
