# Phase 2 — Machine Learning Layer

## Objective

Add honest recovery prediction and deterministic business scoring without allowing ML to select or execute payment actions.

## Implemented

- Logistic Regression recovery-probability pipeline
- One-hot categorical processing and scaled numeric processing
- Customer-grouped train/test split
- Versioned model artifact and JSON metadata
- Held-out precision, recall, F1, and ROC-AUC
- Confusion-matrix error counts and coefficient-based explanations
- Explicit post-decision leakage exclusions
- Transparent churn-risk heuristic
- Configurable six-month revenue-at-risk assumption
- Deterministic priority formula
- Persisted score records with model version
- Ranked priority-case API and dashboard view
- Score context in audit records

## Prediction Target

The target is whether a synthetic failed payment recovers within the simulator's modeled recovery process. This target and all reported metrics are synthetic demonstration data, not production evidence.

## Features

- failure category
- payment method
- previous success count
- previous failure count
- customer age in days
- subscription value
- retry count
- event hour
- day of week

The outcome, recovery time, and final state are explicitly excluded because they are not available when a decision is made.

## Evaluation

Seed: `20260827`

- Training rows: 2,195
- Test rows: 805
- Split: grouped by customer ID
- Customer overlap between train and test: 0
- Precision: 0.7329
- Recall: 0.7488
- F1: 0.7407
- ROC-AUC: 0.7985

The `0.5` threshold is used only to calculate evaluation classification metrics. It is not a business retry threshold.

## Churn Risk

Churn risk remains a heuristic:

```text
min(previous_failure_count / 5, 1)
×
(1 - min(customer_age_days / 730, 1))
```

It is bounded from 0 to 1, documented, and never described as a trained model or calibrated churn probability.

## Revenue at Risk

```text
subscription_value × assumed_remaining_months
```

The initial configurable assumption is six remaining months. This is an estimate, not observed future revenue.

## Priority Score

```text
recovery_probability × churn_risk × revenue_at_risk
```

The formula is deterministic and preserved from the blueprint.

## Important Boundary

Phase 2 does not change the Phase 1 recovery action from model probability. Measured recovery-rate improvement requires an approved deterministic strategy consuming these scores, which belongs to later optimization and decision-engine phases. Claiming an improvement in Phase 2 would be fabricated.

## Limitations

- The model learns relationships deliberately embedded in synthetic data.
- Metrics do not demonstrate production generalization.
- A larger or real longitudinal dataset could change feature usefulness and calibration.
- The churn heuristic has no trained-model performance metric.
- Priority multiplication can be dominated by revenue scale or collapse when churn risk is near zero.

## Verification

The final phase report records the full test result, model metadata, commit, and push status.
