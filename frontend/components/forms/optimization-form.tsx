"use client";

import { useState } from "react";

import { apiPost, messageOf } from "@/lib/client";
import { formatPercent } from "@/lib/format";
import { PAYMENT_METHODS, type OptimizationResponse, type PaymentMethod } from "@/lib/types";

/**
 * Retry-timing and next-best-method recommendations.
 *
 * The two history rows below are a deliberately small synthetic sample so the panel can
 * be used without a populated store — which is also why the response carries a sample
 * size and a confidence, and why they are shown rather than hidden. A recommendation
 * from two observations is a recommendation from two observations.
 *
 * A recommendation is an input to the decision engine, not an instruction: the engine
 * still applies the guardrails before any of this is acted on.
 */
export function OptimizationForm() {
  const [customerId, setCustomerId] = useState("cust_opt_100");
  const [referenceHour, setReferenceHour] = useState(14);
  const [historyMethod, setHistoryMethod] = useState<PaymentMethod>("UPI");
  const [historySuccess, setHistorySuccess] = useState(true);
  const [historyHour, setHistoryHour] = useState(20);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OptimizationResponse | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    const hour = String(historyHour).padStart(2, "0");
    const history = [
      {
        customer_id: customerId,
        timestamp: `2026-08-20T${hour}:00:00Z`,
        payment_method: historyMethod,
        successful: historySuccess,
      },
      {
        customer_id: customerId,
        timestamp: `2026-08-21T${hour}:00:00Z`,
        payment_method: historyMethod,
        successful: true,
      },
    ];
    try {
      setResult(
        await apiPost<OptimizationResponse>("/recommendations", {
          customer_id: customerId,
          reference_hour: referenceHour,
          history,
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
          <label htmlFor="op-customer">Customer ID</label>
          <input
            id="op-customer"
            value={customerId}
            onChange={(change) => setCustomerId(change.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="op-hour">Reference hour (UTC) — {referenceHour}:00</label>
          <input
            id="op-hour"
            type="range"
            min={0}
            max={23}
            step={1}
            value={referenceHour}
            onChange={(change) => setReferenceHour(Number(change.target.value))}
          />
        </div>
      </div>

      <h3 className="card-title">Customer payment history sample</h3>
      <div className="form-row">
        <div className="field">
          <label htmlFor="op-method">Historical method</label>
          <select
            id="op-method"
            value={historyMethod}
            onChange={(change) => setHistoryMethod(change.target.value as PaymentMethod)}
          >
            {PAYMENT_METHODS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="op-hist-hour">Historical hour — {historyHour}:00</label>
          <input
            id="op-hist-hour"
            type="range"
            min={0}
            max={23}
            step={1}
            value={historyHour}
            onChange={(change) => setHistoryHour(Number(change.target.value))}
          />
        </div>
      </div>
      <label style={{ display: "flex", gap: "8px", alignItems: "center", margin: "0 0 12px" }}>
        <input
          type="checkbox"
          checked={historySuccess}
          onChange={(change) => setHistorySuccess(change.target.checked)}
          style={{ width: "auto" }}
        />
        <span>First historical attempt succeeded</span>
      </label>

      <button type="submit" disabled={busy}>
        {busy ? "Profiling…" : "Generate recommendations"}
      </button>
      <span className="field-hint">
        Two synthetic history rows are sent for the customer above. Nothing is stored.
      </span>

      {error ? (
        <div className="callout bad section-gap" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      {result ? (
        <div className="grid grid-2 section-gap">
          <div className="card">
            <h3 className="card-title">⏱️ Recommended retry window</h3>
            <ul className="stack">
              <li>
                Retry after <code>{result.retry_after_hours}h</code>
              </li>
              <li>
                Preferred hour <code>{result.preferred_hour}:00 UTC</code>
              </li>
              <li>
                Confidence <code>{formatPercent(result.timing_confidence, 1)}</code>
              </li>
            </ul>
            <p className="inline-note">{result.timing_reason}</p>
          </div>
          <div className="card">
            <h3 className="card-title">💳 Next-best payment method</h3>
            <ul className="stack">
              <li>
                Method <code>{result.recommended_payment_method}</code>
              </li>
              <li>
                Historical success rate <code>{formatPercent(result.method_success_rate, 1)}</code>
              </li>
              <li>
                Sample size <code>{result.method_sample_size} observations</code>
              </li>
              <li>
                Confidence <code>{formatPercent(result.method_confidence, 1)}</code>
              </li>
            </ul>
            <p className="inline-note">{result.method_reason}</p>
          </div>
        </div>
      ) : null}
    </form>
  );
}
