import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from revenue_recovery.scoring import CATEGORICAL_FEATURES, MODEL_FEATURES, NUMERIC_FEATURES


MODEL_VERSION = "recovery-logistic-v1"
FAILURE_EFFECTS = {
    "INSUFFICIENT_FUNDS": 0.5,
    "EXPIRED_CARD": -1.5,
    "INVALID_CARD": -3.0,
    "AUTHENTICATION_FAILURE": -0.2,
    "BANK_DECLINED": -0.8,
    "GATEWAY_OR_NETWORK_FAILURE": 1.1,
    "FRAUD_RISK_DECLINE": -4.0,
    "PAYMENT_METHOD_FAILURE": -0.6,
    "TEMPORARY_BANK_ISSUE": 0.9,
}


def generate_training_data(count: int = 3000, seed: int = 20260827) -> pd.DataFrame:
    rng = random.Random(seed)
    categories = list(FAILURE_EFFECTS)
    methods = ["CARD", "UPI", "NET_BANKING", "WALLET"]
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    for index in range(count):
        customer_id = f"customer_{rng.randint(1, 600):04d}"
        category = rng.choices(categories, weights=[28, 10, 6, 12, 14, 10, 4, 7, 9], k=1)[0]
        successes = rng.randint(0, 20)
        failures = rng.randint(0, 7)
        age = rng.randint(10, 1800)
        value = float(rng.choice([499, 799, 999, 1499, 2499, 4999]))
        retry_count = rng.randint(0, 3)
        timestamp = start + timedelta(hours=rng.randint(0, 24 * 365))
        method = rng.choice(methods)
        history_rate = successes / max(successes + failures, 1)
        logit = (
            -0.35
            + FAILURE_EFFECTS[category]
            + 1.8 * history_rate
            - 0.35 * retry_count
            - 0.08 * failures
            + (0.2 if 6 <= timestamp.hour <= 18 else -0.1)
            + (0.15 if method == "UPI" else 0.0)
        )
        probability = 1 / (1 + math.exp(-logit))
        recovered = int(rng.random() < probability)
        rows.append({
            "customer_id": customer_id,
            "failure_category": category,
            "payment_method": method,
            "previous_success_count": successes,
            "previous_failure_count": failures,
            "customer_age_days": age,
            "subscription_value": value,
            "retry_count": retry_count,
            "hour": timestamp.hour,
            "day_of_week": timestamp.weekday(),
            "recovered": recovered,
        })
    return pd.DataFrame(rows)


def train_and_evaluate(output_path: Path, metadata_path: Path, seed: int = 20260827) -> dict[str, object]:
    data = generate_training_data(seed=seed)
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed)
    train_indices, test_indices = next(splitter.split(data, groups=data["customer_id"]))
    train, test = data.iloc[train_indices], data.iloc[test_indices]

    preprocessing = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ("numeric", Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]), NUMERIC_FEATURES),
    ])
    pipeline = Pipeline([
        ("preprocessing", preprocessing),
        ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=seed)),
    ])
    pipeline.fit(train[MODEL_FEATURES], train["recovered"])
    probabilities = pipeline.predict_proba(test[MODEL_FEATURES])[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    true_negative, false_positive, false_negative, true_positive = confusion_matrix(
        test["recovered"], predictions
    ).ravel()
    metrics = {
        "precision": round(float(precision_score(test["recovered"], predictions)), 4),
        "recall": round(float(recall_score(test["recovered"], predictions)), 4),
        "f1": round(float(f1_score(test["recovered"], predictions)), 4),
        "roc_auc": round(float(roc_auc_score(test["recovered"], probabilities)), 4),
    }
    feature_names = pipeline.named_steps["preprocessing"].get_feature_names_out()
    coefficients = pipeline.named_steps["classifier"].coef_[0]
    coefficient_pairs = sorted(
        zip(feature_names.tolist(), coefficients.tolist(), strict=True),
        key=lambda pair: abs(pair[1]),
        reverse=True,
    )
    train_customers = set(train["customer_id"])
    test_customers = set(test["customer_id"])
    metadata = {
        "model_version": MODEL_VERSION,
        "model_type": "LogisticRegression",
        "seed": seed,
        "training_rows": int(len(train)),
        "test_rows": int(len(test)),
        "training_customers": len(train_customers),
        "test_customers": len(test_customers),
        "customer_group_overlap": len(train_customers & test_customers),
        "split_strategy": "GroupShuffleSplit by customer_id",
        "features": MODEL_FEATURES,
        "excluded_post_decision_fields": ["recovered", "recovery_time", "final_state"],
        "decision_threshold_for_evaluation_only": 0.5,
        "metrics": metrics,
        "class_balance": {
            "train_recovery_rate": round(float(train["recovered"].mean()), 4),
            "test_recovery_rate": round(float(test["recovered"].mean()), 4),
        },
        "error_analysis": {
            "true_negative": int(true_negative),
            "false_positive": int(false_positive),
            "false_negative": int(false_negative),
            "true_positive": int(true_positive),
        },
        "largest_absolute_coefficients": [
            {"feature": feature, "coefficient": round(coefficient, 4)}
            for feature, coefficient in coefficient_pairs[:10]
        ],
        "synthetic_data_disclaimer": "Metrics are from reproducible synthetic data, not production performance.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipeline, "model_version": MODEL_VERSION}, output_path)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata
