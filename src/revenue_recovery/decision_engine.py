from dataclasses import dataclass
from datetime import datetime

from revenue_recovery.guardrails import GuardrailConfig, GuardrailResult, evaluate_guardrails
from revenue_recovery.models import FailureCategory


@dataclass(frozen=True)
class DecisionContext:
    category: FailureCategory
    amount: float
    retry_count: int
    recovery_probability: float
    incident_active: bool = False
    last_contact_at: datetime | None = None
    recommended_method: str | None = None
    retry_after_hours: int | None = None
    # Set only by the human-review resolution path. It satisfies the high-value
    # escalation guardrail and nothing else; see evaluate_guardrails.
    human_review_approved: bool = False


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    guardrail: GuardrailResult


class DecisionEngine:
    def __init__(self, config: GuardrailConfig = GuardrailConfig()):
        self.config = config

    def decide(self, context: DecisionContext) -> Decision:
        guardrail = evaluate_guardrails(
            context.category, context.amount, context.retry_count,
            context.incident_active, context.last_contact_at, config=self.config,
            human_review_approved=context.human_review_approved,
        )
        if not guardrail.allowed:
            return Decision(guardrail.forced_action or "STOP_RECOVERY", guardrail.reason, guardrail)
        if context.category in {FailureCategory.EXPIRED_CARD, FailureCategory.PAYMENT_METHOD_FAILURE} and context.recommended_method:
            return Decision("CHANGE_PAYMENT_METHOD", "A different payment method is recommended based on customer history.", guardrail)
        if context.recovery_probability >= 0.65:
            return Decision("RETRY_LATER", "Recovery probability is high and no guardrail blocks a retry.", guardrail)
        if context.recovery_probability >= 0.40:
            return Decision("SEND_NOTIFICATION", "Recovery probability is moderate; notify the customer before further recovery.", guardrail)
        return Decision("STOP_RECOVERY", "Recovery probability is low and no safe automated retry is justified.", guardrail)
