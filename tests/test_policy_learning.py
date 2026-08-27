from revenue_recovery.models import FailureCategory
from revenue_recovery.policy_learning import BanditObservation, OfflinePolicyLearner, PolicyAction, compare_policy


def test_policy_learns_high_reward_action() -> None:
    observations = [
        BanditObservation(FailureCategory.INSUFFICIENT_FUNDS, 0.8, 100, 0, False, PolicyAction.RETRY_LATER, 1.0),
        BanditObservation(FailureCategory.INSUFFICIENT_FUNDS, 0.8, 100, 0, False, PolicyAction.SEND_NOTIFICATION, 0.1),
    ]
    decision = OfflinePolicyLearner(observations).decide(FailureCategory.INSUFFICIENT_FUNDS, 0.8, 100, 0, False)
    assert decision.action == "RETRY_LATER"
    assert decision.safety_forced is False


def test_policy_cannot_override_safety() -> None:
    observations = [BanditObservation(FailureCategory.FRAUD_RISK_DECLINE, 0.99, 100, 0, False, PolicyAction.RETRY_LATER, 99.0)]
    decision = OfflinePolicyLearner(observations).decide(FailureCategory.FRAUD_RISK_DECLINE, 0.99, 100, 0, False)
    assert decision.action == "STOP_RECOVERY"
    assert decision.safety_forced is True


def test_policy_comparison_is_deterministic() -> None:
    observations = [BanditObservation(FailureCategory.INSUFFICIENT_FUNDS, 0.8, 100, 0, False, PolicyAction.RETRY_LATER, 1.0)] * 10
    result = compare_policy(observations, OfflinePolicyLearner(observations))
    assert result.learned_total_reward == result.baseline_total_reward == 10.0
