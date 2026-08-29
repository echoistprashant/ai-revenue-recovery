"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiPost, messageOf } from "@/lib/client";
import type { CaseResolution, ResolveCaseResponse } from "@/lib/types";

const OPTIONS: readonly { value: CaseResolution; label: string; caption: string }[] = [
  {
    value: "MANUAL_RETRY",
    label: "Manual retry",
    caption: "Re-submit to the decision engine, which may still withhold it.",
  },
  {
    value: "MANUAL_RECOVERED",
    label: "Manually recovered",
    caption: "The customer paid through another channel — record it as recovered.",
  },
  { value: "WRITTEN_OFF", label: "Written off", caption: "Give up on this case and close it." },
];

/**
 * The reviewer's decision form.
 *
 * `MANUAL_RETRY` does not retry anything on the reviewer's authority: the backend
 * re-runs the deterministic engine, which still refuses a fraud decline, a capped
 * retry, or a suppressed route. The outcome below reports `executed` honestly, so a
 * withheld retry is never presented as a recovery.
 */
export function ResolveCaseForm({ eventId }: { eventId: number }) {
  const router = useRouter();
  const [resolution, setResolution] = useState<CaseResolution>("MANUAL_RETRY");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<ResolveCaseResponse | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setOutcome(null);
    try {
      const result = await apiPost<ResolveCaseResponse>(`/review-queue/${eventId}/resolve`, {
        resolution,
        note,
      });
      setOutcome(result);
      // The case leaves the queue on success, so the server-rendered list is stale.
      router.refresh();
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <fieldset style={{ border: "none", padding: 0, margin: "0 0 12px" }}>
        <legend className="field-hint" style={{ marginBottom: "6px" }}>
          Resolution
        </legend>
        {OPTIONS.map((option) => (
          <label
            key={option.value}
            style={{ display: "flex", gap: "8px", alignItems: "flex-start", marginBottom: "6px" }}
          >
            <input
              type="radio"
              name="resolution"
              value={option.value}
              checked={resolution === option.value}
              onChange={() => setResolution(option.value)}
              style={{ width: "auto", marginTop: "4px" }}
            />
            <span>
              <strong style={{ fontSize: "0.85rem" }}>{option.label}</strong>
              <br />
              <span className="field-hint">{option.caption}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <div className="field">
        <label htmlFor={`note-${eventId}`}>Reviewer note (recorded in the audit log)</label>
        <textarea
          id={`note-${eventId}`}
          maxLength={500}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Why this decision was made."
        />
        <span className="field-hint">{note.length}/500 characters.</span>
      </div>

      <button type="submit" disabled={busy}>
        {busy ? "Resolving…" : "Resolve case"}
      </button>

      {error ? (
        <div className="callout bad section-gap" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      {outcome ? (
        <div className={`callout ${outcome.executed ? "good" : "warn"} section-gap`}>
          <strong>
            {outcome.executed ? "Action executed" : "Withheld by the decision engine"}
          </strong>
          <p>{outcome.detail}</p>
          <p className="inline-note">
            Final state <code>{outcome.final_state}</code> · recovered{" "}
            <code>{String(outcome.recovered)}</code> · executed{" "}
            <code>{String(outcome.executed)}</code> · resolved by{" "}
            <code>{outcome.resolved_by}</code> at <code>{outcome.resolved_at}</code>
          </p>
        </div>
      ) : null}
    </form>
  );
}
