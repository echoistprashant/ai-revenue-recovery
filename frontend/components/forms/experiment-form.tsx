"use client";

import { useState } from "react";

import { apiPost, messageOf } from "@/lib/client";
import { Metric, TableWrap } from "@/components/ui";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { ExperimentResponse } from "@/lib/types";

/**
 * Offline A/B projection over a synthetic population.
 *
 * The population is generated from a fixed formula rather than sampled, so a run is
 * reproducible and nobody can mistake the output for measured performance. This is a
 * projection tool: the result never becomes live policy, which is the same rule the
 * offline learning module follows.
 */
export function ExperimentForm() {
  const [experimentId, setExperimentId] = useState("exp_strategy_retry_v2");
  const [population, setPopulation] = useState(40);
  const [lift, setLift] = useState(0.12);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExperimentResponse | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    const events = Array.from({ length: population }, (_, index) => ({
      event_id: `event_${index}`,
      amount: 100 + ((index * 25) % 500),
      latent_recovery_score: ((index * 37) % 100) / 100,
    }));
    try {
      setResult(
        await apiPost<ExperimentResponse>("/experiments", {
          experiment_id: experimentId,
          events,
          treatment_lift: lift,
        }),
      );
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <div className="form-row">
        <div className="field">
          <label htmlFor="ex-id">Experiment ID</label>
          <input
            id="ex-id"
            value={experimentId}
            maxLength={100}
            onChange={(change) => setExperimentId(change.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="ex-population">Synthetic event population — {population}</label>
          <input
            id="ex-population"
            type="range"
            min={10}
            max={200}
            step={1}
            value={population}
            onChange={(change) => setPopulation(Number(change.target.value))}
          />
        </div>
        <div className="field">
          <label htmlFor="ex-lift">Treatment lift parameter — {lift.toFixed(2)}</label>
          <input
            id="ex-lift"
            type="range"
            min={0.01}
            max={0.3}
            step={0.01}
            value={lift}
            onChange={(change) => setLift(Number(change.target.value))}
          />
          <span className="field-hint">An assumption you are testing, not a measured effect.</span>
        </div>
      </div>

      <button type="submit" disabled={busy}>
        {busy ? "Running evaluation…" : "Run experiment and projection"}
      </button>

      {error ? (
        <div className="callout bad section-gap" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      {result ? <ExperimentResult result={result} /> : null}
    </form>
  );
}

/**
 * The two variants side by side, with the interval before the verdict.
 *
 * An indistinguishable result is reported as such rather than as a small win: a delta
 * whose 95% interval crosses zero is not evidence of a lift, and presenting it as one is
 * how a projection turns into a bad decision.
 */
function ExperimentResult({ result }: { result: ExperimentResponse }) {
  const [low, high] = result.confidence_interval_95;
  const percent = (value: number) => `${(value * 100).toFixed(2)}%`;
  const signed = (value: number) => `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
  return (
    <>
      <div className="grid grid-4 section-gap">
        <Metric label="Control recovery rate" value={percent(result.control.recovery_rate)} />
        <Metric label="Treatment recovery rate" value={percent(result.treatment.recovery_rate)} />
        <Metric
          label="Rate delta"
          value={signed(result.recovery_rate_delta)}
          tone={result.statistically_distinguishable ? (result.recovery_rate_delta >= 0 ? "good" : "bad") : "neutral"}
        />
        <Metric
          label="Revenue delta"
          value={`${result.recovered_revenue_delta >= 0 ? "+" : ""}${formatCurrency(result.recovered_revenue_delta)}`}
        />
      </div>

      <div className={`callout ${result.statistically_distinguishable ? "good" : "warn"} section-gap`}>
        <strong>
          {result.statistically_distinguishable
            ? "Statistically distinguishable at 95%"
            : "Not statistically distinguishable at 95%"}
        </strong>
        <p>
          95% CI on the rate delta: <code>[{percent(low)}, {percent(high)}]</code>
          {result.statistically_distinguishable
            ? "."
            : " — the interval includes zero, so this population does not separate the two strategies."}
        </p>
      </div>

      <TableWrap>
        <table>
          <thead>
            <tr>
              <th>Variant</th>
              <th className="numeric">Sample</th>
              <th className="numeric">Recovered</th>
              <th className="numeric">Rate</th>
              <th className="numeric">Recovered revenue</th>
              <th className="numeric">Unresolved</th>
            </tr>
          </thead>
          <tbody>
            {[result.control, result.treatment].map((variant) => (
              <tr key={variant.variant}>
                <td className="mono">{variant.variant}</td>
                <td className="numeric">{formatNumber(variant.sample_size, 0)}</td>
                <td className="numeric">{formatNumber(variant.recovered_count, 0)}</td>
                <td className="numeric">{percent(variant.recovery_rate)}</td>
                <td className="numeric">{formatCurrency(variant.recovered_revenue)}</td>
                <td className="numeric">{formatNumber(variant.unresolved_count, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    </>
  );
}
