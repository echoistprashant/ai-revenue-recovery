# Phase 3 — Recovery Optimization

## Objective

Use customer history to recommend a more appropriate retry time and payment method instead of treating every recovery action identically.

## Implemented

- Explicit customer payment-history records
- Customer-specific successful-hour aggregation
- Retry-window recommendations with confidence and explanation
- Payment-method success-rate ranking
- Method recommendation sample size and confidence
- Documented cold-start fallbacks
- Shared-population optimization evaluation
- Reproducible latent potential outcomes for fair strategy comparison

## Retry Timing

For customers with successful history, the recommended hour is the most frequently successful historical hour. Confidence is the share of successful records occurring in that hour. Customers with no successful history receive the documented six-hour fallback.

This is an explainable historical heuristic, not a trained retry-timing model.

## Payment Method

Methods are ranked by historical customer-specific success rate, then sample size. Confidence increases with sample size up to ten observations. Customers without history receive the documented card fallback with zero confidence.

## Evaluation Design

The fixed and optimized strategies are evaluated against the same customer population and the same deterministic latent outcome value for each customer. Optimization changes the success threshold based on timing and method evidence; it does not receive independently generated favorable labels.

All results are simulated and do not represent production performance.

## Scope Boundary

Phase 3 returns timing and method recommendations. It does not provide the final centralized action authority, incident suppression, human escalation, or other Phase 4 guardrails.

## Verification

The final report records the actual measured comparison, test result, commit, and push status.
