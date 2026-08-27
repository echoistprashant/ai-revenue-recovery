from datetime import datetime, timezone

from revenue_recovery.models import PaymentMethod
from revenue_recovery.optimization import PaymentHistory, compare_strategies, recommend_payment_method, recommend_retry_window
from revenue_recovery.optimization_evaluation import evaluate_optimization, generate_customer_histories


def test_retry_window_varies_by_customer() -> None:
    history = [
        PaymentHistory("a", datetime(2026, 1, 1, 9, tzinfo=timezone.utc), PaymentMethod.CARD, True),
        PaymentHistory("a", datetime(2026, 1, 2, 9, tzinfo=timezone.utc), PaymentMethod.CARD, True),
        PaymentHistory("b", datetime(2026, 1, 1, 20, tzinfo=timezone.utc), PaymentMethod.UPI, True),
        PaymentHistory("b", datetime(2026, 1, 2, 20, tzinfo=timezone.utc), PaymentMethod.UPI, True),
    ]
    assert recommend_retry_window("a", history).preferred_hour != recommend_retry_window("b", history).preferred_hour


def test_retry_window_is_reproducible_from_reference_hour() -> None:
    history = [PaymentHistory("a", datetime(2026, 1, 1, 20, tzinfo=timezone.utc), PaymentMethod.UPI, True)]
    assert recommend_retry_window("a", history, reference_hour=10).retry_after_hours == 10


def test_method_recommendation_has_rate_and_cold_start() -> None:
    history = [
        PaymentHistory("a", datetime(2026, 1, 1, tzinfo=timezone.utc), PaymentMethod.CARD, False),
        PaymentHistory("a", datetime(2026, 1, 2, tzinfo=timezone.utc), PaymentMethod.UPI, True),
    ]
    recommendation = recommend_payment_method("a", history)
    assert recommendation.payment_method is PaymentMethod.UPI
    assert recommendation.success_rate == 1.0
    assert recommend_payment_method("new", []).confidence == 0.0


def test_strategy_comparison_uses_same_population() -> None:
    result = compare_strategies([
        {"retryable": True, "baseline_recovered": False, "optimized_recovered": True, "amount": 100},
        {"retryable": True, "baseline_recovered": True, "optimized_recovered": True, "amount": 200},
        {"retryable": False, "baseline_recovered": True, "optimized_recovered": True, "amount": 500},
    ])
    assert result.baseline_recovery_rate == 0.5
    assert result.optimized_recovery_rate == 1.0
    assert result.recovered_revenue_delta == 100


def test_optimization_evaluation_is_reproducible_and_improves() -> None:
    assert generate_customer_histories(seed=42) == generate_customer_histories(seed=42)
    first = evaluate_optimization(seed=42)
    second = evaluate_optimization(seed=42)
    assert first == second
    assert first.optimized_recovery_rate > first.baseline_recovery_rate
    assert first.optimized_recovered_revenue > first.baseline_recovered_revenue
