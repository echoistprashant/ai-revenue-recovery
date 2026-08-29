"use client";

import { useState } from "react";

import { apiPost, messageOf } from "@/lib/client";
import { formatPercent } from "@/lib/format";
import {
  FAILURE_CATEGORIES,
  PAYMENT_METHODS,
  type DecisionResponse,
  type FailureCategory,
  type PaymentMethod,
} from "@/lib/types";

/**
 * The decision and guardrail simulator.
 *
 * It evaluates the same rules the pipeline uses, without writing anything: a run here
 * ingests no event, queues no task, and sends no message. That makes it safe to point at
 * `FRAUD_RISK_DECLINE` and watch the hard stop refuse, which is the most useful thing
 * this panel does.
 */
export function DecisionSimulatorForm() {
  const [category, setCategory] = useState<FailureCategory>("INSUFFICIENT_FUNDS");
  const [amount, setAmount] = useState(5000);
  const [retryCount, setRetryCount] = useState(0);
  const [probability, setProbability] = useState(0.75);
  const [incidentActive, setIncidentActive] = useState(false);
  const [method, setMethod] = useState<PaymentMethod | "None">("CARD");
  const [contactedHoursAgo, setContactedHoursAgo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DecisionResponse | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    const hours = Number(contactedHoursAgo);
    const lastContactAt =
      contactedHoursAgo !== "" && Number.isFinite(hours)
        ? new Date(Date.now() - hours * 3_600_000).toISOString()
        : null;
    try {
      setResult(
        await apiPost<DecisionResponse>("/decisions", {
          failure_category: category,
          amount,
          retry_count: retryCount,
          recovery_probability: probability,
          incident_active: incidentActive,
          recommended_method: method === "None" ? null : method,
          last_contact_at: lastContactAt,
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
          <label htmlFor="dc-category">Failure category</label>
          <select
            id="dc-category"
            value={category}
            onChange={(change) => setCategory(change.target.value as FailureCategory)}
          >
            {FAILURE_CATEGORIES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="dc-amount">Transaction amount (₹)</label>
          <input
            id="dc-amount"
            type="number"
            min={1}
            step={1}
            value={amount}
            onChange={(change) => setAmount(Math.max(1, Number(change.target.value) || 1))}
          />
        </div>
        <div className="field">
          <label htmlFor="dc-retries">Retries already made</label>
          <input
            id="dc-retries"
            type="number"
            min={0}
            value={retryCount}
            onChange={(change) => setRetryCount(Math.max(0, Number(change.target.value) || 0))}
          />
        </div>
      </div>
      <div className="form-row">
        <div className="field">
          <label htmlFor="dc-probability">Recovery probability — {formatPercent(probability, 0)}</label>
          <input
            id="dc-probability"
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={probability}
            onChange={(change) => setProbability(Number(change.target.value))}
          />
        </div>
        <div className="field">
          <label htmlFor="dc-method">Recommended method</label>
          <select
            id="dc-method"
            value={method}
            onChange={(change) => setMethod(change.target.value as PaymentMethod | "None")}
          >
            {PAYMENT_METHODS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
            <option value="None">None</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="dc-contact">Last contacted (hours ago)</label>
          <input
            id="dc-contact"
            type="number"
            min={0}
            step={1}
            value={contactedHoursAgo}
            placeholder="never"
            onChange={(change) => setContactedHoursAgo(change.target.value)}
          />
          <span className="field-hint">Leave blank for no prior contact. Recent contact trips the cooldown guardrail.</span>
        </div>
      </div>
      <label style={{ display: "flex", gap: "8px", alignItems: "center", margin: "0 0 12px" }}>
        <input
          type="checkbox"
          checked={incidentActive}
          onChange={(change) => setIncidentActive(change.target.checked)}
          style={{ width: "auto" }}
        />
        <span>Gateway incident active on this route</span>
      </label>

      <button type="submit" disabled={busy}>
        {busy ? "Evaluating…" : "Evaluate decision rules"}
      </button>
      <span className="field-hint">
        Evaluation only — nothing is ingested, queued, or sent.
      </span>

      {error ? (
        <div className="callout bad section-gap" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      {result ? (
        <div className={`callout ${result.guardrail_rule ? "warn" : "good"} section-gap`}>
          <strong>
            {result.guardrail_rule
              ? `🛡️ Guardrail triggered: ${result.guardrail_rule} → ${result.action}`
              : `Selected action: ${result.action}`}
          </strong>
          <p>
            <span className="field-hint">Guardrail verdict</span>
            <br />
            {result.guardrail_reason}
          </p>
          <p>
            <span className="field-hint">Engine explanation</span>
            <br />
            {result.reason}
          </p>
        </div>
      ) : null}
    </form>
  );
}
