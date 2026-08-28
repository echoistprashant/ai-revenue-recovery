"""What each role is offered in the dashboard menu.

These tests pin the *presentation* rule only. The backend's role checks are tested in
``tests/test_api_auth.py``, and they remain the enforcement: a viewer who reaches a
write route by any other means still gets a 403.
"""

import pytest

from dashboard.access import MODULES, ROLE_RANK, allowed, menu_for

WRITE_MODULES = {"💳 Payment Operations", "💬 Customer Communication"}
ADMIN_MODULES = {"👥 User Administration"}


def test_roles_are_ranked_so_a_higher_role_includes_a_lower_one() -> None:
    assert allowed("ADMIN", "VIEWER") is True
    assert allowed("ADMIN", "OPERATOR") is True
    assert allowed("OPERATOR", "VIEWER") is True
    assert allowed("VIEWER", "VIEWER") is True
    assert allowed("VIEWER", "OPERATOR") is False
    assert allowed("OPERATOR", "ADMIN") is False


def test_an_unrecognised_role_is_shown_nothing() -> None:
    """A role this build does not know ranks below everything, not above it.

    If a future backend adds a role, an old dashboard must fail closed rather than
    hand it the admin menu.
    """
    assert allowed("SUPERUSER", "VIEWER") is False
    assert menu_for("SUPERUSER") == []
    assert menu_for("") == []


def test_a_viewer_is_not_offered_a_module_that_writes() -> None:
    menu = set(menu_for("VIEWER"))
    assert not menu & WRITE_MODULES
    assert not menu & ADMIN_MODULES
    assert "📊 Executive Overview" in menu


def test_a_viewer_can_still_read_the_review_queue() -> None:
    """Seeing what is waiting for a human is a read; resolving it is not.

    The resolve control inside the panel is gated on OPERATOR separately, so a viewer
    can see the backlog without being able to act on it.
    """
    assert "🧑‍⚖️ Human Review Queue" in menu_for("VIEWER")


def test_an_operator_gets_the_write_modules_but_not_administration() -> None:
    menu = set(menu_for("OPERATOR"))
    assert WRITE_MODULES <= menu
    assert not menu & ADMIN_MODULES


def test_an_admin_gets_every_module() -> None:
    assert menu_for("ADMIN") == [label for label, _ in MODULES]


def test_menu_order_is_stable_and_labels_are_unique() -> None:
    labels = [label for label, _ in MODULES]
    assert len(labels) == len(set(labels))
    assert menu_for("VIEWER") == [label for label in labels if label in set(menu_for("VIEWER"))]


@pytest.mark.parametrize("minimum", [minimum for _, minimum in MODULES])
def test_every_module_declares_a_known_role(minimum: str) -> None:
    assert minimum in ROLE_RANK
