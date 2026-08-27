import json

from revenue_recovery.models import FailureCategory
from revenue_recovery.policy_learning import BanditObservation, OfflinePolicyLearner, PolicyAction, compare_policy


def main() -> None:
    observations = []
    categories = [FailureCategory.INSUFFICIENT_FUNDS, FailureCategory.GATEWAY_OR_NETWORK_FAILURE, FailureCategory.EXPIRED_CARD]
    actions = [PolicyAction.RETRY_LATER, PolicyAction.RETRY_LATER, PolicyAction.CHANGE_PAYMENT_METHOD]
    for index in range(300):
        category = categories[index % len(categories)]
        action = actions[index % len(actions)]
        reward = 1.0 if action is PolicyAction.RETRY_LATER else 0.8
        observations.append(BanditObservation(category, 0.7, 1000, 0, False, action, reward))
    learner = OfflinePolicyLearner(observations)
    print(json.dumps(compare_policy(observations, learner).__dict__, indent=2))


if __name__ == "__main__":
    main()
