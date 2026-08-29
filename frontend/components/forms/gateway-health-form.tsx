"use client";

import { useState } from "react";

import { apiPost, messageOf } from "@/lib/client";
import { Metric } from "@/components/ui";
import { formatNumber, formatPercent } from "@/lib/format";
import type { GatewayHealthResponse } from "@/lib/types";

/**
 * The bank/gateway anomaly check.
 *
 * An incident is declared from a rolling failure rate against a baseline, with a minimum
 * event count so a run of three failures on a quiet route does not suppress recovery for
 * everyone on it. When one is active the engine forces `SUPPRESS_RETRY` — the retry would
 * have failed for reasons that have nothing to do with the customer.
 */
export function GatewayHealthForm() {
  const [bank, setBank] = useState("HDFC");
  const [gateway, setGateway] = useState("RAZORPAY");
  const [failures, setFailures] = useState(8);
  const [total, setTotal] = useState(20);
  const [baseline, setBaseline] = useState(0.02);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GatewayHealthResponse | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await apiPost<GatewayHealthResponse>("/gateway-health", {
          bank,
          gateway,
          failures,
          total,
          baseline_failure_rate: baseline,
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
          <label htmlFor="gw-bank">Bank</label>
          <input id="gw-bank" value={bank} onChange={(change) => setBank(change.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="gw-gateway">Gateway</label>
          <input id="gw-gateway" value={gateway} onChange={(change) => setGateway(change.target.value)} required />
        </div>
      </div>

      <div className="form-row">
        <div className="field">
          <label htmlFor="gw-failures">Observed failures</label>
          <input
            id="gw-failures"
            type="number"
            min={0}
            value={failures}
            onChange={(change) => setFailures(Math.max(0, Number(change.target.value) || 0))}
          />
        </div>
        <div className="field">
          <label htmlFor="gw-total">Total events</label>
          <input
            id="gw-total"
            type="number"
            min={1}
            value={total}
            onChange={(change) => setTotal(Math.max(1, Number(change.target.value) || 1))}
          />
          <span className="field-hint">An incident needs a minimum sample (20) before it can be declared.</span>
        </div>
        <div className="field">
          <label htmlFor="gw-baseline">Baseline failure rate</label>
          <input
            id="gw-baseline"
            type="number"
            min={0.001}
            max={1}
            step={0.001}
            value={baseline}
            onChange={(change) => setBaseline(Number(change.target.value) || 0.001)}
          />
        </div>
      </div>
      <button type="submit" disabled={busy}>
        {busy ? "Checking…" : "Check gateway health"}
      </button>
      {failures > total ? (
        <span className="field-hint">Failures cannot exceed total events — the API will refuse this.</span>
      ) : null}

      {error ? (
        <div className="callout bad section-gap" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      {result ? (
        <>
          <div className={`callout ${result.incident_active ? "bad" : "good"} section-gap`} role={result.incident_active ? "alert" : undefined}>
            <strong>
              {result.incident_active
                ? `🚨 Systemic incident on ${result.bank} / ${result.gateway}`
                : `✅ Health normal for ${result.bank} / ${result.gateway}`}
            </strong>
            <p>
              {result.incident_active
                ? "While this is active the engine forces SUPPRESS_RETRY on this route, including for tasks that were queued before the incident began."
                : "Retries on this route are evaluated normally by the decision engine."}
            </p>
          </div>
          <div className="grid grid-3">
            <Metric label="Observed failure rate" value={formatPercent(result.observed_failure_rate, 1)} />
            <Metric label="Baseline failure rate" value={formatPercent(result.baseline_failure_rate, 1)} />
            <Metric
              label="Failure multiplier"
              value={`${formatNumber(result.failure_multiplier, 1)}×`}
              tone={result.incident_active ? "bad" : "neutral"}
            />
          </div>
        </>
      ) : null}
    </form>
  );
}
