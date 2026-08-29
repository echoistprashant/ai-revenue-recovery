import { OptimizationForm } from "@/components/forms/optimization-form";
import { Callout, Card, PageHeader, SyntheticDisclaimer } from "@/components/ui";
import { requireRole } from "@/lib/api";

export const metadata = { title: "Recovery Optimization — AI Revenue Recovery" };

/**
 * Retry timing and next-best method.
 *
 * These are recommendations, not decisions: the engine takes them as inputs and can
 * still refuse. `/recommendations` reads nothing from the store and writes nothing to
 * it — the history it profiles is the sample posted with the request.
 */
export default async function OptimizationPage() {
  await requireRole("VIEWER");

  return (
    <>
      <PageHeader
        title="🔮 Recovery Optimization"
        subtitle="When to retry, and which method to try next, from a customer's payment history."
      />

      <SyntheticDisclaimer />

      <Callout title="A recommendation is an input, not an instruction">
        A preferred hour and a next-best method are handed to the decision engine, which
        applies the guardrails before anything is scheduled. A recommendation to retry in two
        hours is still refused if the retry cap is reached, the route has an incident, or the
        failure was a fraud decline.
      </Callout>

      <Card
        title="Timing and method profiler"
        hint="Confidence and sample size are reported so a thin sample is visible rather than implied."
      >
        <OptimizationForm />
      </Card>
    </>
  );
}
