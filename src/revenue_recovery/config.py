from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path(os.getenv("REVENUE_RECOVERY_DATABASE", "data/revenue_recovery.db"))
    retry_delays_hours: tuple[int, ...] = (1, 6, 24)
    synthetic_seed: int = 20260827
    assumed_remaining_months: int = 6
    recovery_model_path: Path = Path("models/recovery_model.joblib")
    razorpay_webhook_secret: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret")


DEFAULT_SETTINGS = Settings()
