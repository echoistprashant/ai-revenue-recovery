import { FlushQueueButton } from "@/components/forms/flush-queue-button";
import { IngestEventForm } from "@/components/forms/ingest-event-form";
import { WebhookSimulator } from "@/components/forms/webhook-simulator";
import { Callout, Card, ErrorNote, KeyValues, PageHeader, PipelineFlow } from "@/components/ui";
import { apiGet, attempt, requireRole } from "@/lib/api";
import { humanizeEnum } from "@/lib/format";
import type { TaskStats } from "@/lib/types";

export const metadata = { title: "Payment Operations — AI Revenue Recovery" };

/**
 * Where events enter the system.
 *
 * Both entry points on this page — the internal form and the signed webhook — post to
 * endpoints that run the same pipeline: classify, score, apply guardrails, then ask the
 * decision engine. Neither can reach an action directly, which is the property that has
 * to stay true as entry points are added.
 */
export default async function OperationsPage() {
  await requireRole("OPERATOR");

  const stats = await attempt(() => apiGet<TaskStats>("/tasks/stats"));

  return (
    <>
      <PageHeader
        title="💳 Payment Operations"
        subtitle="Ingest failure events directly or as signed gateway webhooks, and drain due background work."
      />

      <Card title="What happens to an event you submit here">
        <PipelineFlow activeStep={0} />
      </Card>

      <Card
        title="📝 Internal schema form"
        hint="One failure event in the platform's own shape. The presets fill the form; nothing is sent until you submit."
      >
        <IngestEventForm />
      </Card>

      <Card
        title="🔗 Razorpay webhook adapter"
        hint="Builds a real Razorpay envelope, signs it with HMAC-SHA256 on the server, and posts it to /webhooks/razorpay."
      >
        <Callout title="The signing secret stays on the server">
          This page never receives <code>RAZORPAY_WEBHOOK_SECRET</code>. The payload below is
          sent to a route handler in this app, which signs the exact bytes it forwards. That
          route requires the <code>OPERATOR</code> role, because the backend endpoint is
          authenticated by signature alone — a gateway cannot hold a password. If no secret is
          configured the request is refused rather than signed with a known development value.
        </Callout>
        <div className="section-gap">
          <WebhookSimulator />
        </div>
      </Card>

      <Card
        title="⚙️ Background work"
        hint="Scheduled retries and messages wait in a durable queue until they are due."
      >
        {stats.ok ? (
          <KeyValues
            rows={Object.entries(stats.data).map(([key, value]) => [
              humanizeEnum(key),
              <code key={key}>{String(value)}</code>,
            ])}
          />
        ) : (
          <ErrorNote message={stats.message} />
        )}
        <div className="section-gap">
          <FlushQueueButton />
          <p className="field-hint">
            Flushing claims due tasks and runs them through the decision engine again. A task
            whose guardrail state changed since it was queued — a retry that has since hit the
            cap, a route that is now suppressed — is withheld at execution time, not honoured
            because it was scheduled earlier.
          </p>
        </div>
      </Card>
    </>
  );
}
