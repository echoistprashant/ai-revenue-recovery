"""Execution of already-approved recovery actions.

The executor is the only place that performs the side effect of an action, and it
re-runs the deterministic decision engine immediately before acting. That second
evaluation matters because time passes between approval and execution: a retry cap
may now be reached, a gateway incident may now be active, or the same event may have
been re-classified. If the engine no longer approves the action, the action does not
happen — the queue cannot outvote the engine.

Providers are injected so the simulated provider used for synthetic data can be
swapped for a real gateway client without touching decision logic.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

from revenue_recovery.baseline import simulate_outcome
from revenue_recovery.decision_engine import DecisionContext, DecisionEngine
from revenue_recovery.llm_boundary import ApprovedCommunication, CommunicationGenerator
from revenue_recovery.models import FailureCategory, RecoveryAction
from revenue_recovery.observability import mask_identifier
from revenue_recovery.tasks import TaskType

LOGGER = logging.getLogger(__name__)

RETRY_ACTIONS = {RecoveryAction.RETRY_NOW, RecoveryAction.RETRY_LATER}
CONTACTABLE_ACTIONS = {
    RecoveryAction.RETRY_NOW,
    RecoveryAction.RETRY_LATER,
    RecoveryAction.SEND_NOTIFICATION,
    RecoveryAction.CHANGE_PAYMENT_METHOD,
    RecoveryAction.ESCALATE_TO_HUMAN,
}


@dataclass(frozen=True)
class ActionContext:
    event_id: int
    payment_id: str
    category: FailureCategory
    amount: float
    retry_count: int
    recovery_probability: float
    incident_active: bool = False
    # True only when an authorized reviewer resolved an escalated case. It reaches
    # the high-value guardrail and stops there; the fraud hard stop and the retry
    # cap are evaluated first and are not affected by it.
    human_review_approved: bool = False


@dataclass(frozen=True)
class ExecutionResult:
    executed: bool
    revalidated_action: RecoveryAction
    detail: str
    recovered: bool | None = None
    final_state: str | None = None
    message: str | None = None


class RetryProvider(Protocol):
    def attempt_retry(self, context: ActionContext) -> bool: ...


class NotificationProvider(Protocol):
    def send(self, context: ActionContext, message: str) -> str: ...


class SimulatedRetryProvider:
    """Deterministic stand-in for a gateway retry call.

    Reuses the Phase 1 baseline simulator so queued execution produces exactly the
    same outcome as the inline path for the same event.
    """

    def attempt_retry(self, context: ActionContext) -> bool:
        return simulate_outcome(context.category, context.payment_id, context.retry_count)


class LoggingNotificationProvider:
    def send(self, context: ActionContext, message: str) -> str:
        # The message body is deliberately not logged. It is customer-facing prose
        # about a specific failed payment, the log is copied to places the database is
        # not, and the event id is enough to retrieve it from the audit trail.
        LOGGER.info(
            "notification dispatched",
            extra={
                "event_id": context.event_id,
                "payment_id": mask_identifier(context.payment_id),
                "action_category": context.category.value,
                "message_length": len(message),
            },
        )
        return f"logged:{context.event_id}"


class ActionExecutor:
    def __init__(
        self,
        decision_engine: DecisionEngine | None = None,
        retry_provider: RetryProvider | None = None,
        notification_provider: NotificationProvider | None = None,
        communication_generator: CommunicationGenerator | None = None,
    ):
        self.decision_engine = decision_engine or DecisionEngine()
        self.retry_provider = retry_provider or SimulatedRetryProvider()
        self.notification_provider = notification_provider or LoggingNotificationProvider()
        self.communication_generator = communication_generator or CommunicationGenerator()

    def execute(self, task_type: TaskType, context: ActionContext) -> ExecutionResult:
        decision = self.decision_engine.decide(DecisionContext(
            category=context.category,
            amount=context.amount,
            retry_count=context.retry_count,
            recovery_probability=context.recovery_probability,
            incident_active=context.incident_active,
            human_review_approved=context.human_review_approved,
        ))
        action = RecoveryAction(decision.action)
        if task_type is TaskType.EXECUTE_RETRY:
            return self._execute_retry(action, decision.reason, context)
        return self._send_notification(action, decision.reason, context)

    def _execute_retry(self, action: RecoveryAction, reason: str, context: ActionContext) -> ExecutionResult:
        if action not in RETRY_ACTIONS:
            return ExecutionResult(
                executed=False,
                revalidated_action=action,
                detail=f"Retry withheld at execution time: {reason}",
                final_state="WITHHELD",
            )
        recovered = self.retry_provider.attempt_retry(context)
        return ExecutionResult(
            executed=True,
            revalidated_action=action,
            detail="Retry executed after the decision engine re-approved the action.",
            recovered=recovered,
            final_state="RECOVERED" if recovered else "UNRESOLVED",
        )

    def _send_notification(self, action: RecoveryAction, reason: str, context: ActionContext) -> ExecutionResult:
        # Fraud declines never trigger automated customer contact, whatever the
        # queue holds, because the hard stop has no override path.
        if context.category is FailureCategory.FRAUD_RISK_DECLINE or action not in CONTACTABLE_ACTIONS:
            return ExecutionResult(
                executed=False,
                revalidated_action=action,
                detail=f"Notification withheld at execution time: {reason}",
            )
        message = self.communication_generator.generate(
            ApprovedCommunication(action, context.category, context.amount)
        )
        channel_reference = self.notification_provider.send(context, message)
        return ExecutionResult(
            executed=True,
            revalidated_action=action,
            detail=f"Notification dispatched via {channel_reference}.",
            message=message,
        )
