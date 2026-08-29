"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { messageOf, postLocal } from "@/lib/client";
import { isWithheld, type ProcessedEvent } from "@/lib/types";

const EVENTS = ["payment.failed", "subscription.halted", "payment.authorized"] as const;

const ERROR_CODES = [
  "BAD_REQUEST_PAYMENT_ACCOUNT_INSUFFICIENT_BALANCE",
  "BAD_REQUEST_PAYMENT_CARD_EXPIRED",
  "BAD_REQUEST_PAYMENT_CARD_INVALID",
  "BAD_REQUEST_PAYMENT_AUTHENTICATION_FAILED",
  "GATEWAY_ERROR",
  "FRAUD_RISK_DECLINE",
  "BAD_REQUEST_PAYMENT_DECLINED_BY_BANK",
] as const;

/** Razorpay's own envelope, built exactly as the adapter expects to receive it. */
function buildPayload(event: string, errorCode: string, amountPaise: number, paymentId: string) {
  const createdAt = Math.floor(Date.now() / 1000);
  return {
    entity: "event",
    account_id: "acc_sim_rzp_01",
    event,
    contains: ["payment"],
    payload: {
      payment: {
        entity: {
          id: paymentId,
          entity: "payment",
          amount: amountPaise,
          currency: "INR",
          status: "failed",
          method: "card",
          bank: "HDFC",
          error_code: errorCode,
          notes: {
            customer_id: "cust_rzp_web_1",
            subscription_id: "sub_rzp_web_1",
            attempt_id: "att_1",
            previous_success_count: 4,
            previous_failure_count: 1,
            customer_age_days: 150,
            subscription_value: amountPaise / 100,
            retry_count: 0,
          },
          created_at: createdAt,
        },
      },
    },
    created_at: createdAt,
  };
}

/**
 * The signed-webhook simulator.
 *
 * Unlike the Streamlit build, there is no secret field here. The payload is assembled in
 * the browser and signed by `/api/webhooks/razorpay` on the server, so the HMAC key
 * never leaves it. That route also requires an `OPERATOR` session, because the backend
 * endpoint trusts the signature alone.
 */
export function WebhookSimulator() {
  const router = useRouter();
  const [event, setEvent] = useState<string>(EVENTS[0]);
  const [errorCode, setErrorCode] = useState<string>(ERROR_CODES[0]);
  const [amountPaise, setAmountPaise] = useState(249900);
  const [paymentId, setPaymentId] = useState("pay_rzp_live_001");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProcessedEvent | null>(null);

  const payload = buildPayload(event, errorCode, amountPaise, paymentId);

  async function transmit() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await postLocal<ProcessedEvent>("/api/webhooks/razorpay", payload));
      router.refresh();
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="form-row">
        <div className="field">
          <label htmlFor="wh-event">Razorpay event</label>
          <select id="wh-event" value={event} onChange={(change) => setEvent(change.target.value)}>
            {EVENTS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="wh-code">Razorpay error code</label>
          <select id="wh-code" value={errorCode} onChange={(change) => setErrorCode(change.target.value)}>
            {ERROR_CODES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="form-row">
        <div className="field">
          <label htmlFor="wh-amount">Amount (paise)</label>
          <input
            id="wh-amount"
            type="number"
            min={100}
            step={100}
            value={amountPaise}
            onChange={(change) => setAmountPaise(Math.max(100, Number(change.target.value) || 100))}
          />
          <span className="field-hint">
            Razorpay sends minor units; the adapter divides by 100. {amountPaise} paise = ₹
            {(amountPaise / 100).toFixed(2)}.
          </span>
        </div>
        <div className="field">
          <label htmlFor="wh-pid">Payment ID</label>
          <input id="wh-pid" value={paymentId} onChange={(change) => setPaymentId(change.target.value)} />
          <span className="field-hint">
            Re-sending the same ID is treated as a duplicate and replays the first decision.
          </span>
        </div>
      </div>

      <details className="section-gap">
        <summary>Raw webhook JSON that will be signed and transmitted</summary>
        <pre>{JSON.stringify(payload, null, 2)}</pre>
      </details>

      <button type="button" onClick={transmit} disabled={busy} className="section-gap">
        {busy ? "Signing and transmitting…" : "Transmit signed webhook"}
      </button>

      {error ? (
        <div className="callout bad section-gap" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      {result ? (
        <div className={`callout ${isWithheld(result.action) ? "warn" : "good"} section-gap`}>
          <strong>
            Signature verified · event {result.event_id} → {result.action}
          </strong>
          <p>{result.reason}</p>
          <p className="inline-note">
            Normalised category <code>{result.failure_category}</code>
            {result.duplicate ? " · duplicate, first decision replayed" : ""}
          </p>
        </div>
      ) : null}
    </>
  );
}
