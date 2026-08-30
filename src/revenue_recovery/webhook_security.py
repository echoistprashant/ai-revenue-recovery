"""Freshness checking for signed gateway webhook deliveries.

An HMAC signature proves a payload came from someone holding the secret. It does not
prove *when*. Anyone who can capture one delivery — a proxy log, a mirrored request, a
misconfigured egress — holds a payload that stays valid forever, and can post it again
later.

Razorpay sends no timestamp header (unlike Stripe's `Stripe-Signature`, which carries a
`t=` element), so there is nothing to check outside the body. What it does send is a
`created_at` epoch second at the top level of the event, and that field is *inside* the
signed bytes: editing it invalidates the signature. So the timestamp is trustworthy
exactly to the degree the signature is, and comparing it against the local clock turns
a captured delivery into something that expires.

This is a freshness check, not deduplication. Two different guards do different jobs:

- Freshness rejects a delivery that is too old to be a live gateway callback.
- Idempotency on ``(tenant_id, payment_id, attempt_id)`` means a *fresh* duplicate —
  a genuine Razorpay retry, or a replay inside the window — returns the first stored
  decision without running the pipeline or executing an action a second time.

Neither one is sufficient alone, and the second is the one that protects money.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class WebhookFreshnessError(ValueError):
    """Raised when a delivery's own timestamp puts it outside the accepted window."""


@dataclass(frozen=True)
class Freshness:
    """The outcome of a freshness check, for logging as well as for control flow."""

    accepted: bool
    reason: str
    delivered_at: datetime | None
    skew_seconds: float | None


def delivery_timestamp(payload: Any) -> datetime | None:
    """Return the signed `created_at` of a Razorpay event, if it carries one.

    Prefers the event's own top-level `created_at`, which is what a real delivery
    always has, and falls back to the payment entity's. Returns ``None`` rather than
    guessing when neither is present or either is unparseable — "no timestamp" is a
    different fact from "timestamp of now", and the caller decides what to do with it.
    """
    if not isinstance(payload, dict):
        return None
    candidates = [payload.get("created_at")]
    entity = payload.get("payload")
    if isinstance(entity, dict):
        payment = entity.get("payment")
        if isinstance(payment, dict):
            inner = payment.get("entity") if isinstance(payment.get("entity"), dict) else payment
            candidates.append(inner.get("created_at"))
    for raw in candidates:
        if raw is None or isinstance(raw, bool):
            continue
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            continue
    return None


def check_freshness(
    delivered_at: datetime | None,
    *,
    now: datetime,
    tolerance_seconds: int,
    require_timestamp: bool,
) -> Freshness:
    """Decide whether a signed delivery is recent enough to act on.

    The window is symmetric. A delivery from the future is refused as firmly as a
    stale one: it means the sender's clock is wrong, and accepting it would extend the
    replay window by however far ahead that clock runs.

    ``require_timestamp`` is what production sets. A genuine Razorpay delivery always
    carries `created_at`, so an untimestamped payload in production is either not from
    Razorpay or has been stripped to defeat this check. Development leaves it off so
    the simulation scripts and the hand-built payloads in the test suite — which
    predate this check and are not replays of anything — keep working.
    """
    if delivered_at is None:
        if require_timestamp:
            return Freshness(False, "Delivery carries no signed timestamp.", None, None)
        return Freshness(True, "No signed timestamp; freshness not checked.", None, None)
    skew = (now - delivered_at).total_seconds()
    if abs(skew) > tolerance_seconds:
        direction = "stale" if skew > 0 else "ahead of this server's clock"
        return Freshness(
            False,
            f"Delivery is {direction} by {abs(skew):.0f}s, outside the {tolerance_seconds}s window.",
            delivered_at,
            skew,
        )
    return Freshness(True, "Within the accepted window.", delivered_at, skew)
