from dataclasses import dataclass
from datetime import timedelta
import json

from revenue_recovery.actions import ActionContext, ActionExecutor, RazorpayRetryProvider, SimulatedRetryProvider
from revenue_recovery.classification import classify_failure
from revenue_recovery.clock import iso_now, to_iso, utc_now
from revenue_recovery.config import QUEUED, Settings
from revenue_recovery.database import Database, DatabaseConnection
from revenue_recovery.decision_engine import DecisionContext, DecisionEngine
from revenue_recovery.guardrails import HIGH_VALUE_REVIEW, evaluate_guardrails
from revenue_recovery.models import AuditEntry, CaseResolution, EventHistoryItem, FailureCategory, PaymentEventCreate, PriorityCase, ProcessedEvent, RecoveryAction, RecoveryMetrics, ResolveCaseResponse, ReviewCase
from revenue_recovery.outbound import (
    MultiChannelNotificationProvider,
    RetellVoiceCallProvider,
    TwilioWhatsAppProvider,
    VapiVoiceCallProvider,
    VomyraVoiceCallProvider,
)
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
    RecoveryAction.SEND_NOTIFICATION: "AWAITING_CUSTOMER",
}

# The only state a reviewer may act on. A fraud decline lands in STOPPED and so is
# not offered for review at all; that is the first of the two barriers in front of
# the fraud hard stop, the second being the re-run of the decision engine.
REVIEWABLE_STATE = "ESCALATED"


class CaseNotReviewableError(ValueError):
    """Raised when a case is not in a state a reviewer may resolve."""


def _tenant_filter(tenant_id: str | None, alias: str) -> tuple[str, dict[str, object]]:
    """Return the ``WHERE`` fragment and bind parameters that scope a read.

    ``None`` means every tenant, which only the worker and the offline scripts use.
    Every API read passes the authenticated caller's tenant, so a request cannot
    widen its own scope by omitting a parameter.
    """
    if tenant_id is None:
        return "", {}
    return f" WHERE {alias}.tenant_id = :tenant_id", {"tenant_id": tenant_id}


class UnsupportedFailureCodeError(ValueError):
    pass


@dataclass(frozen=True)
class Dispatch:
    recovered: bool | None
    final_state: str
    recovered_amount: float
    task_id: int | None = None
    detail: str | None = None


