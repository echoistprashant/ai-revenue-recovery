from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd

from revenue_recovery.models import FailureCategory, PaymentEventCreate


CATEGORICAL_FEATURES = ["failure_category", "payment_method"]
NUMERIC_FEATURES = [
    "previous_success_count",
    "previous_failure_count",
    "customer_age_days",
    "subscription_value",
    "retry_count",
    "hour",
    "day_of_week",
]
MODEL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES


@dataclass(frozen=True)
class ScoreResult:
    recovery_probability: float
    churn_risk: float
    revenue_at_risk: float
    priority_score: float
    model_version: str


def build_feature_row(event: PaymentEventCreate, category: FailureCategory) -> dict[str, object]:
    return {
        "failure_category": category.value,
        "payment_method": event.payment_method.value,
        "previous_success_count": event.previous_success_count,
        "previous_failure_count": event.previous_failure_count,
        "customer_age_days": event.customer_age_days,
        "subscription_value": event.subscription_value,
        "retry_count": event.retry_count,
        "hour": event.timestamp.hour,
        "day_of_week": event.timestamp.weekday(),
    }


def calculate_churn_risk(previous_failure_count: int, customer_age_days: int) -> float:
    failure_component = min(previous_failure_count / 5, 1.0)
    age_component = 1.0 - min(customer_age_days / 730, 1.0)
    return round(failure_component * age_component, 4)


def calculate_revenue_at_risk(subscription_value: float, assumed_remaining_months: int) -> float:
    if assumed_remaining_months <= 0:
        raise ValueError("assumed_remaining_months must be positive")
    return round(subscription_value * assumed_remaining_months, 2)


class RecoveryScorer:
    def __init__(self, artifact_path: Path):
        artifact = joblib.load(artifact_path)
        self.pipeline = artifact["pipeline"]
        self.model_version = artifact["model_version"]

    def score(
        self,
        event: PaymentEventCreate,
        category: FailureCategory,
        assumed_remaining_months: int,
    ) -> ScoreResult:
        features = pd.DataFrame([build_feature_row(event, category)], columns=MODEL_FEATURES)
        recovery_probability = float(self.pipeline.predict_proba(features)[0, 1])
        churn_risk = calculate_churn_risk(event.previous_failure_count, event.customer_age_days)
        revenue_at_risk = calculate_revenue_at_risk(event.subscription_value, assumed_remaining_months)
        priority_score = recovery_probability * churn_risk * revenue_at_risk
        return ScoreResult(
            recovery_probability=round(recovery_probability, 4),
            churn_risk=churn_risk,
            revenue_at_risk=revenue_at_risk,
            priority_score=round(priority_score, 2),
            model_version=self.model_version,
        )
