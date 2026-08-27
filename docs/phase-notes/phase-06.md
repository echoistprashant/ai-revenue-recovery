# Phase 6 — Experimentation Engine

## Objective

Move from unverified strategy claims to reproducible comparisons with explicit uncertainty.

## Implemented

- Deterministic hash-based experiment assignment
- Control and treatment recovery metrics
- Recovered revenue and unresolved-case comparison
- Two-proportion 95% confidence interval
- Explicit statistically-distinguishable flag
- What-if projection isolated from action execution
- Typed experiment API endpoint
- Executable JSON experiment report

## Evaluation Result

The deterministic 500-event demonstration produced:

- Control: 48.08% recovery, INR 126,750 simulated revenue
- Treatment: 61.25% recovery, INR 144,750 simulated revenue
- Recovery-rate delta: 13.17 percentage points
- 95% confidence interval: 4.43 to 21.91 percentage points
- Simulated revenue delta: INR 18,000
- What-if projection: 62.0% versus actual treatment 61.25%

The interval excludes zero for this simulated run, so the result is statistically distinguishable under the simulator assumptions. It is not evidence of real-world commercial performance.

## Fairness of Comparison

Assignment is deterministic from experiment ID and event ID. Both strategies operate on one latent event population. The treatment modifies only the modeled recovery threshold, avoiding independently generated favorable treatment outcomes.

## Scope Boundary

The experiment engine calculates and reports outcomes. It does not execute recovery actions, change decision thresholds, or update deployed policy automatically.

## Verification

- 45 tests passed before the final typed API addition
- executable report completed successfully
- what-if projection and simulated treatment actual were in the same range
- JSON serialization was verified end to end
