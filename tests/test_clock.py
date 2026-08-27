"""UTC ISO-8601 text timestamps.

The task queue selects due work with a string comparison, so ``to_iso`` has to make
lexicographic order match chronological order for every input it accepts.
"""

from datetime import datetime, timedelta, timezone

from revenue_recovery.clock import from_iso, iso_now, to_iso, utc_now


def test_naive_datetimes_are_treated_as_utc() -> None:
    assert to_iso(datetime(2026, 8, 27, 10, 0, 0)) == "2026-08-27T10:00:00.000000+00:00"


def test_offset_datetimes_are_converted_to_utc() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    assert to_iso(datetime(2026, 8, 27, 15, 30, 0, tzinfo=ist)) == "2026-08-27T10:00:00.000000+00:00"


def test_text_order_matches_time_order_across_offsets() -> None:
    """A queue that compares strings must not be fooled by a different offset."""
    ist = timezone(timedelta(hours=5, minutes=30))
    earlier = to_iso(datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc))
    later_in_ist = to_iso(datetime(2026, 8, 27, 16, 0, 0, tzinfo=ist))  # 10:30 UTC
    assert earlier < later_in_ist


def test_round_trip_preserves_the_instant() -> None:
    moment = utc_now()
    assert from_iso(to_iso(moment)) == moment.replace(microsecond=moment.microsecond)


def test_from_iso_assumes_utc_for_offsetless_text() -> None:
    assert from_iso("2026-08-27T10:00:00").tzinfo is timezone.utc


def test_iso_now_is_sortable_and_parsable() -> None:
    first = iso_now()
    second = iso_now()
    assert first <= second
    assert from_iso(second) >= from_iso(first)
