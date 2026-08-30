"""Run the background recovery worker.

Deployment shape is one extra long-running process alongside the API:

    python scripts/run_worker.py

It claims due rows from the ``tasks`` table, re-runs the decision engine for each
one, and executes only what the engine still approves. Use ``--once`` to drain the
queue a single time (useful in cron-style deployments and for manual flushes).
"""

import argparse
import logging
import signal
import threading
from dataclasses import replace
from pathlib import Path

from revenue_recovery.config import DEFAULT_SETTINGS
from revenue_recovery.database import Database
from revenue_recovery.observability import configure_logging
from revenue_recovery.worker import RecoveryWorker


def build_worker(database: str | Path | None, batch_size: int | None, poll_seconds: float | None) -> RecoveryWorker:
    settings = DEFAULT_SETTINGS
    if batch_size is not None:
        settings = replace(settings, worker_batch_size=batch_size)
    if poll_seconds is not None:
        settings = replace(settings, worker_poll_interval_seconds=poll_seconds)
    target = database if database is not None else settings.database_target
    return RecoveryWorker(Database(target), settings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute queued recovery actions.")
    parser.add_argument("--database", default=None, help="SQLite path or SQLAlchemy URL (defaults to app settings)")
    parser.add_argument("--once", action="store_true", help="Drain currently due tasks and exit")
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--poll-seconds", type=float, default=None)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    # The worker is a process entry point, so it owns root logging. JSON when the
    # deployment asked for it (or in production), and the readable single-line format
    # otherwise, because this script is also run by hand.
    if not configure_logging(
        DEFAULT_SETTINGS.log_format or ("json" if DEFAULT_SETTINGS.is_production else ""),
        args.log_level,
    ):
        logging.basicConfig(
            level=getattr(logging, args.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    worker = build_worker(args.database, args.batch_size, args.poll_seconds)

    if args.once:
        print(worker.run_once().as_dict())
        return

    # SIGTERM is how a container stops. Setting the event lets the current task
    # finish and the loop exit cleanly instead of abandoning a claimed row.
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    worker.run_forever(stop_event=stop)


if __name__ == "__main__":
    main()
