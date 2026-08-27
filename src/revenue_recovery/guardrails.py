from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from revenue_recovery.models import FailureCategory


@dataclass(frozen=True)
class GuardrailConfig:
    high_value_threshold: float = 50000.0
    max_retries: int = 3
    contact_cooldown_hours: int = 24


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    forced_action: str | None
    rule: str | None
    reason: str


def evaluate_guardrails(
    category: FailureCategory,
    amount: float,
    retry_count: int,
    incident_active: bool,
    last_contact_at: datetime | None,
    now: datetime | None = None,
    config: GuardrailConfig = GuardrailConfig(),
) -> GuardrailResult:
    if category is FailureCategory.FRAUD_RISK_DECLINE:
        return GuardrailResult(False, "STOP_RECOVERY", "FRAUD_HARD_STOP", "Fraud-risk declines cannot be automatically recovered.")
    if retry_count >= config.max_retries:
        return GuardrailResult(False, "STOP_RECOVERY", "RETRY_CAP", "The configured retry cap has been reached.")
    if amount >= config.high_value_threshold:
        return GuardrailResult(False, "ESCALATE_TO_HUMAN", "HIGH_VALUE_REVIEW", "The transaction exceeds the human-review threshold.")
    if incident_active:
        return GuardrailResult(False, "SUPPRESS_RETRY", "ACTIVE_INCIDENT", "Recovery is suppressed while the payment route has an active incident.")
    current = now or datetime.now(timezone.utc)
    if last_contact_at and current - last_contact_at < timedelta(hours=config.contact_cooldown_hours):
        return GuardrailResult(False, "SEND_NOTIFICATION", "CONTACT_COOLDOWN", "Customer contact is inside the configured cooldown window.")
    return GuardrailResult(True, None, None, "No blocking guardrail was triggered.")
