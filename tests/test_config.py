"""Settings resolution.

Environment variables are read in ``from_env`` rather than in field defaults, so a
test can build settings explicitly and importing the module does not freeze the
process environment.
"""

from pathlib import Path

import pytest

from revenue_recovery.config import INLINE, QUEUED, Settings


def test_defaults_are_sqlite_and_inline() -> None:
    settings = Settings()
    assert settings.database_target == Path("data/revenue_recovery.db")
    assert settings.task_execution_mode == INLINE
    assert settings.is_production is False


def test_database_url_wins_over_the_sqlite_path() -> None:
    settings = Settings(database_url="postgresql://u:p@h/db")
    assert settings.database_target == "postgresql://u:p@h/db"


def test_from_env_reads_every_documented_variable() -> None:
    settings = Settings.from_env({
        "REVENUE_RECOVERY_DATABASE": "custom.db",
        "DATABASE_URL": "postgresql+psycopg://u:p@h/db",
        "RECOVERY_MODEL_PATH": "models/other.joblib",
        "RAZORPAY_WEBHOOK_SECRET": "from_env",
        "APP_ENVIRONMENT": "Production",
        "TASK_EXECUTION_MODE": QUEUED,
        "TASK_MAX_ATTEMPTS": "5",
        "TASK_RETRY_BACKOFF_SECONDS": "120",
        "WORKER_POLL_INTERVAL_SECONDS": "1.5",
        "WORKER_BATCH_SIZE": "50",
    })
    assert settings.database_path == Path("custom.db")
    assert settings.database_target == "postgresql+psycopg://u:p@h/db"
    assert settings.recovery_model_path == Path("models/other.joblib")
    assert settings.razorpay_webhook_secret == "from_env"
    assert settings.is_production is True
    assert settings.task_execution_mode == QUEUED
    assert settings.task_max_attempts == 5
    assert settings.task_retry_backoff_seconds == 120
    assert settings.worker_poll_interval_seconds == 1.5
    assert settings.worker_batch_size == 50


def test_from_env_falls_back_to_defaults_on_an_empty_environment() -> None:
    settings = Settings.from_env({})
    assert settings.database_target == Path("data/revenue_recovery.db")
    assert settings.task_execution_mode == INLINE


def test_an_unknown_execution_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="task_execution_mode"):
        Settings(task_execution_mode="fire_and_forget")
