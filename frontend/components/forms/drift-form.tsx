"use client";

import { useState } from "react";

import { Metric } from "@/components/ui";
import { apiPost, messageOf } from "@/lib/client";
import { formatNumber } from "@/lib/format";
import type { DriftResponse } from "@/lib/types";

/** The same two-bucket mixes the Streamlit build offers, so PSI values are comparable. */
const REFERENCES: readonly { label: string; build: () => string[] }[] = [
  { label: "Baseline (70% CARD / 30% UPI)", build: () => mix(70, 30) },
  { label: "Balanced (50% CARD / 50% UPI)", build: () => mix(50, 50) },
];

const CURRENTS: readonly { label: string; build: () => string[] }[] = [
  { label: "Shifted (20% CARD / 80% UPI)", build: () => mix(20, 80) },
  { label: "Baseline (70% CARD / 30% UPI)", build: () => mix(70, 30) },
];

function mix(card: number, upi: number): string[] {
  return [...Array<string>(card).fill("CARD"), ...Array<string>(upi).fill("UPI")];
}

const STATUS_TONE: Readonly<Record<string, "good" | "warn" | "bad">> = {
  STABLE: "good",
  MODERATE_DRIFT: "warn",
  SIGNIFICANT_DRIFT: "bad",
};

const STATUS_LABEL: Readonly<Record<string, string>> = {
  STABLE: "STABLE (PSI < 0.10)",
  MODERATE_DRIFT: "MODERATE DRIFT (0.10 ≤ PSI < 0.25)",
  SIGNIFICANT_DRIFT: "SIGNIFICANT DRIFT (PSI ≥ 0.25)",
};

/**
 * Population Stability Index between a training baseline and live inference.
 *
 * Drift is an alert, not a control input: a significant PSI does not change a single
 * financial decision. It tells a human that the model is being asked about a population
 * it was not trained on, and what to do about that is a human's call.
 */
export function DriftForm() {
  const [referenceIndex, setReferenceIndex] = useState(0);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DriftResponse | null>(null);

  async function calculate() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await apiPost<DriftResponse>("/drift", {
          reference: REFERENCES[referenceIndex]!.build(),
          current: CURRENTS[currentIndex]!.build(),
        }),
      );
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
          <label htmlFor="dr-reference">Reference distribution</label>
          <select
            id="dr-reference"
            value={referenceIndex}
            onChange={(change) => setReferenceIndex(Number(change.target.value))}
          >
            {REFERENCES.map((option, index) => (
              <option key={option.label} value={index}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="dr-current">Current inference distribution</label>
          <select
            id="dr-current"
            value={currentIndex}
            onChange={(change) => setCurrentIndex(Number(change.target.value))}
          >
            {CURRENTS.map((option, index) => (
              <option key={option.label} value={index}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <button type="button" onClick={calculate} disabled={busy}>
        {busy ? "Calculating…" : "Calculate population stability index"}
      </button>

      {error ? (
        <div className="callout bad section-gap" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      {result ? (
        <>
          <div className="grid grid-2 section-gap">
            <Metric label="PSI score" value={formatNumber(result.psi, 4)} />
            <Metric
              label="Drift status"
              value={STATUS_LABEL[result.status] ?? result.status}
              tone={STATUS_TONE[result.status] ?? "neutral"}
            />
          </div>
          <p className="inline-note">
            Drift is a monitoring signal only. It does not modify a financial decision, relax a
            guardrail, or retrain anything — retraining is a deliberate, reviewed step.
          </p>
        </>
      ) : null}
    </>
  );
}