class PaymentRecoveryService:
    def __init__(self, database: Database, settings: Settings, action_executor: ActionExecutor | None = None):
        self.database = database
        self.settings = settings
        self.database.initialize()
        self.scorer = RecoveryScorer(settings.recovery_model_path) if settings.recovery_model_path.exists() else None
        self.decision_engine = DecisionEngine()
        if action_executor is None:
            if settings.has_razorpay_credentials:
                retry_provider = RazorpayRetryProvider(settings.razorpay_key_id, settings.razorpay_key_secret)
            else:
                retry_provider = SimulatedRetryProvider()

            vp_choice = settings.voice_provider.lower()
            if vp_choice == "vapi":
                voice_provider = VapiVoiceCallProvider(
                    api_key=settings.vapi_api_key,
                    assistant_id=settings.vapi_assistant_id,
                    phone_number_id=settings.vapi_phone_number_id,
                    fallback_phone=settings.vapi_fallback_phone,
                )
            elif vp_choice == "vomyra":
                voice_provider = VomyraVoiceCallProvider(
                    api_key=settings.vomyra_api_key,
                    agent_id=settings.vomyra_agent_id,
                    api_url=settings.vomyra_api_url,
                    fallback_phone=settings.vomyra_fallback_phone,
                )
            else:
                voice_provider = RetellVoiceCallProvider(
                    api_key=settings.retell_api_key,
                    agent_id=settings.retell_agent_id,
                    from_number=settings.retell_from_number,
                    fallback_phone=settings.retell_fallback_phone,
                )
            wa_provider = TwilioWhatsAppProvider(
                account_sid=settings.twilio_account_sid,
                auth_token=settings.twilio_auth_token,
                whatsapp_from=settings.twilio_whatsapp_from,
            )
            notification_provider = MultiChannelNotificationProvider(
                voice_provider=voice_provider,
                whatsapp_provider=wa_provider,
            )
            action_executor = ActionExecutor(
                decision_engine=self.decision_engine,
                retry_provider=retry_provider,
                notification_provider=notification_provider,
            )
        self.action_executor = action_executor
        self.task_queue = TaskQueue(
            max_attempts=settings.task_max_attempts,
            backoff_seconds=settings.task_retry_backoff_seconds,
        )
        self.worker = RecoveryWorker(database, settings, self.action_executor, self.task_queue)

    @property
    def queued_execution(self) -> bool:
        return self.settings.task_execution_mode == QUEUED

    def _tenant(self, tenant_id: str | None) -> str:
        """Resolve the tenant for a write, falling back to the configured default.

        Reads take ``tenant_id=None`` to mean "every tenant", which the worker and
        the offline scripts need. Writes always land in exactly one tenant.
        """
        return tenant_id or self.settings.default_tenant

    def process_event(self, event: PaymentEventCreate, tenant_id: str | None = None) -> ProcessedEvent:
        tenant = self._tenant(tenant_id)
        try:
            category = classify_failure(event.failure_code)
        except ValueError as exc:
            raise UnsupportedFailureCodeError(str(exc)) from exc

        preliminary_guardrail = evaluate_guardrails(category, event.amount, event.retry_count, False, None)
        # Scoring is skipped for cases that are already finished — a fraud decline or a
        # capped retry gains nothing from a probability. A high-value escalation is the
        # exception: it is going to a person, who needs the model's view to decide, and
        # the retry they may approve is re-decided from this same score. Without it an
        # escalated case would carry a probability of zero and could never be retried.
        should_score = preliminary_guardrail.allowed or preliminary_guardrail.rule == HIGH_VALUE_REVIEW
        score = None
        if should_score and self.scorer:
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
                """SELECT event_id FROM payment_events
                   WHERE tenant_id = :tenant_id AND payment_id = :payment_id
                     AND attempt_id = :attempt_id""",
                {"tenant_id": tenant, "payment_id": event.payment_id, "attempt_id": event.attempt_id},
            )
            if existing:
                return self._load_processed(connection, int(existing["event_id"]), duplicate=True)

            created_at = iso_now()
            event_id = connection.insert_returning_id(
                """INSERT INTO payment_events (
                    tenant_id, payment_id, attempt_id, customer_id, subscription_id, amount, currency,
                    payment_method, gateway, bank, failure_code, failure_category,
                    event_timestamp, previous_success_count, previous_failure_count,
                    customer_age_days, subscription_value, retry_count, created_at
                ) VALUES (
                    :tenant_id, :payment_id, :attempt_id, :customer_id, :subscription_id, :amount, :currency,
                    :payment_method, :gateway, :bank, :failure_code, :failure_category,
                    :event_timestamp, :previous_success_count, :previous_failure_count,
                    :customer_age_days, :subscription_value, :retry_count, :created_at
                )""",
                {
                    "tenant_id": tenant,
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
            customer_id=event.customer_id,
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

    def get_metrics(self, tenant_id: str | None = None) -> RecoveryMetrics:
        scope, parameters = _tenant_filter(tenant_id, "e")
        with self.database.connect() as connection:
            summary = connection.fetch_one(
                """SELECT COUNT(*) AS total, COUNT(o.recovered) AS resolved,
                          COALESCE(SUM(CASE WHEN o.recovered = 1 THEN 1 ELSE 0 END), 0) AS recovered,
                          COALESCE(SUM(o.recovered_amount), 0) AS revenue
                   FROM payment_events e JOIN outcomes o ON o.event_id = e.event_id"""
                + scope,
                parameters,
            )
            breakdown_rows = connection.fetch_all(
                "SELECT failure_category, COUNT(*) AS count FROM payment_events e"
                + scope
                + " GROUP BY failure_category",
                parameters,
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

    def get_top_priority_cases(self, limit: int = 10, tenant_id: str | None = None) -> list[PriorityCase]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        scope, parameters = _tenant_filter(tenant_id, "e")
        with self.database.connect() as connection:
            rows = connection.fetch_all(
                """SELECT e.payment_id, e.attempt_id, e.failure_category, e.amount,
                          s.recovery_probability, s.churn_risk, s.revenue_at_risk,
                          s.priority_score, s.model_version
                   FROM scores s JOIN payment_events e ON e.event_id = s.event_id"""
                + scope
                + " ORDER BY s.priority_score DESC, e.event_id ASC LIMIT :limit",
                parameters | {"limit": limit},
            )
        return [PriorityCase(**dict(row)) for row in rows]

    def get_history(self, limit: int = 50, tenant_id: str | None = None) -> list[EventHistoryItem]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        scope, parameters = _tenant_filter(tenant_id, "e")
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
                   LEFT JOIN scores s ON s.event_id = e.event_id"""
                + scope
                + " ORDER BY e.event_id DESC LIMIT :limit",
                parameters | {"limit": limit},
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

    def get_review_queue(self, limit: int = 50, tenant_id: str | None = None) -> list[ReviewCase]:
        """Cases the engine escalated and no human has closed yet."""
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        scope, parameters = _tenant_filter(tenant_id, "e")
        clause = (scope + " AND " if scope else " WHERE ") + "o.final_state = :state AND o.resolved_at IS NULL"
        with self.database.connect() as connection:
            rows = connection.fetch_all(
                """SELECT e.event_id, e.payment_id, e.attempt_id, e.customer_id, e.amount,
                          e.currency, e.failure_category, d.action, d.reason, o.final_state,
                          s.recovery_probability, s.churn_risk, s.revenue_at_risk,
                          s.priority_score, e.created_at
                   FROM payment_events e
                   JOIN decisions d ON d.event_id = e.event_id
                   JOIN outcomes o ON o.event_id = e.event_id
                   LEFT JOIN scores s ON s.event_id = e.event_id"""
                + clause
                + " ORDER BY COALESCE(s.priority_score, 0) DESC, e.event_id ASC LIMIT :limit",
                parameters | {"state": REVIEWABLE_STATE, "limit": limit},
            )
        return [
            ReviewCase(
                event_id=int(row["event_id"]),
                payment_id=str(row["payment_id"]),
                attempt_id=str(row["attempt_id"]),
                customer_id=str(row["customer_id"]),
                amount=float(row["amount"]),
                currency=str(row["currency"]),
                failure_category=FailureCategory(row["failure_category"]),
                action=RecoveryAction(row["action"]),
                reason=str(row["reason"]),
                final_state=str(row["final_state"]),
                recovery_probability=row["recovery_probability"],
                churn_risk=row["churn_risk"],
                revenue_at_risk=row["revenue_at_risk"],
                priority_score=row["priority_score"],
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def resolve_case(
        self,
        event_id: int,
        resolution: CaseResolution,
        actor: str,
        note: str = "",
        tenant_id: str | None = None,
    ) -> ResolveCaseResponse:
        """Close an escalated case on a reviewer's authority.

        ``MANUAL_RETRY`` is the only resolution with a financial side effect, and it
        does not perform one directly: it goes through ``ActionExecutor``, which
        re-runs the deterministic decision engine. The reviewer's approval is passed
        as ``human_review_approved``, which satisfies the high-value escalation
        guardrail — the guardrail that exists precisely to wait for a person — and
        reaches nothing else. A fraud decline is refused twice over: it is never in
        ``ESCALATED`` state to begin with, and the engine would stop it anyway.
        """
        with self.database.connect() as connection:
            case = self._load_case(connection, event_id, tenant_id)
            category = FailureCategory(case["failure_category"])
            resolved_at = iso_now()
            if resolution is CaseResolution.MANUAL_RETRY:
                response = self._resolve_by_retry(connection, case, category, actor, resolved_at)
            else:
                response = self._resolve_by_record(connection, case, resolution, actor, resolved_at)
            self.database.audit(connection, event_id, "CASE_RESOLVED", {
                "resolution": resolution.value,
                "resolved_by": actor,
                "note": note,
                "final_state": response.final_state,
                "recovered": response.recovered,
                "executed": response.executed,
                "detail": response.detail,
                "failure_category": category.value,
            })
        return response

    def _load_case(self, connection: DatabaseConnection, event_id: int, tenant_id: str | None) -> dict:
        scope, parameters = _tenant_filter(tenant_id, "e")
        clause = (scope + " AND " if scope else " WHERE ") + "e.event_id = :event_id"
        row = connection.fetch_one(
            """SELECT e.event_id, e.amount, e.payment_id, e.retry_count, e.failure_category,
                      o.final_state, o.resolved_at,
                      COALESCE(s.recovery_probability, 0.0) AS recovery_probability
               FROM payment_events e
               JOIN outcomes o ON o.event_id = e.event_id
               LEFT JOIN scores s ON s.event_id = e.event_id"""
            + clause,
            parameters | {"event_id": event_id},
        )
        # A case in another tenant is reported as missing rather than forbidden: the
        # caller should not learn that the event exists.
        if row is None:
            raise LookupError(f"No case {event_id} in this tenant")
        if row["resolved_at"] is not None:
            raise CaseNotReviewableError(f"Case {event_id} was already resolved at {row['resolved_at']}")
        if str(row["final_state"]) != REVIEWABLE_STATE:
            raise CaseNotReviewableError(
                f"Case {event_id} is {row['final_state']}, and only {REVIEWABLE_STATE} cases can be resolved"
            )
        return dict(row)

    def _resolve_by_retry(
        self,
        connection: DatabaseConnection,
        case: dict,
        category: FailureCategory,
        actor: str,
        resolved_at: str,
    ) -> ResolveCaseResponse:
        context = ActionContext(
            event_id=int(case["event_id"]),
            payment_id=str(case["payment_id"]),
            category=category,
            amount=float(case["amount"]),
            retry_count=int(case["retry_count"]),
            recovery_probability=float(case["recovery_probability"]),
            human_review_approved=True,
        )
        result = self.action_executor.execute(TaskType.EXECUTE_RETRY, context)
        if not result.executed:
            # The engine refused. The case stays open so it is still visible, and
            # nothing is recorded as recovered.
            return ResolveCaseResponse(
                event_id=context.event_id, resolution=CaseResolution.MANUAL_RETRY,
                final_state=REVIEWABLE_STATE, recovered=None, executed=False,
                detail=result.detail, resolved_by=actor, resolved_at=resolved_at,
            )
        final_state = result.final_state or "UNRESOLVED"
        recovered_amount = float(case["amount"]) if result.recovered else 0.0
        self._write_resolution(connection, context.event_id, result.recovered, recovered_amount, final_state, actor, resolved_at)
        return ResolveCaseResponse(
            event_id=context.event_id, resolution=CaseResolution.MANUAL_RETRY,
            final_state=final_state, recovered=result.recovered, executed=True,
            detail=result.detail, resolved_by=actor, resolved_at=resolved_at,
        )

    def _resolve_by_record(
        self,
        connection: DatabaseConnection,
        case: dict,
        resolution: CaseResolution,
        actor: str,
        resolved_at: str,
    ) -> ResolveCaseResponse:
        """Record a reviewer's conclusion. No payment action is taken here."""
        recovered = resolution is CaseResolution.MANUAL_RECOVERED
        final_state = "MANUALLY_RECOVERED" if recovered else "WRITTEN_OFF"
        amount = float(case["amount"]) if recovered else 0.0
        event_id = int(case["event_id"])
        self._write_resolution(connection, event_id, recovered, amount, final_state, actor, resolved_at)
        detail = (
            "Reviewer recorded the payment as recovered outside the platform."
            if recovered
            else "Reviewer wrote the case off; no further recovery will be attempted."
        )
        return ResolveCaseResponse(
            event_id=event_id, resolution=resolution, final_state=final_state,
            recovered=recovered, executed=False, detail=detail,
            resolved_by=actor, resolved_at=resolved_at,
        )

    def _write_resolution(
        self,
        connection: DatabaseConnection,
        event_id: int,
        recovered: bool | None,
        recovered_amount: float,
        final_state: str,
        actor: str,
        resolved_at: str,
    ) -> None:
        connection.execute(
            """UPDATE outcomes
               SET recovered = :recovered, recovered_amount = :amount, final_state = :final_state,
                   resolved_by = :actor, resolved_at = :resolved_at
               WHERE event_id = :event_id""",
            {
                "recovered": None if recovered is None else int(recovered),
                "amount": recovered_amount,
                "final_state": final_state,
                "actor": actor,
                "resolved_at": resolved_at,
                "event_id": event_id,
            },
        )

    def get_audit_trail(
        self,
        event_id: int | None = None,
        limit: int = 100,
        tenant_id: str | None = None,
    ) -> list[AuditEntry]:
        """Read the audit log, scoped to the caller's tenant.

        The audit log has no tenant column of its own; it is joined to the event it
        describes so isolation follows from the event's tenant rather than from a
        second copy of the same fact.
        """
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        conditions = []
        parameters: dict[str, object] = {"limit": limit}
        if tenant_id is not None:
            conditions.append("e.tenant_id = :tenant_id")
            parameters["tenant_id"] = tenant_id
        if event_id is not None:
            conditions.append("a.event_id = :event_id")
            parameters["event_id"] = event_id
        clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        with self.database.connect() as connection:
            rows = connection.fetch_all(
                """SELECT a.audit_id, a.event_id, a.event_type, a.details_json, a.created_at
                   FROM audit_log a JOIN payment_events e ON e.event_id = a.event_id"""
                + clause
                + " ORDER BY a.audit_id DESC LIMIT :limit",
                parameters,
            )
        return [
            AuditEntry(
                audit_id=int(row["audit_id"]),
                event_id=int(row["event_id"]),
                event_type=str(row["event_type"]),
                details=_safe_json(str(row["details_json"])),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]


def _safe_json(raw: str) -> dict:
    """Audit rows are written by this application, but a hand-edited row should not
    break the whole audit view."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"unparsed": raw}
    return parsed if isinstance(parsed, dict) else {"value": parsed}
