from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from revenue_recovery.decision_engine import DecisionContext, DecisionEngine
from revenue_recovery.models import FailureCategory


class PolicyAction(StrEnum):
    RETRY_LATER = "RETRY_LATER"
    CHANGE_PAYMENT_METHOD = "CHANGE_PAYMENT_METHOD"
    SEND_NOTIFICATION = "SEND_NOTIFICATION"
    STOP_RECOVERY = "STOP_RECOVERY"


@dataclass(frozen=True)
class BanditObservation:
    category: FailureCategory
    recovery_probability: float
    amount: float
    retry_count: int
    incident_active: bool
    action: PolicyAction
    reward: float


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    expected_reward: float
    safety_forced: bool
    reason: str


@dataclass(frozen=True)
class PolicyComparison:
    observations: int
    learned_total_reward: float
    baseline_total_reward: float
    learned_average_reward: float
    baseline_average_reward: float
    learned_better: bool


class OfflinePolicyLearner:
    def __init__(self, observations: Iterable[BanditObservation]):
        self._scores: dict[tuple[FailureCategory, PolicyAction], list[float]] = {}
        for observation in observations:
            self._scores.setdefault((observation.category, observation.action), []).append(observation.reward)

    def decide(self, category: FailureCategory, recovery_probability: float, amount: float, retry_count: int, incident_active: bool) -> PolicyDecision:
        forced = DecisionEngine().decide(DecisionContext(category, amount, retry_count, recovery_probability, incident_active=incident_active))
        if forced.guardrail.forced_action:
            return PolicyDecision(forced.action, 0.0, True, forced.reason)
        candidates = [action for action in PolicyAction if (category, action) in self._scores]
        if not candidates:
            return PolicyDecision("STOP_RECOVERY", 0.0, False, "No learned evidence exists; using the safe fallback.")
        action = max(candidates, key=lambda candidate: sum(self._scores[(category, candidate)]) / len(self._scores[(category, candidate)]))
        rewards = self._scores[(category, action)]
        return PolicyDecision(action.value, round(sum(rewards) / len(rewards), 4), False, "Selected the action with the highest observed average reward for this failure category.")


def compare_policy(observations: list[BanditObservation], learner: OfflinePolicyLearner) -> PolicyComparison:
    learned_rewards: list[float] = []
    baseline_rewards: list[float] = []
    for observation in observations:
        decision = learner.decide(observation.category, observation.recovery_probability, observation.amount, observation.retry_count, observation.incident_active)
        learned_rewards.append(observation.reward if decision.action == observation.action.value else 0.0)
        baseline = DecisionEngine().decide(DecisionContext(observation.category, observation.amount, observation.retry_count, observation.recovery_probability, incident_active=observation.incident_active))
        baseline_rewards.append(observation.reward if baseline.action == observation.action.value else 0.0)
    learned_total = sum(learned_rewards)
    baseline_total = sum(baseline_rewards)
    n = len(observations)
    return PolicyComparison(n, round(learned_total, 2), round(baseline_total, 2), round(learned_total / n, 4) if n else 0.0, round(baseline_total / n, 4) if n else 0.0, learned_total > baseline_total)
