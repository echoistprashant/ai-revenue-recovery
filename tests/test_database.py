"""Dual-driver database layer: URL handling, schema ownership, and connections."""

from pathlib import Path

import pytest
from sqlalchemy import inspect

from revenue_recovery.database import (
    Database,
    SchemaNotMigratedError,
    is_sqlite_url,
    normalize_database_url,
    sqlite_file_path,
)
from revenue_recovery.schema import METADATA


def test_path_becomes_sqlite_url(tmp_path: Path) -> None:
    url = normalize_database_url(tmp_path / "app.db")
    assert url.startswith("sqlite+pysqlite:///")
    assert url.endswith("/app.db")


def test_bare_string_is_treated_as_a_file_path() -> None:
    assert normalize_database_url("data/app.db") == "sqlite+pysqlite:///data/app.db"


@pytest.mark.parametrize("driver", ["postgres", "postgresql", "postgresql+psycopg"])
def test_postgres_spellings_normalize_to_psycopg(driver: str) -> None:
    url = normalize_database_url(f"{driver}://user:secret@db:5432/revenue")
    assert url.startswith("postgresql+psycopg://")
    # The password has to survive normalization or production cannot connect.
    assert "secret" in url
    assert not is_sqlite_url(url)


def test_sqlite_url_is_upgraded_to_the_pysqlite_driver() -> None:
    assert normalize_database_url("sqlite:///data/app.db") == "sqlite+pysqlite:///data/app.db"


def test_sqlite_file_path_is_none_for_non_files() -> None:
    assert sqlite_file_path("postgresql+psycopg://u:p@h/db") is None
    assert sqlite_file_path("sqlite+pysqlite:///:memory:") is None
    assert sqlite_file_path("sqlite+pysqlite:///data/app.db") == Path("data/app.db")


def test_initialize_creates_every_table_and_parent_directory(tmp_path: Path) -> None:
    database = Database(tmp_path / "nested" / "dir" / "app.db")
    database.initialize()
    present = set(inspect(database.engine).get_table_names())
    assert set(METADATA.tables) <= present
    database.dispose()


def test_sqlite_enforces_foreign_keys(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    with database.connect() as connection:
        assert connection.fetch_one("PRAGMA foreign_keys")["foreign_keys"] == 1
    database.dispose()


def test_insert_returning_id_round_trips(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    with database.connect() as connection:
        event_id = connection.insert_returning_id(
            """INSERT INTO payment_events (
                   payment_id, attempt_id, customer_id, subscription_id, amount, currency,
                   payment_method, gateway, bank, failure_code, failure_category,
                   event_timestamp, previous_success_count, previous_failure_count,
                   customer_age_days, subscription_value, retry_count, created_at
               ) VALUES (
                   'pay_1', 'att_1', 'cust_1', 'sub_1', 100.0, 'INR',
                   'CARD', 'gw', 'bank', 'insufficient_funds', 'INSUFFICIENT_FUNDS',
                   '2026-08-27T00:00:00+00:00', 1, 0, 10, 100.0, 0, '2026-08-27T00:00:00+00:00'
               )""",
            {},
            "event_id",
        )
        assert event_id > 0
        row = connection.fetch_one(
            "SELECT payment_id FROM payment_events WHERE event_id = :id", {"id": event_id}
        )
        assert row["payment_id"] == "pay_1"
    database.dispose()


def test_non_sqlite_refuses_to_create_its_own_schema(tmp_path: Path) -> None:
    """Alembic owns the production schema.

    Booting against an unmigrated PostgreSQL database must fail loudly instead of
    silently creating tables that then drift from the migration history.
    """
    database = Database(tmp_path / "unmigrated.db")
    database.is_sqlite = False  # exercise the production branch without a live server
    with pytest.raises(SchemaNotMigratedError) as excinfo:
        database.initialize()
    assert "alembic upgrade head" in str(excinfo.value)
    database.dispose()
