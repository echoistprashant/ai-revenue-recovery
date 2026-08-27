from dataclasses import dataclass
import os
from pathlib import Path

INLINE = "inline"
QUEUED = "queued"
EXECUTION_MODES = (INLINE, QUEUED)


@dataclass(frozen=True)
class Settings:
    """Runtime configuration.

    Values are read from the environment in :meth:`from_env` rather than in field
    defaults, so importing this module does not freeze the process environment and
    tests can build explicit settings objects.
    """

    database_path: Path = Path("data/revenue_recovery.db")
    database_url: str = ""
    retry_delays_hours: tuple[int, ...] = (1, 6, 24)
    synthetic_seed: int = 20260827
    assumed_remaining_months: int = 6
    recovery_model_path: Path = Path("models/recovery_model.joblib")
    razorpay_webhook_secret: str = "test_webhook_secret"
    environment: str = "development"
    task_execution_mode: str = INLINE
    task_max_attempts: int = 3
    task_retry_backoff_seconds: int = 60
    worker_poll_interval_seconds: float = 5.0
    worker_batch_size: int = 20

    def __post_init__(self) -> None:
        if self.task_execution_mode not in EXECUTION_MODES:
            raise ValueError(f"task_execution_mode must be one of {EXECUTION_MODES}")

    @property
    def database_target(self) -> str | Path:
        """Explicit URL when configured, otherwise the SQLite file path."""
        return self.database_url or self.database_path

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        source = env if env is not None else dict(os.environ)
        return cls(
            database_path=Path(source.get("REVENUE_RECOVERY_DATABASE", "data/revenue_recovery.db")),
            database_url=source.get("DATABASE_URL", ""),
            recovery_model_path=Path(source.get("RECOVERY_MODEL_PATH", "models/recovery_model.joblib")),
            razorpay_webhook_secret=source.get("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret"),
            environment=source.get("APP_ENVIRONMENT", "development"),
            task_execution_mode=source.get("TASK_EXECUTION_MODE", INLINE),
            task_max_attempts=int(source.get("TASK_MAX_ATTEMPTS", "3")),
            task_retry_backoff_seconds=int(source.get("TASK_RETRY_BACKOFF_SECONDS", "60")),
            worker_poll_interval_seconds=float(source.get("WORKER_POLL_INTERVAL_SECONDS", "5.0")),
            worker_batch_size=int(source.get("WORKER_BATCH_SIZE", "20")),
        )


DEFAULT_SETTINGS = Settings.from_env()
