from pathlib import Path

import pandas as pd

from revenue_recovery.models import FailureCategory, PaymentEventCreate
from revenue_recovery.scoring import (
    MODEL_FEATURES,
    RecoveryScorer,
    build_feature_row,
    calculate_churn_risk,
    calculate_revenue_at_risk,
)


def test_feature_row_contains_only_approved_features(event_payload: dict) -> None:
    event = PaymentEventCreate.model_validate(event_payload)
    row = build_feature_row(event, FailureCategory.INSUFFICIENT_FUNDS)
    assert list(row) == MODEL_FEATURES
    assert "recovered" not in row
    assert "recovery_time" not in row


def test_churn_heuristic_is_bounded_and_explainable() -> None:
    assert calculate_churn_risk(0, 30) == 0.0
    assert calculate_churn_risk(5, 0) == 1.0
    assert 0 < calculate_churn_risk(3, 365) < 1


def test_revenue_at_risk_uses_configured_months() -> None:
    assert calculate_revenue_at_risk(1499, 6) == 8994


def test_saved_model_scores_probability(event_payload: dict) -> None:
    scorer = RecoveryScorer(Path("models/recovery_model.joblib"))
    event = PaymentEventCreate.model_validate(event_payload)
    score = scorer.score(event, FailureCategory.INSUFFICIENT_FUNDS, 6)
    assert 0 <= score.recovery_probability <= 1
    assert score.model_version == "recovery-logistic-v1"
    assert score.priority_score >= 0
