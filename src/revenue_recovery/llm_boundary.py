from dataclasses import dataclass
from typing import Any, Callable

from revenue_recovery.models import FailureCategory, RecoveryAction


@dataclass(frozen=True)
class ApprovedCommunication:
    action: RecoveryAction
    category: FailureCategory
    amount: float


class CommunicationGenerator:
    """Generate wording only; the approved action is never selected here."""

    def generate(self, approved: ApprovedCommunication) -> str:
        templates = {
            RecoveryAction.RETRY_LATER: "We couldn't complete your payment. We will try again later; no action is needed right now.",
            RecoveryAction.CHANGE_PAYMENT_METHOD: "We couldn't complete your payment. Please update your payment method to keep your subscription active.",
            RecoveryAction.SEND_NOTIFICATION: "We couldn't complete your payment. Please review your payment details when convenient.",
            RecoveryAction.ESCALATE_TO_HUMAN: "We need a specialist to review this payment. Our team will contact you with the next steps.",
            RecoveryAction.SUPPRESS_RETRY: "We are temporarily pausing payment attempts while the payment network issue is investigated.",
            RecoveryAction.STOP_RECOVERY: "We could not recover this payment automatically. Please contact support for assistance.",
            RecoveryAction.RETRY_NOW: "We are attempting your payment again now.",
        }
        return templates[approved.action]


class AnalystTools:
    """Read-only analytics tools exposed to an analyst model."""

    def __init__(self, metrics: Callable[[], dict[str, Any]], breakdown: Callable[[], dict[str, Any]], gateway_health: Callable[[], dict[str, Any]], priority: Callable[[int], list[dict[str, Any]]]):
        self._tools = {
            "get_recovery_metrics": metrics,
            "get_failure_breakdown": breakdown,
            "get_gateway_health": gateway_health,
            "get_top_priority_cases": priority,
        }

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise ValueError(f"Unknown or non-approved analyst tool: {name}")
        return self._tools[name](**kwargs)


class RevenueAnalyst:
    def __init__(self, tools: AnalystTools):
        self.tools = tools

    def answer(self, question: str) -> str:
        normalized = question.lower()
        try:
            if any(word in normalized for word in ("gateway", "bank", "incident", "outage")):
                result = self.tools.call("get_gateway_health")
                source = "get_gateway_health"
            elif any(word in normalized for word in ("failure", "reason", "breakdown", "category")):
                result = self.tools.call("get_failure_breakdown")
                source = "get_failure_breakdown"
            elif any(word in normalized for word in ("priority", "case", "customer")):
                result = self.tools.call("get_top_priority_cases", n=3)
                source = "get_top_priority_cases"
            else:
                result = self.tools.call("get_recovery_metrics")
                source = "get_recovery_metrics"
        except Exception as exc:
            return f"I could not answer from project data because the approved analytics tool failed: {exc}"
        return f"Source: {source}. Project data: {result}. No financial action was executed."
