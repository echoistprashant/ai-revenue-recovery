"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { apiPost, messageOf } from "@/lib/client";
import { formatCurrency, formatNumber, formatScore } from "@/lib/format";
import { PAYMENT_METHODS, isWithheld, type PaymentMethod, type ProcessedEvent } from "@/lib/types";

interface EventDraft {
  payment_id: string;
  attempt_id: string;
  customer_id: string;
  subscription_id: string;
  amount: number;
  payment_method: PaymentMethod;
  gateway: string;
  bank: string;
  failure_code: string;
  previous_success_count: number;
  previous_failure_count: number;
  customer_age_days: number;
  subscription_value: number;
  retry_count: number;
}

/** A suffix that makes repeated preset use land on a new idempotency key. */
function stamp(): string {
  const now = new Date();
  return `${String(now.getMinutes()).padStart(2, "0")}${String(now.getSeconds()).padStart(2, "0")}`;
}

const PRESETS: readonly { label: string; build: () => EventDraft }[] = [
  {
    label: "🟢 Insufficient funds",
    build: () => ({
      payment_id: `pay_${stamp()}`,
      attempt_id: "att_1",
      customer_id: "cust_101",
      subscription_id: "sub_501",
      amount: 2499,
      payment_method: "CARD",
      gateway: "RAZORPAY",
      bank: "HDFC",
      failure_code: "card_declined_insufficient_funds",
      previous_success_count: 5,
      previous_failure_count: 1,
      customer_age_days: 180,
      subscription_value: 2499,
      retry_count: 0,
    }),
  },
  {
    label: "🔴 Fraud hard stop",
    build: () => ({
      payment_id: `pay_fraud_${stamp()}`,
      attempt_id: "att_1",
      customer_id: "cust_888",
      subscription_id: "sub_888",
      amount: 15000,
      payment_method: "CARD",
      gateway: "RAZORPAY",
      bank: "ICICI",
      failure_code: "fraud_risk_decline",
      previous_success_count: 0,
      previous_failure_count: 3,
      customer_age_days: 10,
      subscription_value: 15000,
      retry_count: 0,
    }),
  },
  {
    label: "⚠️ High value escalation",
    build: () => ({
      payment_id: `pay_highval_${stamp()}`,
      attempt_id: "att_1",
      customer_id: "cust_enterprise",
      subscription_id: "sub_enterprise",
      amount: 75000,
      payment_method: "NET_BANKING",
      gateway: "RAZORPAY",
      bank: "SBI",
      failure_code: "bank_declined_generic",
      previous_success_count: 12,
      previous_failure_count: 0,
      customer_age_days: 365,
      subscription_value: 75000,
      retry_count: 0,
    }),
  },
  {
    label: "🌐 Bank outage",
    build: () => ({
      payment_id: `pay_outage_${stamp()}`,
      attempt_id: "att_1",
      customer_id: "cust_outage",
      subscription_id: "sub_outage",
      amount: 999,
      payment_method: "UPI",
      gateway: "RAZORPAY",
      bank: "AXIS",
      failure_code: "temporary_bank_issue",
      previous_success_count: 2,
      previous_failure_count: 0,
      customer_age_days: 60,
      subscription_value: 999,
      retry_count: 0,
    }),
  },
];

const DEFAULT_DRAFT: EventDraft = {
  payment_id: "pay_test_001",
  attempt_id: "att_1",
  customer_id: "cust_123",
  subscription_id: "sub_456",
  amount: 1999,
  payment_method: "CARD",
  gateway: "RAZORPAY",
  bank: "HDFC",
  failure_code: "card_declined_insufficient_funds",
  previous_success_count: 4,
  previous_failure_count: 1,
  customer_age_days: 120,
  subscription_value: 1999,
  retry_count: 0,
};

/**
 * The internal-schema ingestion form.
 *
 * Submitting posts one failure event to `/events`, which runs the whole pipeline:
 * classification, scoring, guardrails, then the decision engine. The response below is
 * printed as it came back — including a `NO_ACTION` on a fraud decline — because the
 * point of this panel is to watch what the engine does, not to confirm a hope.
 */
