import {
  BarList,
  Card,
  ErrorNote,
  Metric,
  PageHeader,
  SyntheticDisclaimer,
} from "@/components/ui";
import { apiGet, attempt, requireRole } from "@/lib/api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/format";
import type { OperationalMetrics, RecoveryMetrics, TaskStats } from "@/lib/types";

export const metadata = { title: "Executive Overview — AI Revenue Recovery" };

/**
 * Tenant-level recovery position.
 *
 * Each panel loads independently, so an unreachable `/operational-metrics` shows one
 * inline message instead of blanking the recovery figures next to it.
 */
export default async function OverviewPage() {
  await requireRole("VIEWER");

  const [metrics, operational, tasks] = await Promise.all([
    attempt(() => apiGet<RecoveryMetrics>("/metrics")),
    attempt(() => apiGet<OperationalMetrics>("/operational-metrics")),
    attempt(() => apiGet<TaskStats>("/tasks/stats")),
  ]);

  return (
    <>
      <PageHeader
        title="📊 Executive Overview"
        subtitle="Recovery rate, recovered revenue, and failure mix for your tenant."
      />
      <SyntheticDisclaimer />

      {metrics.ok ? (
        <>
          <div className="grid grid-4">
            <Metric
              label="Total failed payments"
              value={formatNumber(metrics.data.total_failures)}
              note={`${formatNumber(metrics.data.unresolved_events)} still unresolved`}
            />
            <Metric
              label="Simulated recovered events"
              value={formatNumber(metrics.data.recovered_events)}
              note={`${formatNumber(metrics.data.resolved_events)} resolved`}
              tone="good"
            />
            <Metric
              label="Simulated recovery rate"
              value={formatPercent(metrics.data.recovery_rate)}
              note="Recovered ÷ resolved"
            />
            <Metric
              label="Simulated recovered revenue"
              value={formatCurrency(metrics.data.recovered_revenue)}
              note="Sum of recovered amounts"
              tone="good"
            />
          </div>

          <div className="grid grid-2 section-gap">
            <Card
              title="Failure category breakdown"
              hint="Classified by the rule-based classifier, not by the model."
            >
              <BarList
                items={Object.entries(metrics.data.failure_breakdown)
                  .sort(([, a], [, b]) => b - a)
                  .map(([label, value]) => ({ label, value, display: formatNumber(value) }))}
              />
            </Card>

            <Card title="Service and model status">
              {operational.ok ? (
                <div className="grid grid-2">
                  <Metric label="Deployed model" value={String(operational.data.model_version ?? "unavailable")} />
                  <Metric
                    label="API requests observed"
                    value={formatNumber(Number(operational.data.request_count ?? 0))}
                  />
                  <Metric
                    label="Error rate"
                    value={formatPercent(Number(operational.data.error_rate ?? 0), 2)}
                    tone={Number(operational.data.error_rate ?? 0) > 0 ? "warn" : "good"}
                  />
                  <Metric
                    label="Average latency"
                    value={`${formatNumber(Number(operational.data.average_latency_ms ?? 0), 1)} ms`}
                  />
                </div>
              ) : (
                <ErrorNote message={operational.message} />
              )}

              {tasks.ok ? (
                <p className="inline-note">
                  Queue: mode <code>{String(tasks.data.execution_mode ?? "inline")}</code> ·{" "}
                  {formatNumber(Number(tasks.data.PENDING ?? 0))} pending ·{" "}
                  {formatNumber(Number(tasks.data.due_now ?? 0))} due now ·{" "}
                  {formatNumber(Number(tasks.data.FAILED ?? 0))} failed. Every queued task is
                  re-checked by the decision engine before it runs.
                </p>
              ) : (
                <p className="inline-note">Queue statistics unavailable: {tasks.message}</p>
              )}
            </Card>
          </div>
        </>
      ) : (
        <ErrorNote message={metrics.message} />
      )}
    </>
  );
}
