import sqlite3

from revenue_recovery.baseline import select_baseline_action, simulate_outcome
from revenue_recovery.classification import classify_failure
from revenue_recovery.config import Settings
from revenue_recovery.database import Database
from revenue_recovery.models import BaselineAction, PaymentEventCreate, ProcessedEvent, RecoveryMetrics


class UnsupportedFailureCodeError(ValueError):
    pass


class PaymentRecoveryService:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings
        self.database.initialize()

    def process_event(self, event: PaymentEventCreate) -> ProcessedEvent:
        try:
            category = classify_failure(event.failure_code)
        except ValueError as exc:
            raise UnsupportedFailureCodeError(str(exc)) from exc

        decision = select_baseline_action(category, event.retry_count, self.settings.retry_delays_hours)
        recovered = (
            simulate_outcome(category, event.payment_id, event.retry_count)
            if decision.action is BaselineAction.RETRY_LATER
            else None
        )

        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT event_id FROM payment_events WHERE payment_id = ? AND attempt_id = ?",
                (event.payment_id, event.attempt_id),
            ).fetchone()
            if existing:
                return self._load_processed(connection, existing["event_id"], duplicate=True)

            cursor = connection.execute(
                """INSERT INTO payment_events (
                    payment_id, attempt_id, customer_id, subscription_id, amount, currency,
                    payment_method, gateway, bank, failure_code, failure_category,
                    event_timestamp, previous_success_count, previous_failure_count,
                    customer_age_days, subscription_value, retry_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.payment_id, event.attempt_id, event.customer_id, event.subscription_id,
                    event.amount, event.currency, event.payment_method.value, event.gateway,
                    event.bank, event.failure_code, category.value, event.timestamp.isoformat(),
                    event.previous_success_count, event.previous_failure_count,
                    event.customer_age_days, event.subscription_value, event.retry_count,
                ),
            )
            event_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO decisions (event_id, action, retry_delay_hours, reason) VALUES (?, ?, ?, ?)",
                (event_id, decision.action.value, decision.retry_delay_hours, decision.reason),
            )
            if recovered is None:
                final_state = "STOPPED"
                recovered_amount = 0.0
            elif recovered:
                final_state = "RECOVERED"
                recovered_amount = event.amount
            else:
                final_state = "UNRESOLVED"
                recovered_amount = 0.0
            connection.execute(
                "INSERT INTO outcomes (event_id, recovered, recovered_amount, final_state) VALUES (?, ?, ?, ?)",
                (event_id, None if recovered is None else int(recovered), recovered_amount, final_state),
            )
            self.database.audit(connection, event_id, "EVENT_PROCESSED", {
                "failure_category": category.value,
                "action": decision.action.value,
                "reason": decision.reason,
                "final_state": final_state,
            })
            return ProcessedEvent(
                event_id=event_id,
                payment_id=event.payment_id,
                attempt_id=event.attempt_id,
                failure_category=category,
                action=decision.action,
                retry_delay_hours=decision.retry_delay_hours,
                reason=decision.reason,
                recovered=recovered,
            )

    def _load_processed(self, connection: sqlite3.Connection, event_id: int, duplicate: bool) -> ProcessedEvent:
        row = connection.execute(
            """SELECT e.event_id, e.payment_id, e.attempt_id, e.failure_category,
                      d.action, d.retry_delay_hours, d.reason, o.recovered
               FROM payment_events e
               JOIN decisions d ON d.event_id = e.event_id
               JOIN outcomes o ON o.event_id = e.event_id
               WHERE e.event_id = ?""",
            (event_id,),
        ).fetchone()
        return ProcessedEvent(
            event_id=row["event_id"], payment_id=row["payment_id"], attempt_id=row["attempt_id"],
            failure_category=row["failure_category"], action=row["action"],
            retry_delay_hours=row["retry_delay_hours"], reason=row["reason"],
            recovered=None if row["recovered"] is None else bool(row["recovered"]), duplicate=duplicate,
        )

    def get_metrics(self) -> RecoveryMetrics:
        with self.database.connect() as connection:
            summary = connection.execute(
                """SELECT COUNT(*) total, COUNT(o.recovered) resolved,
                          COALESCE(SUM(CASE WHEN o.recovered = 1 THEN 1 ELSE 0 END), 0) recovered,
                          COALESCE(SUM(o.recovered_amount), 0) revenue
                   FROM payment_events e JOIN outcomes o ON o.event_id = e.event_id"""
            ).fetchone()
            breakdown_rows = connection.execute(
                "SELECT failure_category, COUNT(*) count FROM payment_events GROUP BY failure_category"
            ).fetchall()
        resolved = summary["resolved"]
        recovered = summary["recovered"]
        return RecoveryMetrics(
            total_failures=summary["total"], resolved_events=resolved, recovered_events=recovered,
            unresolved_events=summary["total"] - recovered,
            recovery_rate=round(recovered / resolved, 4) if resolved else 0.0,
            recovered_revenue=round(summary["revenue"], 2),
            failure_breakdown={row["failure_category"]: row["count"] for row in breakdown_rows},
        )
