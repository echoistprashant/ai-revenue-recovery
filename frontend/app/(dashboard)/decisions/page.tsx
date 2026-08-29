import { DecisionSimulatorForm } from "@/components/forms/decision-simulator-form";
import { Card, PageHeader, PipelineFlow, SafetyCallout, TableWrap } from "@/components/ui";
import { requireRole } from "@/lib/api";

export const metadata = { title: "Decision Center — AI Revenue Recovery" };

/** The guardrails, in the order they are evaluated. Order is the whole design. */
const GUARDRAILS: readonly { rule: string; forces: string; when: string }[] = [
  {
    rule: "FRAUD_HARD_STOP",
    forces: "STOP_RECOVERY",
    when: "The failure category is FRAUD_RISK_DECLINE. Checked first, and there is no override — no role, no reviewer, and no queued task can get past it.",
  },
  {
    rule: "RETRY_CAP",
    forces: "STOP_RECOVERY",
    when: "The attempt count has reached the configured maximum (default 3), whatever the model scored.",
  },
  {
    rule: "HIGH_VALUE_REVIEW",
    forces: "ESCALATE_TO_HUMAN",
    when: "The amount exceeds the human-review threshold (default ₹50,000). The case goes to the review queue instead of being acted on.",
  },
  {
    rule: "ACTIVE_INCIDENT",
    forces: "SUPPRESS_RETRY",
    when: "The bank/gateway route has an active incident, so a retry would fail for reasons that have nothing to do with the customer.",
  },
  {
    rule: "CONTACT_COOLDOWN",
    forces: "SEND_NOTIFICATION",
    when: "The customer was contacted inside the cooldown window (default 24h), so another message is withheld.",
  },
];

/**
 * The decision engine, explained and made pokeable.
 *
 * The simulator is read-only by construction: `/decisions` evaluates rules and returns a
 * verdict without touching the store, so nothing on this page can start a recovery.
 */
export default async function DecisionsPage() {
  await requireRole("VIEWER");

  return (
    <>
      <PageHeader
        title="🧠 Decision Center"
        subtitle="The deterministic engine and the guardrails that sit in front of it."
      />

      <SafetyCallout />

      <Card title="Where a decision is made" hint="Guardrails run between scoring and the engine — never after it.">
        <PipelineFlow activeStep={4} />
      </Card>

      <Card
        title="Guardrail evaluation order"
        hint="The first rule that matches decides, which is why the fraud stop is checked first."
      >
        <TableWrap>
          <table>
            <thead>
              <tr>
                <th>Rule</th>
                <th>Forced action</th>
                <th>Fires when</th>
              </tr>
            </thead>
            <tbody>
              {GUARDRAILS.map((item) => (
                <tr key={item.rule}>
                  <td className="mono">{item.rule}</td>
                  <td className="mono">{item.forces}</td>
                  <td className="wrap-text">{item.when}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      </Card>

      <Card
        title="Interactive decision and guardrail simulator"
        hint="Change the signals and see which rule claims the decision."
      >
        <DecisionSimulatorForm />
      </Card>
    </>
  );
}
