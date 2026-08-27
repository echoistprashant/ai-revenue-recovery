import argparse
from dataclasses import replace
from pathlib import Path

from revenue_recovery.config import DEFAULT_SETTINGS
from revenue_recovery.database import Database
from revenue_recovery.service import PaymentRecoveryService
from revenue_recovery.synthetic import generate_events


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a reproducible Phase 1 synthetic payment batch.")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=DEFAULT_SETTINGS.synthetic_seed)
    parser.add_argument("--database", type=Path, default=DEFAULT_SETTINGS.database_path)
    args = parser.parse_args()

    settings = replace(DEFAULT_SETTINGS, database_path=args.database, synthetic_seed=args.seed)
    service = PaymentRecoveryService(Database(settings.database_path), settings)
    for event in generate_events(args.count, args.seed):
        service.process_event(event)

    metrics = service.get_metrics()
    print(metrics.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
