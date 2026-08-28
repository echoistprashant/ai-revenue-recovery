"""Tests for accounts and the role model.

The role model has one job: decide which routes a request may reach. These tests
pin that ranking down, and pin down the two account behaviours that leak
information if they go wrong — how a failed sign-in reports itself, and what a
deactivated account can still do.
"""

import pytest

from revenue_recovery.auth import (
    Role,
    UnknownUserError,
    User,
    UserExistsError,
    UserRepository,
    role_satisfies,
)
from revenue_recovery.security import WeakPasswordError

PASSWORD = "a-good-enough-password"
OTHER_PASSWORD = "a-different-password-99"


@pytest.fixture
def users(service) -> UserRepository:
    return UserRepository(service.database)


def test_role_ranking_is_cumulative() -> None:
    assert role_satisfies(Role.ADMIN, Role.VIEWER)
    assert role_satisfies(Role.ADMIN, Role.OPERATOR)
    assert role_satisfies(Role.OPERATOR, Role.VIEWER)
    assert role_satisfies(Role.VIEWER, Role.VIEWER)


def test_lower_roles_do_not_satisfy_higher_ones() -> None:
    assert not role_satisfies(Role.VIEWER, Role.OPERATOR)
    assert not role_satisfies(Role.VIEWER, Role.ADMIN)
    assert not role_satisfies(Role.OPERATOR, Role.ADMIN)


def test_user_can_reports_the_same_ranking() -> None:
    operator = User(1, "op", Role.OPERATOR, "acme", True, "2026-08-28T00:00:00+00:00")
    assert operator.can(Role.VIEWER)
    assert operator.can(Role.OPERATOR)
    assert not operator.can(Role.ADMIN)


def test_create_stores_a_hash_and_never_the_password(users: UserRepository, service) -> None:
    users.create("Alice", PASSWORD, Role.OPERATOR, "acme")
    with service.database.connect() as connection:
        row = connection.fetch_one("SELECT password_hash FROM users WHERE username = 'alice'")
    assert PASSWORD not in str(row["password_hash"])


def test_usernames_are_normalized(users: UserRepository) -> None:
    """``Alice`` and ``alice`` must be one account, or a second one could be created
    to shadow the first."""
    created = users.create("  Alice  ", PASSWORD, Role.VIEWER, "acme")
    assert created.username == "alice"
    assert users.get("ALICE").user_id == created.user_id
    with pytest.raises(UserExistsError):
        users.create("ALICE", OTHER_PASSWORD, Role.ADMIN, "acme")


def test_create_rejects_an_empty_username(users: UserRepository) -> None:
    with pytest.raises(ValueError):
        users.create("   ", PASSWORD, Role.VIEWER, "acme")


def test_create_rejects_a_weak_password_before_writing_a_row(users: UserRepository) -> None:
    with pytest.raises(WeakPasswordError):
        users.create("bob", "short", Role.VIEWER, "acme")
    assert users.count() == 0


def test_authenticate_accepts_the_right_password(users: UserRepository) -> None:
    users.create("alice", PASSWORD, Role.OPERATOR, "acme")
    authenticated = users.authenticate("alice", PASSWORD)
    assert authenticated is not None
    assert authenticated.role is Role.OPERATOR
    assert authenticated.tenant_id == "acme"


def test_authenticate_records_the_login_time(users: UserRepository) -> None:
    users.create("alice", PASSWORD, Role.VIEWER, "acme")
    assert users.get("alice").last_login_at is None
    users.authenticate("alice", PASSWORD)
    assert users.get("alice").last_login_at is not None


def test_authenticate_rejects_a_wrong_password(users: UserRepository) -> None:
    users.create("alice", PASSWORD, Role.ADMIN, "acme")
    assert users.authenticate("alice", OTHER_PASSWORD) is None


def test_an_unknown_username_and_a_wrong_password_are_indistinguishable(users: UserRepository) -> None:
    """Both return ``None``. Reporting "no such user" separately would turn the login
    form into a way to enumerate who has an account."""
    users.create("alice", PASSWORD, Role.VIEWER, "acme")
    assert users.authenticate("alice", OTHER_PASSWORD) is None
    assert users.authenticate("nobody-at-all", OTHER_PASSWORD) is None


def test_a_deactivated_account_cannot_sign_in_even_with_the_right_password(users: UserRepository) -> None:
    users.create("alice", PASSWORD, Role.ADMIN, "acme")
    users.set_active("alice", False)
    assert users.authenticate("alice", PASSWORD) is None


def test_reactivating_restores_sign_in(users: UserRepository) -> None:
    users.create("alice", PASSWORD, Role.ADMIN, "acme")
    users.set_active("alice", False)
    users.set_active("alice", True)
    assert users.authenticate("alice", PASSWORD) is not None


def test_set_password_replaces_the_old_one(users: UserRepository) -> None:
    users.create("alice", PASSWORD, Role.VIEWER, "acme")
    users.set_password("alice", OTHER_PASSWORD)
    assert users.authenticate("alice", PASSWORD) is None
    assert users.authenticate("alice", OTHER_PASSWORD) is not None


def test_set_password_rejects_a_weak_replacement(users: UserRepository) -> None:
    users.create("alice", PASSWORD, Role.VIEWER, "acme")
    with pytest.raises(WeakPasswordError):
        users.set_password("alice", "short")
    assert users.authenticate("alice", PASSWORD) is not None


def test_operations_on_a_missing_account_raise(users: UserRepository) -> None:
    with pytest.raises(UnknownUserError):
        users.get("ghost")
    with pytest.raises(UnknownUserError):
        users.set_active("ghost", False)
    with pytest.raises(UnknownUserError):
        users.set_password("ghost", PASSWORD)


def test_list_users_can_be_scoped_to_one_tenant(users: UserRepository) -> None:
    users.create("alice", PASSWORD, Role.ADMIN, "acme")
    users.create("bob", PASSWORD, Role.VIEWER, "globex")
    assert [user.username for user in users.list_users("acme")] == ["alice"]
    assert [user.username for user in users.list_users("globex")] == ["bob"]
    assert len(users.list_users()) == 2
