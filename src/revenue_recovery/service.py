from dataclasses import dataclass
from datetime import timedelta

from revenue_recovery.actions import ActionContext, ActionExecutor
from revenue_recovery.classification import classify_failure
from revenue_recovery.clock import iso_now, to_iso, utc_now
from revenue_recovery.config import QUEUED, Settings
from revenue_recovery.database import Database, DatabaseConnection
from revenue_recovery.decision_engine import DecisionContext, DecisionEngine
from revenue_recovery.guardrails import evaluate_guardrails
from revenue_recovery.models import EventHistoryItem, FailureCategory, PaymentEventCreate, PriorityCase, ProcessedEvent, RecoveryAction, RecoveryMetrics
from revenue_recovery.scoring import RecoveryScorer, ScoreResult
from revenue_recovery.tasks import TaskQueue, TaskType
from revenue_recovery.worker import RecoveryWorker

RETRY_ACTIONS = {RecoveryAction.RETRY_NOW, RecoveryAction.RETRY_LATER}

# Outcome state for actions that have no executable side effect. These describe what
# the case is waiting on, which is what the review queue and audit UI read.
FINAL_STATE_BY_ACTION = {
    RecoveryAction.STOP_RECOVERY: "STOPPED",
    RecoveryAction.SUPPRESS_RETRY: "SUPPRESSED",
    RecoveryAction.ESCALATE_TO_HUMAN: "ESCALATED",
    RecoveryAction.CHANGE_PAYMENT_METHOD: "AWAITING_METHOD_UPDATE",
}


class UnsupportedFailureCodeError(ValueError):
    pass


@dataclass(frozen=True)
class Dispatch:
    recovered: bool | None
    final_state: str
    recovered_amount: float
    task_id: int | None
    detail: str


