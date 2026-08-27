from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime

from revenue_recovery.models import PaymentMethod


@dataclass(frozen=True)
class PaymentHistory:
    customer_id: str
    timestamp: datetime
    payment_method: PaymentMethod
    successful: bool


@dataclass(frozen=True)
class RetryWindowRecommendation:
    customer_id: str
    retry_after_hours: int
    preferred_hour: int
    confidence: float
    reason: str


@dataclass(frozen=True)
class PaymentMethodRecommendation:
    customer_id: str
    payment_method: PaymentMethod
    success_rate: float
    sample_size: int
    confidence: float
    reason: str


@dataclass(frozen=True)
class StrategyComparison:
    baseline_recovery_rate: float
    optimized_recovery_rate: float
    baseline_recovered_revenue: float
    optimized_recovered_revenue: float
    recovery_rate_delta: float
    recovered_revenue_delta: float


def _history_by_customer(history: list[PaymentHistory]) -> dict[str, list[PaymentHistory]]:
    grouped: dict[str, list[PaymentHistory]] = defaultdict(list)
    for record in history:
        grouped[record.customer_id].append(record)
    return grouped


def recommend_retry_window(customer_id: str, history: list[PaymentHistory], reference_hour: int = 0, fallback_hours: int = 6) -> RetryWindowRecommendation:
    if not 0 <= reference_hour <= 23:
        raise ValueError("reference_hour must be between 0 and 23")
    records = [record for record in _history_by_customer(history).get(customer_id, []) if record.successful]
    if not records:
        return RetryWindowRecommendation(customer_id, fallback_hours, 12, 0.0, "No successful history; using the documented fallback window.")
    hour_counts = Counter(record.timestamp.hour for record in records)
    preferred_hour, count = hour_counts.most_common(1)[0]
    confidence = round(count / len(records), 4)
    retry_after = (preferred_hour - reference_hour) % 24
    retry_after = retry_after or 24
    return RetryWindowRecommendation(customer_id, retry_after, preferred_hour, confidence, f"Customer historically succeeds most often around hour {preferred_hour:02d}:00.")


def recommend_payment_method(customer_id: str, history: list[PaymentHistory], fallback: PaymentMethod = PaymentMethod.CARD) -> PaymentMethodRecommendation:
    records = _history_by_customer(history).get(customer_id, [])
    by_method: dict[PaymentMethod, list[PaymentHistory]] = defaultdict(list)
    for record in records:
        by_method[record.payment_method].append(record)
    if not by_method:
        return PaymentMethodRecommendation(customer_id, fallback, 0.0, 0, 0.0, "No payment-method history; using the documented fallback.")
    ranked = sorted(by_method.items(), key=lambda item: (sum(r.successful for r in item[1]) / len(item[1]), len(item[1]), item[0].value), reverse=True)
    method, method_records = ranked[0]
    rate = sum(record.successful for record in method_records) / len(method_records)
    confidence = min(1.0, len(method_records) / 10)
    return PaymentMethodRecommendation(customer_id, method, round(rate, 4), len(method_records), round(confidence, 4), f"{method.value} has the strongest historical success rate for this customer.")


def compare_strategies(events: list[dict[str, object]]) -> StrategyComparison:
    """Compare fixed retry timing with recommended timing using shared potential outcomes.

    Each event must provide baseline_recovered, optimized_recovered, amount, and retryable.
    """
    retryable = [event for event in events if event["retryable"]]
    if not retryable:
        return StrategyComparison(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    baseline = [bool(event["baseline_recovered"]) for event in retryable]
    optimized = [bool(event["optimized_recovered"]) for event in retryable]
    baseline_rate = sum(baseline) / len(baseline)
    optimized_rate = sum(optimized) / len(optimized)
    baseline_revenue = sum(float(event["amount"]) for event, recovered in zip(retryable, baseline, strict=True) if recovered)
    optimized_revenue = sum(float(event["amount"]) for event, recovered in zip(retryable, optimized, strict=True) if recovered)
    return StrategyComparison(round(baseline_rate, 4), round(optimized_rate, 4), round(baseline_revenue, 2), round(optimized_revenue, 2), round(optimized_rate - baseline_rate, 4), round(optimized_revenue - baseline_revenue, 2))
