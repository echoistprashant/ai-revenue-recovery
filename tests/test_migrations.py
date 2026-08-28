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

from revenue_recovery.auth import Role, UserRepository
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


def test_migration_scopes_the_idempotency_key_to_the_tenant(migrated: Database) -> None:
    """The unique key must include ``tenant_id`` in the migrated schema too.

    If the migration kept the old two-column key, two tenants could not both hold a
    gateway's payment identifier, and the duplicate response would tell one tenant
    that another had already processed that payment.
    """
    constraints = inspect(migrated.engine).get_unique_constraints("payment_events")
    keys = [set(constraint["column_names"]) for constraint in constraints]
    assert {"tenant_id", "payment_id", "attempt_id"} in keys
    assert {"payment_id", "attempt_id"} not in keys


def test_accounts_round_trip_against_a_migrated_database(migrated: Database) -> None:
    """Sign-in works on a migrated database, not only on a create_all one."""
    users = UserRepository(migrated)
    created = users.create("migrated-admin", "migration-password-1234", Role.ADMIN, "acme")
    assert created.tenant_id == "acme"
    assert users.authenticate("migrated-admin", "migration-password-1234") is not None
    assert users.authenticate("migrated-admin", "wrong-password-entirely") is None
