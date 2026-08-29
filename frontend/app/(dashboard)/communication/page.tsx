import { CommunicationForm } from "@/components/forms/communication-form";
import { Callout, Card, PageHeader, PipelineFlow, SafetyCallout } from "@/components/ui";
import { requireRole } from "@/lib/api";

export const metadata = { title: "Customer Communication — AI Revenue Recovery" };

/**
 * Bounded copy generation.
 *
 * Requires `OPERATOR` for the same reason the backend route does: generating customer
 * copy is part of acting on a case, not reading about one.
 */
export default async function CommunicationPage() {
  await requireRole("OPERATOR");

  return (
    <>
      <PageHeader
        title="💬 Customer Communication"
        subtitle="The LLM words an approved action. It does not choose one."
      />

      <SafetyCallout />

      <Callout title="The boundary, stated as a pipeline">
        <p className="mono wrap-text">
          deterministic engine approves an action → LLM writes the customer text → operator sends
          it
        </p>
        <p>
          The arrow only points one way. The generator receives the action, the failure category,
          and the amount; it has no tool that can retry a payment, change a method, or close a
          case, and its output is text. If the LLM is unavailable the platform falls back to a
          template rather than skipping the action or inventing one.
        </p>
      </Callout>

      <Card title="Where this sits in the pipeline">
        <PipelineFlow activeStep={5} />
      </Card>

      <Card
        title="Message generator"
        hint="Pick the action the engine approved, and see the copy a customer would read."
      >
        <CommunicationForm />
      </Card>
    </>
  );
}
