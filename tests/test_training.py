from pathlib import Path

from revenue_recovery.training import train_and_evaluate


def test_training_is_grouped_and_documents_leakage(tmp_path: Path) -> None:
    metadata = train_and_evaluate(tmp_path / "model.joblib", tmp_path / "metadata.json", seed=42)
    assert metadata["customer_group_overlap"] == 0
    assert metadata["excluded_post_decision_fields"] == ["recovered", "recovery_time", "final_state"]
    assert set(metadata["metrics"]) == {"precision", "recall", "f1", "roc_auc"}
    assert metadata["largest_absolute_coefficients"]
