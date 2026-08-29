import { AnalystForm } from "@/components/forms/analyst-form";
import { Callout, Card, PageHeader, SyntheticDisclaimer, TableWrap } from "@/components/ui";
import { requireRole } from "@/lib/api";

export const metadata = { title: "AI Revenue Analyst — AI Revenue Recovery" };

const TOOLS: readonly { name: string; returns: string }[] = [
  { name: "get_recovery_metrics()", returns: "Totals, recovery rate, and recovered revenue." },
  { name: "get_failure_breakdown()", returns: "Event counts per failure category." },
  { name: "get_gateway_health()", returns: "Route-level failure rates and incident state." },
  { name: "get_top_priority_cases(n)", returns: "The n highest-priority open cases." },
];

/**
 * Natural-language questions over the same numbers the dashboard shows.
 *
 * The analyst has four read-only tools and nothing else. It cannot write, decide, or
 * trigger — and it is required to answer from a tool result rather than from its own
 * recollection, so a question outside that surface is declined instead of estimated.
 */
export default async function AnalystPage() {
  await requireRole("VIEWER");

  return (
    <>
      <PageHeader
        title="🤖 AI Revenue Analyst"
        subtitle="Business questions answered from tool results, not from the model's memory."
      />

      <SyntheticDisclaimer />

      <Callout title="Read-only by construction">
        Every number in an answer comes from one of the four tools below. There is no write
        tool, no action tool, and no way for a question to start a recovery — the analyst is a
        reader of the same store the dashboard reads. If a question cannot be answered from a
        tool result, the honest answer is that it cannot, and that is what you will get.
      </Callout>

      <Card title="Approved tools">
        <TableWrap>
          <table>
            <thead>
              <tr>
                <th>Tool</th>
                <th>Returns</th>
              </tr>
            </thead>
            <tbody>
              {TOOLS.map((tool) => (
                <tr key={tool.name}>
                  <td className="mono">{tool.name}</td>
                  <td>{tool.returns}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      </Card>

      <Card title="Ask" hint="A quick prompt fills the box and asks in one step.">
        <AnalystForm />
      </Card>
    </>
  );
}
