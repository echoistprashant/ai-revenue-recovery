from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path(os.getenv("REVENUE_RECOVERY_DATABASE", "data/revenue_recovery.db"))
    retry_delays_hours: tuple[int, ...] = (1, 6, 24)
    synthetic_seed: int = 20260827


DEFAULT_SETTINGS = Settings()