export function IngestEventForm() {
  const router = useRouter();
  const [draft, setDraft] = useState<EventDraft>(DEFAULT_DRAFT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProcessedEvent | null>(null);

  function set<K extends keyof EventDraft>(key: K, value: EventDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function number(key: keyof EventDraft) {
    return (event: React.ChangeEvent<HTMLInputElement>) => {
      const parsed = Number(event.target.value);
      set(key, (Number.isFinite(parsed) ? parsed : 0) as EventDraft[typeof key]);
    };
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await apiPost<ProcessedEvent>("/events", draft));
      // Every other panel reads from the same store, so their server render is now stale.
      router.refresh();
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="actions">
        {PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            className="secondary"
            onClick={() => {
              setDraft(preset.build());
              setResult(null);
              setError(null);
            }}
          >
            {preset.label}
          </button>
        ))}
      </div>
      <span className="field-hint">
        A preset fills the form only — nothing is sent until you submit. Each one stamps a
        fresh payment ID so a repeated click is not swallowed as a duplicate.
      </span>
      <form onSubmit={submit} className="section-gap">
        <div className="form-row">
          <div className="field">
            <label htmlFor="payment_id">Payment ID</label>
            <input
              id="payment_id"
              value={draft.payment_id}
              onChange={(event) => set("payment_id", event.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="attempt_id">Attempt ID</label>
            <input
              id="attempt_id"
              value={draft.attempt_id}
              onChange={(event) => set("attempt_id", event.target.value)}
              required
            />
          </div>
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="customer_id">Customer ID</label>
            <input
              id="customer_id"
              value={draft.customer_id}
              onChange={(event) => set("customer_id", event.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="subscription_id">Subscription ID</label>
            <input
              id="subscription_id"
              value={draft.subscription_id}
              onChange={(event) => set("subscription_id", event.target.value)}
              required
            />
          </div>
        </div>
        <div className="form-row">
          <div className="field">
            <label htmlFor="amount">Amount (₹)</label>
            <input id="amount" type="number" min={1} step={1} value={draft.amount} onChange={number("amount")} required />
          </div>
          <div className="field">
            <label htmlFor="payment_method">Payment method</label>
            <select
              id="payment_method"
              value={draft.payment_method}
              onChange={(event) => set("payment_method", event.target.value as PaymentMethod)}
            >
              {PAYMENT_METHODS.map((method) => (
                <option key={method} value={method}>
                  {method}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="gateway">Gateway</label>
            <input id="gateway" value={draft.gateway} onChange={(event) => set("gateway", event.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="bank">Bank</label>
            <input id="bank" value={draft.bank} onChange={(event) => set("bank", event.target.value)} required />
          </div>
        </div>

        <div className="field">
          <label htmlFor="failure_code">Gateway failure code</label>
          <input
            id="failure_code"
            value={draft.failure_code}
            onChange={(event) => set("failure_code", event.target.value)}
            required
          />
          <span className="field-hint">
            The classifier maps this string to a failure category. An unmapped code is
            classified <code>UNKNOWN</code> rather than guessed at.
          </span>
        </div>
        <div className="form-row">
          <div className="field">
            <label htmlFor="previous_success_count">Previous successes</label>
            <input
              id="previous_success_count"
              type="number"
              min={0}
              value={draft.previous_success_count}
              onChange={number("previous_success_count")}
            />
          </div>
          <div className="field">
            <label htmlFor="previous_failure_count">Previous failures</label>
            <input
              id="previous_failure_count"
              type="number"
              min={0}
              value={draft.previous_failure_count}
              onChange={number("previous_failure_count")}
            />
          </div>
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="customer_age_days">Customer age (days)</label>
            <input
              id="customer_age_days"
              type="number"
              min={0}
              value={draft.customer_age_days}
              onChange={number("customer_age_days")}
            />
          </div>
          <div className="field">
            <label htmlFor="subscription_value">Subscription value (₹)</label>
            <input
              id="subscription_value"
              type="number"
              min={0}
              value={draft.subscription_value}
              onChange={number("subscription_value")}
            />
          </div>
        </div>
        <div className="field">
          <label htmlFor="retry_count">Retries already made</label>
          <input id="retry_count" type="number" min={0} value={draft.retry_count} onChange={number("retry_count")} />
          <span className="field-hint">
            At or above the configured cap the retry guardrail refuses another attempt, whatever
            the model scored.
          </span>
        </div>

        <button type="submit" disabled={busy}>
          {busy ? "Processing…" : "Ingest failure event"}
        </button>

        {error ? (
          <div className="callout bad section-gap" role="alert">
            <p>{error}</p>
          </div>
        ) : null}

        {result ? <IngestOutcome result={result} /> : null}
      </form>
    </>
  );
}

/**
 * What the pipeline decided, reported literally.
 *
 * A withheld action — the retry suppressed, stopped, or escalated to a person — is shown
 * as a warning rather than an error: refusing to act on a fraud decline or a capped retry
 * is the system working, not failing. A duplicate is called out because the idempotency
 * key deliberately returns the first decision instead of scoring the same attempt twice.
 */
function IngestOutcome({ result }: { result: ProcessedEvent }) {
  const withheld = isWithheld(result.action);
  return (
    <div className={`callout ${withheld ? "warn" : "good"} section-gap`}>
      <strong>
        Event {result.event_id} → {result.action}
        {result.duplicate ? " (duplicate — first decision replayed)" : ""}
      </strong>
      <p>{result.reason}</p>
      <p className="inline-note">
        Category <code>{result.failure_category}</code> · P(recovery){" "}
        <code>{formatScore(result.recovery_probability ?? null)}</code> · churn risk{" "}
        <code>{formatScore(result.churn_risk ?? null, 2)}</code> · revenue at risk{" "}
        <code>{formatCurrency(result.revenue_at_risk ?? null)}</code> · priority{" "}
        <code>{formatNumber(result.priority_score ?? null, 2)}</code> · model{" "}
        <code>{result.model_version ?? "—"}</code>
        {result.retry_delay_hours !== null ? (
          <>
            {" "}
            · retry in <code>{formatNumber(result.retry_delay_hours, 1)}h</code>
          </>
        ) : null}
      </p>
    </div>
  );
}
