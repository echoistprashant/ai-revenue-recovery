"""Migration parity.

The application creates SQLite schemas from ``METADATA`` while production is
migrated by Alembic. If those two drift, a deployment silently gets a different
database than the one the tests exercised, so the migration is checked against the
metadata rather than trusted.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from revenue_recovery.config import Settings
from revenue_recovery.database import Database
from revenue_recovery.models import PaymentEventCreate
from revenue_recovery.schema import ALL_TABLES, METADATA
from revenue_recovery.service import PaymentRecoveryService

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def migrated(tmp_path, monkeypatch) -> Database:
    monkeypatch.setenv("REVENUE_RECOVERY_DATABASE", str(tmp_path / "migrated.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(config, "head")
    database = Database(tmp_path / "migrated.db")
    yield database
    database.dispose()


def test_migration_creates_the_same_tables_as_the_metadata(migrated: Database) -> None:
    tables = set(inspect(migrated.engine).get_table_names()) - {"alembic_version"}
    assert tables == set(METADATA.tables)


def test_migration_creates_the_same_columns_as_the_metadata(migrated: Database) -> None:
    inspector = inspect(migrated.engine)
    for table in ALL_TABLES:
        migrated_columns = {column["name"] for column in inspector.get_columns(table.name)}
        assert migrated_columns == {column.name for column in table.columns}, table.name


def test_migration_creates_the_same_indexes_as_the_metadata(migrated: Database) -> None:
    inspector = inspect(migrated.engine)
    for table in ALL_TABLES:
        migrated_indexes = {index["name"] for index in inspector.get_indexes(table.name)}
        expected = {index.name for index in table.indexes}
        assert expected <= migrated_indexes, table.name


def test_the_service_runs_against_a_migrated_database(migrated: Database, event_payload: dict) -> None:
    """A migrated database needs no create_all to be usable."""
    settings = Settings(
        database_path=migrated.path,
        recovery_model_path=Path("models/recovery_model.joblib"),
    )
    service = PaymentRecoveryService(migrated, settings)
    processed = service.process_event(PaymentEventCreate(**event_payload))
    assert processed.event_id > 0
    assert service.get_metrics().total_failures == 1
