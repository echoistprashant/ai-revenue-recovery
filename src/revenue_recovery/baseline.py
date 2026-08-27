from dataclasses import dataclass

from revenue_recovery.models import BaselineAction, FailureCategory


@dataclass(frozen=True)
class BaselineDecision:
    action: BaselineAction
    retry_delay_hours: int | None
    reason: str


def select_baseline_action(
    category: FailureCategory,
    retry_count: int,
    retry_delays_hours: tuple[int, ...],
) -> BaselineDecision:
    if category in {FailureCategory.FRAUD_RISK_DECLINE, FailureCategory.INVALID_CARD}:
        return BaselineDecision(
            action=BaselineAction.STOP_RECOVERY,
            retry_delay_hours=None,
            reason=f"Baseline stopped recovery because {category.value} is not retryable.",
        )
    if retry_count >= len(retry_delays_hours):
        return BaselineDecision(
            action=BaselineAction.STOP_RECOVERY,
            retry_delay_hours=None,
            reason="Baseline stopped recovery because the fixed retry schedule was exhausted.",
        )
    delay = retry_delays_hours[retry_count]
    return BaselineDecision(
        action=BaselineAction.RETRY_LATER,
        retry_delay_hours=delay,
        reason=f"Baseline scheduled fixed retry {retry_count + 1} after {delay} hour(s).",
    )


def simulate_outcome(category: FailureCategory, payment_id: str, retry_count: int) -> bool | None:
    """Return a deterministic synthetic outcome for the Phase 1 baseline."""
    if category in {FailureCategory.FRAUD_RISK_DECLINE, FailureCategory.INVALID_CARD}:
        return None
    base_rates = {
        FailureCategory.INSUFFICIENT_FUNDS: 0.58,
        FailureCategory.EXPIRED_CARD: 0.08,
        FailureCategory.AUTHENTICATION_FAILURE: 0.38,
        FailureCategory.BANK_DECLINED: 0.24,
        FailureCategory.GATEWAY_OR_NETWORK_FAILURE: 0.72,
        FailureCategory.PAYMENT_METHOD_FAILURE: 0.30,
        FailureCategory.TEMPORARY_BANK_ISSUE: 0.68,
    }
    threshold = max(0.05, base_rates[category] - (retry_count * 0.08))
    stable_fraction = (sum(ord(char) for char in payment_id) % 100) / 100
    return stable_fraction < threshold
