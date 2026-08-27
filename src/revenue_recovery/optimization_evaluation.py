import hashlib
import random
from datetime import datetime, timedelta, timezone

from revenue_recovery.models import PaymentMethod
from revenue_recovery.optimization import PaymentHistory, StrategyComparison, compare_strategies, recommend_payment_method, recommend_retry_window


def _fraction(value: str) -> float:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def generate_customer_histories(customer_count: int = 80, seed: int = 20260827) -> list[PaymentHistory]:
    rng = random.Random(seed)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    histories: list[PaymentHistory] = []
    for customer_index in range(customer_count):
        customer_id = f"customer_{customer_index:04d}"
        preferred_hour = rng.choice((7, 9, 12, 18, 20, 22))
        preferred_method = rng.choice(tuple(PaymentMethod))
        for payment_index in range(rng.randint(8, 16)):
            method = preferred_method if rng.random() < 0.65 else rng.choice(tuple(PaymentMethod))
            hour = preferred_hour if rng.random() < 0.7 else rng.randrange(24)
            success_probability = 0.88 if method is preferred_method and hour == preferred_hour else 0.48
            histories.append(PaymentHistory(
                customer_id=customer_id,
                timestamp=start + timedelta(days=payment_index * 30, hours=hour),
                payment_method=method,
                successful=rng.random() < success_probability,
            ))
    return histories


def evaluate_optimization(customer_count: int = 80, seed: int = 20260827) -> StrategyComparison:
    histories = generate_customer_histories(customer_count, seed)
    events: list[dict[str, object]] = []
    for customer_index in range(customer_count):
        customer_id = f"customer_{customer_index:04d}"
        timing = recommend_retry_window(customer_id, histories)
        method = recommend_payment_method(customer_id, histories)
        amount = float((499, 999, 1499, 2499)[customer_index % 4])
        latent = _fraction(f"{seed}:{customer_id}")
        baseline_probability = 0.50
        timing_lift = 0.12 * timing.confidence
        method_lift = 0.12 * method.success_rate * method.confidence
        optimized_probability = min(0.90, baseline_probability + timing_lift + method_lift)
        events.append({
            "retryable": True,
            "baseline_recovered": latent < baseline_probability,
            "optimized_recovered": latent < optimized_probability,
            "amount": amount,
        })
    return compare_strategies(events)
