"""Create or update an operator account.

Bootstrapping needs a first administrator, and there is no safe way for a program to
invent that password: a default would be public, and a generated one would have to be
printed and would end up in shell history or CI logs. So the password comes from the
operator — interactively, or from ``REVENUE_RECOVERY_ADMIN_PASSWORD`` for automated
provisioning — and is never written anywhere but the bcrypt hash in the database.

    python scripts/create_user.py --username admin --role ADMIN
    python scripts/create_user.py --username analyst --role VIEWER --tenant acme
    python scripts/create_user.py --username admin --role ADMIN --reset-password
"""

import argparse
import getpass
import os
import sys

from revenue_recovery.auth import Role, UnknownUserError, UserExistsError, UserRepository
from revenue_recovery.config import DEFAULT_SETTINGS
from revenue_recovery.database import Database
from revenue_recovery.security import WeakPasswordError

PASSWORD_VARIABLE = "REVENUE_RECOVERY_ADMIN_PASSWORD"


def read_password(confirm: bool = True) -> str:
    """Take the password from the environment, or prompt without echoing it."""
    from_environment = os.getenv(PASSWORD_VARIABLE, "")
    if from_environment:
        return from_environment
    if not sys.stdin.isatty():
        raise SystemExit(
            f"No terminal available for a password prompt. Set {PASSWORD_VARIABLE} instead."
        )
    password = getpass.getpass("Password: ")
    if confirm and password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords did not match.")
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or update a platform account")
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", default=Role.VIEWER.value, choices=[role.value for role in Role])
    parser.add_argument("--tenant", default=DEFAULT_SETTINGS.default_tenant)
    parser.add_argument("--database", default=None, help="Override DATABASE_URL / REVENUE_RECOVERY_DATABASE")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Set a new password for an account that already exists",
    )
    args = parser.parse_args(argv)

    target = args.database if args.database is not None else DEFAULT_SETTINGS.database_target
    database = Database(target)
    database.initialize()
    users = UserRepository(database)

    try:
        password = read_password()
        if args.reset_password:
            users.set_password(args.username, password)
            print(f"Password updated for {args.username!r}.")
            return 0
        user = users.create(args.username, password, Role(args.role), args.tenant)
    except UserExistsError as exc:
        print(f"{exc}. Use --reset-password to change its password.", file=sys.stderr)
        return 1
    except UnknownUserError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except WeakPasswordError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        database.dispose()

    print(f"Created {user.role.value} {user.username!r} in tenant {user.tenant_id!r}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
