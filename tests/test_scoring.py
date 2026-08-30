import json
import logging
from pathlib import Path
import tomllib

import joblib
import pandas as pd
import sklearn
from packaging.specifiers import SpecifierSet
from packaging.version import Version

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


# --- the model artifact and the runtime must agree on scikit-learn ---------------
#
# scikit-learn does not guarantee that a pickle written by one minor release loads
# correctly in another, and the failure is quiet: the estimator can load with
# attributes missing and keep returning plausible numbers. Docker surfaced this as an
# `InconsistentVersionWarning`. These tests turn the warning into a build failure, so
# the dependency pin, the committed artifact, and the published metadata cannot drift
# apart unnoticed.


def test_the_artifact_records_the_scikit_learn_version_that_wrote_it() -> None:
    artifact = joblib.load(Path("models/recovery_model.joblib"))
    assert artifact["sklearn_version"], "an artifact with no recorded version cannot be checked"


def test_the_runtime_scikit_learn_matches_the_artifact() -> None:
    """The mismatch that produced the Docker warning, as an assertion."""
    artifact = joblib.load(Path("models/recovery_model.joblib"))
    assert artifact["sklearn_version"] == sklearn.__version__, (
        "The installed scikit-learn differs from the one that trained "
        "models/recovery_model.joblib. Install the pinned version, or retrain with "
        "scripts/train_recovery_model.py and commit both the artifact and its metadata."
    )


def test_the_dependency_pin_admits_the_artifacts_version() -> None:
    """A pin that excluded the artifact's own version would make a clean install broken."""
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    pins = [d for d in pyproject["project"]["dependencies"] if d.startswith("scikit-learn")]
    assert len(pins) == 1, pins
    recorded = joblib.load(Path("models/recovery_model.joblib"))["sklearn_version"]
    assert Version(recorded) in SpecifierSet(pins[0].removeprefix("scikit-learn"))


def test_the_published_metadata_names_the_same_version() -> None:
    """The metrics in this file describe one specific artifact; the version says which."""
    metadata = json.loads(Path("models/recovery_model_metadata.json").read_text(encoding="utf-8"))
    artifact = joblib.load(Path("models/recovery_model.joblib"))
    assert metadata["sklearn_version"] == artifact["sklearn_version"]
    assert metadata["model_version"] == artifact["model_version"]


def test_a_mismatched_artifact_warns_with_both_versions_and_still_loads(
    tmp_path, caplog
) -> None:
    """Loading must not fail: the guardrails sit between any score and any action, and
    refusing here would take the service down over what is usually a stale image."""
    original = joblib.load(Path("models/recovery_model.joblib"))
    stale = tmp_path / "stale.joblib"
    joblib.dump({**original, "sklearn_version": "0.1.0"}, stale)

    with caplog.at_level(logging.WARNING, logger="revenue_recovery.scoring"):
        scorer = RecoveryScorer(stale)

    assert scorer.model_version == original["model_version"]
    assert scorer.trained_with_sklearn == "0.1.0"
    record = next(r for r in caplog.records if "scikit-learn version" in r.message)
    assert record.trained_with_sklearn == "0.1.0"
    assert record.runtime_sklearn == sklearn.__version__
    assert "scripts/train_recovery_model.py" in record.remedy


def test_an_artifact_without_a_recorded_version_loads_without_a_warning(tmp_path, caplog) -> None:
    """Older artifacts predate the field. Absent is not a mismatch."""
    original = joblib.load(Path("models/recovery_model.joblib"))
    joblib.dump(
        {k: v for k, v in original.items() if k != "sklearn_version"}, tmp_path / "old.joblib"
    )
    with caplog.at_level(logging.WARNING, logger="revenue_recovery.scoring"):
        scorer = RecoveryScorer(tmp_path / "old.joblib")
    assert scorer.trained_with_sklearn is None
    assert not [r for r in caplog.records if "scikit-learn version" in r.message]
