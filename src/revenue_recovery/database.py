"""Database access for both supported drivers.

Local development, tests, and CI run on SQLite with zero infrastructure; the
production containers run on PostgreSQL. One engine factory and one connection
wrapper serve both, and all SQL in the project stays dialect-neutral (named
bind parameters, ``INSERT ... RETURNING``, no vendor-specific syntax).
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from sqlalchemy import Connection, event, inspect, text
from sqlalchemy.engine import Engine, create_engine, make_url

from revenue_recovery.clock import iso_now
from revenue_recovery.schema import METADATA

SQLITE_DRIVER = "sqlite+pysqlite"


class SchemaNotMigratedError(RuntimeError):
    """Raised when a non-SQLite database is missing tables Alembic should have created."""


def normalize_database_url(target: str | Path) -> str:
    """Accept a filesystem path or a database URL and return a SQLAlchemy URL.

    Filesystem paths keep working so the SQLite-era call sites and the
    ``REVENUE_RECOVERY_DATABASE`` variable need no change.
    """
    if isinstance(target, Path):
        return f"{SQLITE_DRIVER}:///{target.as_posix()}"
    if "://" not in target:
        return f"{SQLITE_DRIVER}:///{Path(target).as_posix()}"
    url = make_url(target)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    elif url.drivername == "sqlite":
        url = url.set(drivername=SQLITE_DRIVER)
    return url.render_as_string(hide_password=False)


def is_sqlite_url(url: str) -> bool:
    return make_url(url).get_backend_name() == "sqlite"


def sqlite_file_path(url: str) -> Path | None:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:":
        return None
    return Path(parsed.database)


class DatabaseConnection:
    """Thin wrapper so callers write plain SQL and read rows by column name."""

    def __init__(self, connection: Connection):
        self._connection = connection

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> Any:
        return self._connection.execute(text(sql), dict(params or {}))

    def fetch_one(self, sql: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any] | None:
        return self.execute(sql, params).mappings().fetchone()

    def fetch_all(self, sql: str, params: Mapping[str, Any] | None = None) -> Sequence[Mapping[str, Any]]:
        return self.execute(sql, params).mappings().fetchall()

    def insert_returning_id(self, sql: str, params: Mapping[str, Any], id_column: str) -> int:
        row = self.fetch_one(f"{sql} RETURNING {id_column}", params)
        if row is None:
            raise RuntimeError("Insert did not return an identifier")
        return int(row[id_column])


class Database:
    def __init__(self, target: str | Path, echo: bool = False):
        self.url = normalize_database_url(target)
        self.is_sqlite = is_sqlite_url(self.url)
        self.engine = self._create_engine(echo)

    @property
    def path(self) -> Path | None:
        """Filesystem location for SQLite databases, ``None`` for PostgreSQL."""
        return sqlite_file_path(self.url)

    def _create_engine(self, echo: bool) -> Engine:
        if self.is_sqlite:
            file_path = self.path
            if file_path is not None and file_path.parent != Path(""):
                file_path.parent.mkdir(parents=True, exist_ok=True)
            engine = create_engine(
                self.url,
                echo=echo,
                future=True,
                connect_args={"check_same_thread": False, "timeout": 30},
            )
            event.listen(engine, "connect", _apply_sqlite_pragmas)
            return engine
        return create_engine(self.url, echo=echo, future=True, pool_pre_ping=True, pool_size=5, max_overflow=5)

    @contextmanager
    def connect(self) -> Iterator[DatabaseConnection]:
        with self.engine.begin() as connection:
            yield DatabaseConnection(connection)

    def initialize(self) -> None:
        """Make sure the schema is present before the application uses it.

        SQLite is created in place, which is what keeps local dev, tests, and CI
        free of any setup step. On PostgreSQL, Alembic owns the schema: creating
        tables here would let a process boot against a database no migration has
        ever touched, and the two definitions would then drift apart silently. So
        the production path verifies and refuses instead of creating.
        """
        if self.is_sqlite:
            METADATA.create_all(self.engine)
            return
        self.verify_schema()

    def verify_schema(self) -> None:
        inspector = inspect(self.engine)
        missing = sorted(name for name in METADATA.tables if not inspector.has_table(name))
        if missing:
            raise SchemaNotMigratedError(
                "Database is missing tables: "
                + ", ".join(missing)
                + ". Run `alembic upgrade head` against DATABASE_URL before starting the application."
            )

    def dispose(self) -> None:
        self.engine.dispose()

    @staticmethod
    def audit(connection: DatabaseConnection, event_id: int, event_type: str, details: dict) -> None:
        connection.execute(
            """INSERT INTO audit_log (event_id, event_type, details_json, created_at)
               VALUES (:event_id, :event_type, :details_json, :created_at)""",
            {
                "event_id": event_id,
                "event_type": event_type,
                "details_json": json.dumps(details, sort_keys=True, default=str),
                "created_at": iso_now(),
            },
        )


def _apply_sqlite_pragmas(dbapi_connection: sqlite3.Connection, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA busy_timeout = 30000")
    cursor.close()
