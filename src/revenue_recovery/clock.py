from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(moment: datetime) -> str:
    """Normalize to UTC ISO-8601 text.

    Timestamps are stored as text so SQLite and PostgreSQL behave identically.
    Normalizing to a single UTC offset keeps lexicographic ordering equal to
    chronological ordering, which the task queue relies on when selecting due work.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


def iso_now() -> str:
    return to_iso(utc_now())


def from_iso(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
