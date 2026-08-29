"use client";

import { useState } from "react";

import { apiPost, messageOf } from "@/lib/client";
import type { AnalystResponse } from "@/lib/types";

const QUICK_PROMPTS: readonly { label: string; question: string }[] = [
  { label: "📊 Overall recovery rate?", question: "what is the recovery rate?" },
  { label: "⚠️ Common failures?", question: "what is the failure breakdown?" },
  { label: "🎯 Top priority cases?", question: "show top 5 priority cases" },
  { label: "🏦 Gateway status?", question: "what is the gateway health status?" },
];

/**
 * The analyst question box.
 *
 * A quick prompt fills the field and asks in one step, because that is what the button
 * is for. The answer is whatever the backend returned: it is grounded in read-only tool
 * results, and a question the tools cannot answer is declined rather than guessed at.
 */
export function AnalystForm() {
  const [question, setQuestion] = useState("What is our current recovery rate and recovered revenue?");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [asked, setAsked] = useState<string | null>(null);

  async function ask(text: string) {
    const trimmed = text.trim();
    if (!trimmed) {
      setError("Type a question first.");
      return;
    }
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      const result = await apiPost<AnalystResponse>("/analyst", { question: trimmed.slice(0, 1000) });
      setAnswer(result.answer);
      setAsked(trimmed);
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="actions">
        {QUICK_PROMPTS.map((prompt) => (
          <button
            key={prompt.label}
            type="button"
            className="secondary"
            disabled={busy}
            onClick={() => {
              setQuestion(prompt.question);
              void ask(prompt.question);
            }}
          >
            {prompt.label}
          </button>
        ))}
      </div>

      <form
        className="section-gap"
        onSubmit={(event) => {
          event.preventDefault();
          void ask(question);
        }}
      >
        <div className="field">
          <label htmlFor="an-question">Ask a business question</label>
          <input
            id="an-question"
            value={question}
            maxLength={1000}
            onChange={(change) => setQuestion(change.target.value)}
          />
          <span className="field-hint">{question.length}/1000 characters.</span>
        </div>
        <button type="submit" disabled={busy}>
          {busy ? "Running read-only tools…" : "Ask analyst"}
        </button>
      </form>

      {error ? (
        <div className="callout bad section-gap" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      {answer ? (
        <div className="callout good section-gap">
          <strong>💬 Grounded answer</strong>
          <p className="wrap-text">{answer}</p>
          {asked ? <p className="inline-note">In answer to: {asked}</p> : null}
        </div>
      ) : null}
    </>
  );
}
