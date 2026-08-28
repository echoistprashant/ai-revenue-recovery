"""User accounts, roles, and what each role is allowed to reach.

The role model is deliberately narrow. A role decides which *routes* a request may
reach; it never decides what a recovery action should be. There is no role, including
``ADMIN``, that can approve an action the deterministic decision engine refuses —
the manual-retry path in :mod:`revenue_recovery.service` re-runs the engine, so a
``FRAUD_RISK_DECLINE`` case stays stopped no matter who is signed in.

Roles:

- ``VIEWER``   — read dashboards, metrics, history, audit trail
- ``OPERATOR`` — everything a viewer can do, plus ingest events, flush the queue,
  and close escalated cases
- ``ADMIN``    — everything an operator can do, plus manage accounts
"""

from dataclasses import dataclass
from enum import StrEnum

from revenue_recovery.clock import iso_now
from revenue_recovery.database import Database, DatabaseConnection
from revenue_recovery.security import hash_password, verify_password


class Role(StrEnum):
    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"


# Ordered weakest to strongest. A route asks for a minimum role and any role at or
# above it passes, which keeps the check in one place instead of a per-route list.
ROLE_RANK = {Role.VIEWER: 1, Role.OPERATOR: 2, Role.ADMIN: 3}


def role_satisfies(actual: Role, required: Role) -> bool:
    return ROLE_RANK[actual] >= ROLE_RANK[required]


class UserExistsError(ValueError):
    """Raised when a username is already taken."""


class UnknownUserError(LookupError):
    """Raised when no account matches a username."""


@dataclass(frozen=True)
class User:
    user_id: int
    username: str
    role: Role
    tenant_id: str
    is_active: bool
    created_at: str
    last_login_at: str | None = None

    def can(self, required: Role) -> bool:
        return role_satisfies(self.role, required)


SELECT_USER = """SELECT user_id, username, password_hash, role, tenant_id, is_active,
                        created_at, last_login_at
                 FROM users WHERE username = :username"""


def _to_user(row) -> User:
    return User(
        user_id=int(row["user_id"]),
        username=str(row["username"]),
        role=Role(str(row["role"])),
        tenant_id=str(row["tenant_id"]),
        is_active=bool(row["is_active"]),
        created_at=str(row["created_at"]),
        last_login_at=None if row["last_login_at"] is None else str(row["last_login_at"]),
    )


class UserRepository:
    """Account storage. Passwords enter as plaintext and leave only as hashes."""

    def __init__(self, database: Database):
        self.database = database

    def create(self, username: str, password: str, role: Role, tenant_id: str) -> User:
        normalized = username.strip().lower()
        if not normalized:
            raise ValueError("Username must not be empty")
        password_hash = hash_password(password)
        created_at = iso_now()
        with self.database.connect() as connection:
            if connection.fetch_one("SELECT 1 FROM users WHERE username = :username", {"username": normalized}):
                raise UserExistsError(f"User {normalized!r} already exists")
            user_id = connection.insert_returning_id(
                """INSERT INTO users (username, password_hash, role, tenant_id, is_active, created_at)
                   VALUES (:username, :password_hash, :role, :tenant_id, 1, :created_at)""",
                {
                    "username": normalized,
                    "password_hash": password_hash,
                    "role": role.value,
                    "tenant_id": tenant_id,
                    "created_at": created_at,
                },
                "user_id",
            )
        return User(
            user_id=user_id, username=normalized, role=role, tenant_id=tenant_id,
            is_active=True, created_at=created_at,
        )

    def get(self, username: str) -> User:
        with self.database.connect() as connection:
            row = connection.fetch_one(SELECT_USER, {"username": username.strip().lower()})
        if row is None:
            raise UnknownUserError(f"No user named {username!r}")
        return _to_user(row)

    def list_users(self, tenant_id: str | None = None) -> list[User]:
        query = """SELECT user_id, username, password_hash, role, tenant_id, is_active,
                          created_at, last_login_at FROM users"""
        parameters: dict[str, object] = {}
        if tenant_id is not None:
            query += " WHERE tenant_id = :tenant_id"
            parameters["tenant_id"] = tenant_id
        with self.database.connect() as connection:
            rows = connection.fetch_all(query + " ORDER BY user_id ASC", parameters)
        return [_to_user(row) for row in rows]

    def set_active(self, username: str, active: bool) -> User:
        with self.database.connect() as connection:
            result = connection.execute(
                "UPDATE users SET is_active = :active WHERE username = :username",
                {"active": int(active), "username": username.strip().lower()},
            )
            if result.rowcount == 0:
                raise UnknownUserError(f"No user named {username!r}")
        return self.get(username)

    def set_password(self, username: str, password: str) -> None:
        password_hash = hash_password(password)
        with self.database.connect() as connection:
            result = connection.execute(
                "UPDATE users SET password_hash = :password_hash WHERE username = :username",
                {"password_hash": password_hash, "username": username.strip().lower()},
            )
            if result.rowcount == 0:
                raise UnknownUserError(f"No user named {username!r}")

    def count(self) -> int:
        with self.database.connect() as connection:
            row = connection.fetch_one("SELECT COUNT(*) AS total FROM users")
        return int(row["total"]) if row else 0

    def authenticate(self, username: str, password: str) -> User | None:
        """Return the user on a correct password, otherwise ``None``.

        Unknown usernames still run a hash comparison so a wrong name and a wrong
        password take a similar amount of time, and a deactivated account fails the
        same way a wrong password does — the caller learns only "these credentials
        do not work".
        """
        normalized = username.strip().lower()
        with self.database.connect() as connection:
            row = connection.fetch_one(SELECT_USER, {"username": normalized})
            if row is None:
                verify_password(password, DUMMY_HASH)
                return None
            if not verify_password(password, str(row["password_hash"])):
                return None
            if not bool(row["is_active"]):
                return None
            self._record_login(connection, normalized)
            user = _to_user(row)
        return user

    def _record_login(self, connection: DatabaseConnection, username: str) -> None:
        connection.execute(
            "UPDATE users SET last_login_at = :now WHERE username = :username",
            {"now": iso_now(), "username": username},
        )


# A real bcrypt hash of a random string that was discarded, so no password matches
# it. Its only purpose is to make the unknown-username path spend the same time as
# the known-username path instead of returning immediately.
DUMMY_HASH = "$2b$12$5AlURPhNiOnOABSN2ToVe.d5N/emUgfVuHRiWQmwDmksGjSA3jxZO"
