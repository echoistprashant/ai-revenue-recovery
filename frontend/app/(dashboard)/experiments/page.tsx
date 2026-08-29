import { ExperimentForm } from "@/components/forms/experiment-form";
import { Callout, Card, PageHeader, SyntheticDisclaimer } from "@/components/ui";
import { requireRole } from "@/lib/api";

export const metadata = { title: "Experiments & What-If — AI Revenue Recovery" };

/**
 * Offline strategy comparison.
 *
 * Everything here is a projection over a generated population. Nothing on this page
 * changes live behaviour, and a favourable result does not become policy — promoting a
 * projection to a live self-modifying rule is exactly what the platform does not do.
 */
export default async function ExperimentsPage() {
  await requireRole("VIEWER");

  return (
    <>
      <PageHeader
        title="🧪 Experiments & What-If"
        subtitle="Control versus treatment on a reproducible synthetic population."
      />

      <SyntheticDisclaimer />

      <Callout title="A projection, not a promotion path">
        The population is generated from a fixed formula, so two runs with the same inputs give
        the same answer — useful for reasoning about a strategy, useless as a claim about real
        performance. Results stay offline: no experiment outcome rewrites the decision rules,
        and no lift parameter loosens a guardrail. Changing live behaviour is a code change that
        goes through review.
      </Callout>

      <Card
        title="Strategy comparison"
        hint="The interval is shown before the verdict, because the verdict is only as good as the interval."
      >
        <ExperimentForm />
      </Card>
    </>
  );
}
