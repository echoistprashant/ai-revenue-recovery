"use client";

import { useState } from "react";

import { apiPost, messageOf } from "@/lib/client";
import {
  FAILURE_CATEGORIES,
  RECOVERY_ACTIONS,
  type CommunicationResponse,
  type FailureCategory,
  type RecoveryAction,
} from "@/lib/types";

/**
 * Copy generation for an action that was already approved.
 *
 * The action is an input to this form, not an output of it: the LLM is told what was
 * decided and asked only to word it. Choosing `STOP_RECOVERY` here does not stop
 * anything — it produces the message that a stopped case would receive.
 */
export function CommunicationForm() {
  const [action, setAction] = useState<RecoveryAction>("RETRY_NOW");
  const [category, setCategory] = useState<FailureCategory>("INSUFFICIENT_FUNDS");
  const [amount, setAmount] = useState(1499);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CommunicationResponse | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await apiPost<CommunicationResponse>("/communication", {
          action,
          failure_category: category,
          amount,
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
          <label htmlFor="cm-action">Approved financial action</label>
          <select
            id="cm-action"
            value={action}
            onChange={(change) => setAction(change.target.value as RecoveryAction)}
          >
            {RECOVERY_ACTIONS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <span className="field-hint">Chosen by the engine in production; selectable here to preview the copy.</span>
        </div>
        <div className="field">
          <label htmlFor="cm-category">Failure category</label>
          <select
            id="cm-category"
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
          <label htmlFor="cm-amount">Amount (₹)</label>
          <input
            id="cm-amount"
            type="number"
            min={1}
            step={1}
            value={amount}
            onChange={(change) => setAmount(Math.max(1, Number(change.target.value) || 1))}
          />
        </div>
      </div>
      <button type="submit" disabled={busy}>
        {busy ? "Generating…" : "Generate customer message"}
      </button>
      <span className="field-hint">
        Generates text only. No message is sent to anyone from this panel.
      </span>

      {error ? (
        <div className="callout bad section-gap" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      {result ? (
        <div className="callout section-gap">
          <strong>✉️ Generated customer communication</strong>
          <p className="wrap-text">{result.message}</p>
          <p className="inline-note">
            Written for the verified action <code>{result.action}</code> — the backend echoes back
            the action it generated copy for, so a mismatch would be visible here.
          </p>
        </div>
      ) : null}
    </form>
  );
}
