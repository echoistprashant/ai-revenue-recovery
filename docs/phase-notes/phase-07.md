# Phase 7 — Advanced AI (Optional)

## Objective

Evaluate whether a simple learned action policy can outperform the hand-designed policy without weakening deterministic safety controls.

## Implemented

- Offline contextual-bandit-style observations
- Failure-category/action reward aggregation
- Highest-average-reward action selection
- Safe fallback for unseen contexts
- Mandatory deterministic guardrail evaluation before learned selection
- Offline comparison with the Phase 4 deterministic policy

## Evaluation

The 300-observation synthetic demonstration produced:

- learned total reward: 280.0
- deterministic baseline total reward: 200.0
- learned average reward: 0.9333
- baseline average reward: 0.6667

This result reflects the deliberately constructed synthetic reward environment. It is not evidence that policy learning would outperform the deterministic policy on real payments.

## Safety Boundary

A learned action is considered only after the deterministic decision engine evaluates guardrails. Forced actions such as fraud `STOP_RECOVERY`, high-value escalation, retry-cap stop, and incident suppression cannot be overridden by learned reward estimates.

## Deployment Boundary

The learner is offline-only. It does not retrain continuously, update deployed policy, execute actions, or write financial configuration.

## Verification

- 49 tests passed
- high-reward fraud retry evidence still produces `STOP_RECOVERY`
- unseen contexts use a safe fallback
- policy comparison is deterministic
