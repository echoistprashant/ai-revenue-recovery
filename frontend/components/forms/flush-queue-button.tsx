"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { apiPost, messageOf } from "@/lib/client";
import { formatNumber } from "@/lib/format";

interface FlushResult {
  claimed: number;
  executed: number;
  withheld: number;
  failed: number;
  requeued: number;
}

/**
 * Drain due background work once.
 *
 * The worker process does this on a loop; the button exists so a single-process
 * deployment can flush the queue on demand. It grants no new authority: each task is
 * re-checked by the decision engine as it is claimed, which is why `withheld` is a
 * normal outcome rather than a failure.
 */
export function FlushQueueButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FlushResult | null>(null);

  async function flush() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await apiPost<FlushResult>("/tasks/run-due"));
      router.refresh();
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" onClick={flush} disabled={busy} className="secondary">
        {busy ? "Draining…" : "Flush due background work"}
      </button>

      {error ? (
        <div className="callout bad section-gap" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      {result ? (
        <div className={`callout ${result.failed > 0 ? "warn" : "good"} section-gap`}>
          <strong>{result.claimed === 0 ? "Nothing was due" : `Drained ${result.claimed} task(s)`}</strong>
          <p className="inline-note">
            executed <code>{formatNumber(result.executed, 0)}</code> · withheld by the engine{" "}
            <code>{formatNumber(result.withheld, 0)}</code> · failed{" "}
            <code>{formatNumber(result.failed, 0)}</code> · requeued{" "}
            <code>{formatNumber(result.requeued, 0)}</code>
          </p>
        </div>
      ) : null}
    </>
  );
}