class PaymentRecoveryService:
    def __init__(self, database: Database, settings: Settings, action_executor: ActionExecutor | None = None):
        self.database = database
        self.settings = settings
        self.database.initialize()
        self.scorer = RecoveryScorer(settings.recovery_model_path) if settings.recovery_model_path.exists() else None
        self.decision_engine = DecisionEngine()
        self.action_executor = action_executor or ActionExecutor(self.decision_engine)
        self.task_queue = TaskQueue(
            max_attempts=settings.task_max_attempts,
            backoff_seconds=settings.task_retry_backoff_seconds,
        )
        self.worker = RecoveryWorker(database, settings, self.action_executor, self.task_queue)

    @property
    def queued_execution(self) -> bool:
        return self.settings.task_execution_mode == QUEUED

    def process_event(self, event: PaymentEventCreate) -> ProcessedEvent:
        try:
            category = classify_failure(event.failure_code)
        except ValueError as exc:
            raise UnsupportedFailureCodeError(str(exc)) from exc

        preliminary_guardrail = evaluate_guardrails(category, event.amount, event.retry_count, False, None)
        score = None
        if preliminary_guardrail.allowed and self.scorer:
            score = self.scorer.score(event, category, self.settings.assumed_remaining_months)
        decision = self.decision_engine.decide(DecisionContext(
            category=category,
            amount=event.amount,
            retry_count=event.retry_count,
            recovery_probability=score.recovery_probability if score else 0.0,
        ))
        action = RecoveryAction(decision.action)
        retry_delay_hours = self.settings.retry_delays_hours[min(event.retry_count, len(self.settings.retry_delays_hours) - 1)] if action is RecoveryAction.RETRY_LATER else None

        with self.database.connect() as connection:
            existing = connection.fetch_one(
                "SELECT event_id FROM payment_events WHERE payment_id = :payment_id AND attempt_id = :attempt_id",
                {"payment_id": event.payment_id, "attempt_id": event.attempt_id},
            )
            if existing:
                return self._load_processed(connection, int(existing["event_id"]), duplicate=True)

            created_at = iso_now()
            event_id = connection.insert_returning_id(
                """INSERT INTO payment_events (
                    payment_id, attempt_id, customer_id, subscription_id, amount, currency,
                    payment_method, gateway, bank, failure_code, failure_category,
                    event_timestamp, previous_success_count, previous_failure_count,
                    customer_age_days, subscription_value, retry_count, created_at
                ) VALUES (
                    :payment_id, :attempt_id, :customer_id, :subscription_id, :amount, :currency,
                    :payment_method, :gateway, :bank, :failure_code, :failure_category,
                    :event_timestamp, :previous_success_count, :previous_failure_count,
                    :customer_age_days, :subscription_value, :retry_count, :created_at
                )""",
                {
                    "payment_id": event.payment_id, "attempt_id": event.attempt_id,
                    "customer_id": event.customer_id, "subscription_id": event.subscription_id,
                    "amount": event.amount, "currency": event.currency,
                    "payment_method": event.payment_method.value, "gateway": event.gateway,
                    "bank": event.bank, "failure_code": event.failure_code,
                    "failure_category": category.value, "event_timestamp": to_iso(event.timestamp),
                    "previous_success_count": event.previous_success_count,
                    "previous_failure_count": event.previous_failure_count,
                    "customer_age_days": event.customer_age_days,
                    "subscription_value": event.subscription_value,
                    "retry_count": event.retry_count, "created_at": created_at,
                },
                "event_id",
            )
            connection.execute(
                """INSERT INTO decisions (event_id, action, retry_delay_hours, reason, created_at)
                   VALUES (:event_id, :action, :retry_delay_hours, :reason, :created_at)""",
                {
                    "event_id": event_id, "action": action.value,
                    "retry_delay_hours": retry_delay_hours, "reason": decision.reason,
                    "created_at": created_at,
                },
            )
            if score:
                self._insert_score(connection, event_id, score, created_at)
            dispatch = self._dispatch_action(connection, event_id, event, category, action, retry_delay_hours, score)
            connection.execute(
                """INSERT INTO outcomes (event_id, recovered, recovered_amount, final_state, created_at)
                   VALUES (:event_id, :recovered, :recovered_amount, :final_state, :created_at)""",
                {
                    "event_id": event_id,
                    "recovered": None if dispatch.recovered is None else int(dispatch.recovered),
                    "recovered_amount": dispatch.recovered_amount,
                    "final_state": dispatch.final_state,
                    "created_at": created_at,
                },
            )
            self.database.audit(connection, event_id, "EVENT_PROCESSED", {
                "failure_category": category.value,
                "action": action.value,
                "reason": decision.reason,
                "guardrail_rule": decision.guardrail.rule,
                "final_state": dispatch.final_state,
                "execution_detail": dispatch.detail,
                "task_id": dispatch.task_id,
                "recovery_probability": score.recovery_probability if score else None,
                "churn_risk": score.churn_risk if score else None,
                "revenue_at_risk": score.revenue_at_risk if score else None,
                "priority_score": score.priority_score if score else None,
                "model_version": score.model_version if score else None,
            })
            return ProcessedEvent(
                event_id=event_id,
                payment_id=event.payment_id,
                attempt_id=event.attempt_id,
                failure_category=category,
                action=action,
                retry_delay_hours=retry_delay_hours,
                reason=decision.reason,
                recovered=dispatch.recovered,
                recovery_probability=score.recovery_probability if score else None,
                churn_risk=score.churn_risk if score else None,
                revenue_at_risk=score.revenue_at_risk if score else None,
                priority_score=score.priority_score if score else None,
                model_version=score.model_version if score else None,
            )

    def _insert_score(self, connection: DatabaseConnection, event_id: int, score: ScoreResult, created_at: str) -> None:
        connection.execute(
            """INSERT INTO scores (
                   event_id, recovery_probability, churn_risk, revenue_at_risk,
                   priority_score, model_version, created_at
               ) VALUES (
                   :event_id, :recovery_probability, :churn_risk, :revenue_at_risk,
                   :priority_score, :model_version, :created_at
               )""",
            {
                "event_id": event_id,
                "recovery_probability": score.recovery_probability,
                "churn_risk": score.churn_risk,
                "revenue_at_risk": score.revenue_at_risk,
                "priority_score": score.priority_score,
                "model_version": score.model_version,
                "created_at": created_at,
            },
        )

    def _dispatch_action(
        self,
        connection: DatabaseConnection,
        event_id: int,
        event: PaymentEventCreate,
        category: FailureCategory,
        action: RecoveryAction,
        retry_delay_hours: int | None,
        score: ScoreResult | None,
    ) -> Dispatch:
        """Queue the approved action, and in inline mode execute it immediately.

        Both modes share one execution path, so queued runs produce the same outcome
        as inline runs for the same event. Inline stays the default because the
        synthetic batches and the recorded baseline numbers depend on it.
        """
        if action not in RETRY_ACTIONS and action is not RecoveryAction.SEND_NOTIFICATION:
            return Dispatch(None, FINAL_STATE_BY_ACTION[action], 0.0, None, "This action has no executable side effect.")

        task_type = TaskType.EXECUTE_RETRY if action in RETRY_ACTIONS else TaskType.SEND_NOTIFICATION
        run_at = to_iso(utc_now() + timedelta(hours=retry_delay_hours or 0))
        task_id = self.task_queue.enqueue(
            connection, event_id, task_type, {"approved_action": action.value}, run_at=run_at
        )
        if self.queued_execution:
            waiting = "SCHEDULED" if task_type is TaskType.EXECUTE_RETRY else "AWAITING_CUSTOMER"
            return Dispatch(None, waiting, 0.0, task_id, f"{task_type.value} queued for background execution at {run_at}.")

        context = ActionContext(
            event_id=event_id,
            payment_id=event.payment_id,
            category=category,
            amount=event.amount,
            retry_count=event.retry_count,
            recovery_probability=score.recovery_probability if score else 0.0,
        )
        result = self.action_executor.execute(task_type, context)
        if task_id is not None:
            self.task_queue.mark_done(connection, task_id)
        final_state = result.final_state or ("AWAITING_CUSTOMER" if result.executed else "WITHHELD")
        return Dispatch(
            result.recovered,
            final_state,
            event.amount if result.recovered else 0.0,
            task_id,
            result.detail,
        )

    def _load_processed(self, connection: DatabaseConnection, event_id: int, duplicate: bool) -> ProcessedEvent:
        row = connection.fetch_one(
            """SELECT e.event_id, e.payment_id, e.attempt_id, e.failure_category,
                      d.action, d.retry_delay_hours, d.reason, o.recovered,
                      s.recovery_probability, s.churn_risk, s.revenue_at_risk,
                      s.priority_score, s.model_version
               FROM payment_events e
               JOIN decisions d ON d.event_id = e.event_id
               JOIN outcomes o ON o.event_id = e.event_id
               LEFT JOIN scores s ON s.event_id = e.event_id
               WHERE e.event_id = :event_id""",
            {"event_id": event_id},
        )
        if row is None:
            raise LookupError(f"Event {event_id} has no decision or outcome record")
        return ProcessedEvent(
            event_id=row["event_id"], payment_id=row["payment_id"], attempt_id=row["attempt_id"],
            failure_category=row["failure_category"], action=RecoveryAction(row["action"]),
            retry_delay_hours=row["retry_delay_hours"], reason=row["reason"],
            recovered=None if row["recovered"] is None else bool(row["recovered"]), duplicate=duplicate,
            recovery_probability=row["recovery_probability"], churn_risk=row["churn_risk"],
            revenue_at_risk=row["revenue_at_risk"], priority_score=row["priority_score"],
            model_version=row["model_version"],
        )

    def get_metrics(self) -> RecoveryMetrics:
        with self.database.connect() as connection:
            summary = connection.fetch_one(
                """SELECT COUNT(*) AS total, COUNT(o.recovered) AS resolved,
                          COALESCE(SUM(CASE WHEN o.recovered = 1 THEN 1 ELSE 0 END), 0) AS recovered,
                          COALESCE(SUM(o.recovered_amount), 0) AS revenue
                   FROM payment_events e JOIN outcomes o ON o.event_id = e.event_id"""
            )
            breakdown_rows = connection.fetch_all(
                "SELECT failure_category, COUNT(*) AS count FROM payment_events GROUP BY failure_category"
            )
        resolved = int(summary["resolved"]) if summary else 0
        recovered = int(summary["recovered"]) if summary else 0
        total = int(summary["total"]) if summary else 0
        return RecoveryMetrics(
            total_failures=total, resolved_events=resolved, recovered_events=recovered,
            unresolved_events=total - recovered,
            recovery_rate=round(recovered / resolved, 4) if resolved else 0.0,
            recovered_revenue=round(float(summary["revenue"]) if summary else 0.0, 2),
            failure_breakdown={str(row["failure_category"]): int(row["count"]) for row in breakdown_rows},
        )

    def get_top_priority_cases(self, limit: int = 10) -> list[PriorityCase]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        with self.database.connect() as connection:
            rows = connection.fetch_all(
                """SELECT e.payment_id, e.attempt_id, e.failure_category, e.amount,
                          s.recovery_probability, s.churn_risk, s.revenue_at_risk,
                          s.priority_score, s.model_version
                   FROM scores s JOIN payment_events e ON e.event_id = s.event_id
                   ORDER BY s.priority_score DESC, e.event_id ASC LIMIT :limit""",
                {"limit": limit},
            )
        return [PriorityCase(**dict(row)) for row in rows]

    def get_history(self, limit: int = 50) -> list[EventHistoryItem]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self.database.connect() as connection:
            rows = connection.fetch_all(
                """SELECT e.event_id, e.payment_id, e.attempt_id, e.customer_id, e.amount,
                          e.currency, e.payment_method, e.gateway, e.bank, e.failure_category,
                          e.event_timestamp, d.action, d.reason, o.final_state, o.recovered,
                          s.recovery_probability, s.churn_risk, s.revenue_at_risk,
                          s.priority_score, e.created_at
                   FROM payment_events e
                   JOIN decisions d ON d.event_id = e.event_id
                   JOIN outcomes o ON o.event_id = e.event_id
                   LEFT JOIN scores s ON s.event_id = e.event_id
                   ORDER BY e.event_id DESC LIMIT :limit""",
                {"limit": limit},
            )
        return [
            EventHistoryItem(
                event_id=row["event_id"],
                payment_id=row["payment_id"],
                attempt_id=row["attempt_id"],
                customer_id=row["customer_id"],
                amount=row["amount"],
                currency=row["currency"],
                payment_method=row["payment_method"],
                gateway=row["gateway"],
                bank=row["bank"],
                failure_category=FailureCategory(row["failure_category"]),
                event_timestamp=str(row["event_timestamp"]),
                action=RecoveryAction(row["action"]),
                reason=row["reason"],
                final_state=row["final_state"],
                recovered=None if row["recovered"] is None else bool(row["recovered"]),
                recovery_probability=row["recovery_probability"],
                churn_risk=row["churn_risk"],
                revenue_at_risk=row["revenue_at_risk"],
                priority_score=row["priority_score"],
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def get_task_stats(self) -> dict[str, int | str]:
        with self.database.connect() as connection:
            stats = self.task_queue.stats(connection)
            stats["due_now"] = self.task_queue.due_count(connection)
        return dict(stats) | {"execution_mode": self.settings.task_execution_mode}

    def run_due_tasks(self, now: str | None = None) -> dict[str, int]:
        """Drain currently due background work once.

        Exposed for operators and tests; the long-running worker process calls the
        same code path in a loop.
        """
        return self.worker.run_once(now=now).as_dict()
