import { DriftForm } from "@/components/forms/drift-form";
import { FlushQueueButton } from "@/components/forms/flush-queue-button";
import { Callout, Card, ErrorNote, Metric, PageHeader } from "@/components/ui";
import { allowed } from "@/lib/access";
import { apiGet, attempt, requireRole } from "@/lib/api";
import { formatNumber, formatPercent } from "@/lib/format";
import type { OperationalMetrics, TaskStats } from "@/lib/types";

export const metadata = { title: "Monitoring & Drift — AI Revenue Recovery" };

/** Read a numeric field from a flat metrics map without inventing a value for a missing one. */
function num(source: Record<string, number | string> | undefined, key: string): number | null {
  const value = source?.[key];
  return typeof value === "number" ? value : null;
}

/**
 * Operational health, the durable queue, and model drift.
 *
 * Reading is `VIEWER`; flushing the queue can execute approved actions, so that control
 * is only rendered for an `OPERATOR`. The backend enforces the same rule — hiding the
 * button just avoids offering a viewer something that would answer 403.
 */
export default async function MonitoringPage() {
  const session = await requireRole("VIEWER");

  const [ops, tasks] = await Promise.all([
    attempt(() => apiGet<OperationalMetrics>("/operational-metrics")),
    attempt(() => apiGet<TaskStats>("/tasks/stats")),
  ]);

  const failed = num(tasks.ok ? tasks.data : undefined, "FAILED") ?? 0;

  return (
    <>
      <PageHeader
        title="📈 Monitoring & Data Drift"
        subtitle="API health, the background recovery queue, and population stability."
      />

      <Card title="API health" hint="Counters since this process started; they reset on restart.">
        {ops.ok ? (
          <div className="grid grid-4">
            <Metric label="Total API requests" value={formatNumber(num(ops.data, "request_count") ?? 0, 0)} />
            <Metric label="HTTP errors (5xx)" value={formatNumber(num(ops.data, "error_count") ?? 0, 0)} />
            <Metric
              label="Error rate"
              value={formatPercent(num(ops.data, "error_rate"), 2)}
              tone={(num(ops.data, "error_rate") ?? 0) > 0.01 ? "warn" : "good"}
            />
            <Metric
              label="Average latency"
              value={`${formatNumber(num(ops.data, "average_latency_ms"), 1)} ms`}
            />
          </div>
        ) : (
          <ErrorNote message={ops.message} />
        )}
      </Card>

      <Card
        title="⚙️ Background recovery queue"
        hint="Approved actions are executed by the worker, not by the ingesting request, so a delayed retry survives a restart."
      >
        {tasks.ok ? (
          <div className="grid grid-4">
            <Metric label="Execution mode" value={String(tasks.data["execution_mode"] ?? "inline").toUpperCase()} />
            <Metric label="Pending" value={formatNumber(num(tasks.data, "PENDING") ?? 0, 0)} />
            <Metric label="Due now" value={formatNumber(num(tasks.data, "due_now") ?? 0, 0)} />
            <Metric label="Completed" value={formatNumber(num(tasks.data, "DONE") ?? 0, 0)} />
            <Metric
              label="Failed"
              value={formatNumber(failed, 0)}
              tone={failed > 0 ? "bad" : "neutral"}
              note={failed > 0 ? "Approved actions that never executed — worth investigating." : undefined}
            />
          </div>
        ) : (
          <ErrorNote message={tasks.message} />
        )}

        <div className="section-gap">
          <p>
            Every queued task is re-checked against the decision engine before it runs. A queued
            row records that an action was approved earlier; it is not authority to act now, which
            is why a task can be withheld at execution time.
          </p>
          {allowed(session.role, "OPERATOR") ? (
            <FlushQueueButton />
          ) : (
            <Callout>
              Flushing due background work requires the <code>OPERATOR</code> role.
            </Callout>
          )}
        </div>
      </Card>

      <Card
        title="🧪 PSI data drift detection"
        hint="Whether the payment-method mix has shifted away from the training baseline."
      >
        <DriftForm />
      </Card>
    </>
  );
}
