import { EmptyState } from "@/components/ui";
import { formatTimestamp } from "@/lib/format";
import type { AuditEntry } from "@/lib/types";

/**
 * The per-event audit trail.
 *
 * Rendered verbatim from the backend rows — what was classified, what the model scored,
 * which guardrail fired, what the worker did — because the point of an audit trail is
 * that it is not summarised.
 */
export function AuditTrail({ entries }: { entries: AuditEntry[] }) {
  if (entries.length === 0) {
    return <EmptyState>No audit entries recorded for this event.</EmptyState>;
  }
  return (
    <div className="stack">
      {entries.map((entry) => (
        <details key={entry.audit_id}>
          <summary>
            {formatTimestamp(entry.created_at)} — <code>{entry.event_type}</code>{" "}
            <span style={{ color: "var(--text-faint)" }}>(audit #{entry.audit_id})</span>
          </summary>
          <pre>{JSON.stringify(entry.details, null, 2)}</pre>
        </details>
      ))}
    </div>
  );
}
