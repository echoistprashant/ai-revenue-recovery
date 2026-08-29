import { GatewayHealthForm } from "@/components/forms/gateway-health-form";
import { Callout, Card, PageHeader } from "@/components/ui";
import { requireRole } from "@/lib/api";

export const metadata = { title: "Gateway Health — AI Revenue Recovery" };

/**
 * Route-level anomaly detection.
 *
 * The check is a pure calculation over the counts posted with the request — it does not
 * read live traffic, and it does not itself declare an incident anywhere. What it shows
 * is the rule the guardrail applies, so an operator can see why a route is suppressed.
 */
export default async function GatewayPage() {
  await requireRole("VIEWER");

  return (
    <>
      <PageHeader
        title="🏦 Gateway Health"
        subtitle="Rolling failure rates per bank and gateway, against a configured baseline."
      />

      <Callout title="Why suppression is the safe response">
        When a route is failing systemically, retrying is not just wasted — it burns the
        customer&apos;s trust and the attempt budget on a failure that was never about them.
        The <code>ACTIVE_INCIDENT</code> guardrail forces <code>SUPPRESS_RETRY</code> until the
        route recovers, and a task queued before the incident is withheld when it comes due.
      </Callout>

      <Card
        title="Health check"
        hint="An incident needs both a multiplier above the threshold and enough events to mean anything."
      >
        <GatewayHealthForm />
      </Card>
    </>
  );
}
