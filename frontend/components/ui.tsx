/**
 * Presentational primitives shared by every module.
 *
 * None of these are client components: they render on the server and ship no
 * JavaScript. Interactivity lives in the small number of `"use client"` forms under
 * `components/forms/`.
 */

import type { ReactNode } from "react";

import { barWidth, humanizeEnum, toneForAction } from "@/lib/format";

export type Tone = "good" | "warn" | "bad" | "neutral";

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header>
      <h1 className="page-title">{title}</h1>
      {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
    </header>
  );
}

export function Card({
  title,
  hint,
  children,
}: {
  title?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section className="card">
      {title ? <h2 className="card-title">{title}</h2> : null}
      {hint ? <p className="card-hint">{hint}</p> : null}
      {children}
    </section>
  );
}

export function Metric({
  label,
  value,
  note,
  tone = "neutral",
}: {
  label: string;
  value: string;
  note?: string;
  tone?: Tone;
}) {
  return (
    <div className={`metric tone-${tone}`}>
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
      {note ? <p className="metric-note">{note}</p> : null}
    </div>
  );
}

/**
 * A status pill. The tone is derived from the value unless one is given, and an
 * unrecognised value renders neutral rather than borrowing a colour that would imply
 * an outcome the backend did not report.
 */
export function Badge({ value, tone }: { value: string | null | undefined; tone?: Tone }) {
  if (!value) {
    return <span className="badge">—</span>;
  }
  const resolved = tone ?? toneForAction(value);
  return <span className={`badge ${resolved}`}>{humanizeEnum(value)}</span>;
}

export function Callout({
  tone = "neutral",
  title,
  children,
}: {
  tone?: Tone;
  title?: string;
  children: ReactNode;
}) {
  return (
    <div className={`callout ${tone}`} role={tone === "bad" ? "alert" : undefined}>
      {title ? <strong>{title}</strong> : null}
      <p>{children}</p>
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <Callout tone="bad" title="This panel could not load">
      {message}
    </Callout>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="empty-state">{children}</p>;
}

export interface BarItem {
  label: string;
  value: number;
  display?: string;
}

/** A horizontal bar list, scaled to the largest value. No chart dependency. */
export function BarList({ items }: { items: BarItem[] }) {
  if (items.length === 0) {
    return <EmptyState>No data to plot yet.</EmptyState>;
  }
  const maximum = Math.max(...items.map((item) => item.value));
  return (
    <div className="bars">
      {items.map((item) => (
        <div className="bar-row" key={item.label}>
          <span className="bar-label" title={item.label}>
            {item.label}
          </span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: barWidth(item.value, maximum) }} />
          </span>
          <span className="bar-value">{item.display ?? item.value}</span>
        </div>
      ))}
    </div>
  );
}

export function TableWrap({ children }: { children: ReactNode }) {
  return <div className="table-wrap">{children}</div>;
}

/** A definition list for single-record detail views. */
export function KeyValues({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <TableWrap>
      <table>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <th scope="row" style={{ width: "220px", textAlign: "left" }}>
                {label}
              </th>
              <td>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

/**
 * Shown on every page. Synthetic figures must never be read as commercial results, and
 * the only reliable way to ensure that is to say so where the numbers are.
 */
export function SyntheticDisclaimer() {
  return (
    <Callout tone="warn" title="Synthetic data">
      Metrics, predictions, and actions shown here come from a reproducible synthetic
      payment simulator. They are for demonstration and engineering evaluation only, not
      commercial financial performance.
    </Callout>
  );
}

/** The LLM boundary, stated where a reader might otherwise assume otherwise. */
export function SafetyCallout() {
  return (
    <Callout tone="bad" title="The LLM is not a financial decision maker">
      Retries, method changes, suppressions, and escalations are chosen by the
      deterministic decision engine and gated by the guardrails — fraud hard stop,
      retry cap, high-value review, contact cooldown, and incident suppression. The LLM
      only writes customer-facing copy for an action that was already approved, or
      answers analytics questions through read-only tools.
    </Callout>
  );
}

const PIPELINE: readonly { title: string; detail: string }[] = [
  { title: "1. Ingestion", detail: "Webhooks & normalization" },
  { title: "2. Classification", detail: "Nine failure rules" },
  { title: "3. ML & signals", detail: "P(recovery), churn, value" },
  { title: "4. Guardrails", detail: "Fraud, cap, value, incident" },
  { title: "5. Decision engine", detail: "Deterministic action" },
  { title: "6. Action & LLM", detail: "Simulated execution & message" },
];

/** The PREDICT → DECIDE → ACT loop, with the current stage highlighted. */
export function PipelineFlow({ activeStep }: { activeStep: number }) {
  return (
    <ol className="pipeline" aria-label="Decision pipeline">
      {PIPELINE.map((step, index) => (
        <li key={step.title} className={index === activeStep ? "pipeline-step active" : "pipeline-step"}>
          <span className="step-title">{step.title}</span>
          <span className="step-detail">{step.detail}</span>
        </li>
      ))}
    </ol>
  );
}
