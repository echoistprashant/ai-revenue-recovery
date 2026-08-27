import random
from datetime import datetime, timedelta, timezone

from revenue_recovery.models import PaymentEventCreate, PaymentMethod


FAILURE_CODES = (
    ("insufficient_funds", 0.28),
    ("card_expired", 0.10),
    ("invalid_card", 0.06),
    ("authentication_failed", 0.12),
    ("bank_declined", 0.14),
    ("gateway_timeout", 0.10),
    ("fraud_suspected", 0.04),
    ("payment_method_unavailable", 0.07),
    ("bank_temporarily_unavailable", 0.09),
)


def generate_events(count: int, seed: int) -> list[PaymentEventCreate]:
    if count <= 0:
        raise ValueError("count must be positive")
    rng = random.Random(seed)
    codes, weights = zip(*FAILURE_CODES, strict=True)
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    events: list[PaymentEventCreate] = []
    for index in range(count):
        customer_number = rng.randint(1, max(10, count // 4))
        previous_successes = rng.randint(0, 18)
        previous_failures = rng.randint(0, 5)
        amount = float(rng.choice((499, 799, 999, 1499, 2499, 4999)))
        event = PaymentEventCreate(
            payment_id=f"pay_{seed}_{index:04d}",
            attempt_id=f"attempt_{index:04d}_0",
            customer_id=f"customer_{customer_number:04d}",
            subscription_id=f"subscription_{customer_number:04d}",
            amount=amount,
            currency="INR",
            payment_method=rng.choice(tuple(PaymentMethod)),
            gateway=rng.choice(("synthetic_alpha", "synthetic_beta")),
            bank=rng.choice(("North Bank", "Central Bank", "South Bank")),
            failure_code=rng.choices(codes, weights=weights, k=1)[0],
            timestamp=start + timedelta(minutes=index * 15),
            previous_success_count=previous_successes,
            previous_failure_count=previous_failures,
            customer_age_days=rng.randint(15, 1500),
            subscription_value=amount,
            retry_count=0,
        )
        events.append(event)
    return events
