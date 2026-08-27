# Phase 4 — System Intelligence and Guardrails

## Objective

Make automated recovery bounded, deterministic, and aware of systemic bank or gateway failures.

## Implemented

- Centralized deterministic action selection
- Complete seven-action vocabulary
- Fraud-risk hard stop
- Configurable retry cap
- Configurable high-value human escalation
- Configurable contact cooldown
- Gateway/bank failure-rate incident detection
- Minimum evidence window for incident activation
- Incident-driven retry suppression
- Incident normalization/recovery behavior
- Typed decision and gateway-health APIs
- Score and guardrail explanations

## Guardrail Precedence

```text
duplicate event
→ fraud hard stop
→ retry cap
→ high-value escalation
→ active incident suppression
→ contact cooldown
→ normal deterministic policy
```

Fraud evaluation occurs before the recovery model is called. Neither a model probability nor any future LLM response can override it.

## Decision Policy

When no guardrail forces an action:

- expired-card or payment-method failures with a recommendation request a method change
- recovery probability at least 0.65 schedules a later retry
- probability from 0.40 to below 0.65 sends a notification
- lower probability stops recovery

These thresholds are explicit policy configuration candidates and are not intrinsic model meanings.

## Incident Detection

The initial detector compares observed failure rate with a documented 2% baseline and activates at three times baseline after at least 20 observations. Retry suppression ends when the measured rate normalizes.

## Verification

- 37 tests passed
- fraud cannot be retried even with probability 0.99
- high-value transactions escalate
- retry cap stops recovery
- active incidents suppress retries
- normalized rates clear the incident
- contact cooldown is enforced
- intelligent actions originate from the decision engine

All runtime outcomes remain simulated.
