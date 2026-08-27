from datetime import datetime, timedelta, timezone

from revenue_recovery.anomaly import gateway_health
from revenue_recovery.decision_engine import DecisionContext, DecisionEngine
from revenue_recovery.guardrails import GuardrailConfig, evaluate_guardrails
from revenue_recovery.models import FailureCategory


def test_fraud_hard_stop_precedes_other_rules() -> None:
    result = evaluate_guardrails(FailureCategory.FRAUD_RISK_DECLINE, 100000, 0, False, None)
    assert result.forced_action == "STOP_RECOVERY"
    assert result.rule == "FRAUD_HARD_STOP"


def test_high_value_escalates() -> None:
    result = evaluate_guardrails(FailureCategory.INSUFFICIENT_FUNDS, 50001, 0, False, None)
    assert result.forced_action == "ESCALATE_TO_HUMAN"


def test_retry_cap_stops() -> None:
    result = evaluate_guardrails(FailureCategory.INSUFFICIENT_FUNDS, 100, 3, False, None, config=GuardrailConfig(max_retries=3))
    assert result.forced_action == "STOP_RECOVERY"


def test_contact_cooldown_blocks_contact() -> None:
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    result = evaluate_guardrails(FailureCategory.INSUFFICIENT_FUNDS, 100, 0, False, now - timedelta(hours=1), now=now)
    assert result.rule == "CONTACT_COOLDOWN"


def test_decision_engine_is_only_action_selector() -> None:
    decision = DecisionEngine().decide(DecisionContext(FailureCategory.INSUFFICIENT_FUNDS, 100, 0, 0.8))
    assert decision.action == "RETRY_LATER"


def test_incident_detector_requires_minimum_events_and_suppresses() -> None:
    healthy = gateway_health("Bank", "Gateway", 1, 10)
    incident = gateway_health("Bank", "Gateway", 12, 20)
    assert healthy.incident_active is False
    assert incident.incident_active is True
    decision = DecisionEngine().decide(DecisionContext(FailureCategory.INSUFFICIENT_FUNDS, 100, 0, 0.9, incident_active=True))
    assert decision.action == "SUPPRESS_RETRY"


def test_incident_clears_when_rate_normalizes() -> None:
    incident = gateway_health("Bank", "Gateway", 8, 20)
    recovered = gateway_health("Bank", "Gateway", 1, 50)
    assert incident.incident_active is True
    assert recovered.incident_active is False
