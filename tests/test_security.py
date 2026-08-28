"""Tests for password hashing and token signing.

These cover the two properties the rest of the auth stack assumes: a password is
never recoverable from what is stored, and a token that was not signed by this
process's key is rejected rather than partially trusted.
"""

from datetime import timedelta
from pathlib import Path

import jwt
import pytest

from revenue_recovery.config import MIN_SIGNING_KEY_LENGTH, Settings
from revenue_recovery.security import (
    MAX_PASSWORD_BYTES,
    MIN_PASSWORD_LENGTH,
    MissingSigningKeyError,
    TokenError,
    TokenSigner,
    WeakPasswordError,
    hash_password,
    resolve_signing_key,
    verify_password,
)

PASSWORD = "correct-horse-battery"
LONG_ENOUGH_KEY = "a-signing-key-that-is-clearly-long-enough"


def settings_for(environment: str = "development", **overrides) -> Settings:
    return Settings(
        database_path=Path("unused.db"),
        recovery_model_path=Path("models/recovery_model.joblib"),
        environment=environment,
        **overrides,
    )


def test_hash_password_does_not_contain_the_password() -> None:
    stored = hash_password(PASSWORD)
    assert PASSWORD not in stored
    assert stored.startswith("$2b$")


def test_hash_password_is_salted() -> None:
    """Two accounts with the same password must not share a hash.

    Identical hashes would let anyone reading the table group users by password and
    crack a whole group at once.
    """
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verify_password_accepts_the_original_and_rejects_everything_else() -> None:
    stored = hash_password(PASSWORD)
    assert verify_password(PASSWORD, stored) is True
    assert verify_password(PASSWORD.upper(), stored) is False
    assert verify_password(PASSWORD + "!", stored) is False
    assert verify_password("", stored) is False


def test_verify_password_rejects_a_corrupt_hash_instead_of_raising() -> None:
    """A damaged stored hash is a failed login, not a 500."""
    assert verify_password(PASSWORD, "not-a-bcrypt-hash") is False
    assert verify_password(PASSWORD, "") is False


def test_short_passwords_are_refused() -> None:
    with pytest.raises(WeakPasswordError):
        hash_password("a" * (MIN_PASSWORD_LENGTH - 1))


def test_overlong_passwords_are_refused_rather_than_silently_truncated() -> None:
    """bcrypt ignores bytes past 72, so accepting a longer password would mean two
    different passwords opening the same account."""
    with pytest.raises(WeakPasswordError):
        hash_password("a" * (MAX_PASSWORD_BYTES + 1))


def test_production_refuses_to_run_without_a_signing_key() -> None:
    with pytest.raises(MissingSigningKeyError):
        resolve_signing_key(settings_for("production", jwt_secret_key=""))


def test_production_refuses_a_short_signing_key() -> None:
    with pytest.raises(MissingSigningKeyError):
        resolve_signing_key(settings_for("production", jwt_secret_key="a" * (MIN_SIGNING_KEY_LENGTH - 1)))


def test_production_accepts_a_long_configured_key() -> None:
    assert resolve_signing_key(settings_for("production", jwt_secret_key=LONG_ENOUGH_KEY)) == LONG_ENOUGH_KEY


def test_development_generates_a_key_per_process() -> None:
    """Development gets a random key rather than a shared constant, so a token from
    one machine is worthless on another."""
    first = resolve_signing_key(settings_for("development"))
    second = resolve_signing_key(settings_for("development"))
    assert first != second
    assert len(first) >= MIN_SIGNING_KEY_LENGTH


def test_issued_token_round_trips() -> None:
    signer = TokenSigner(settings_for(), signing_key=LONG_ENOUGH_KEY)
    token, expires_in = signer.issue("operator", "OPERATOR", "acme")
    claims = signer.verify(token)
    assert claims.username == "operator"
    assert claims.role == "OPERATOR"
    assert claims.tenant_id == "acme"
    assert expires_in == 60 * 60


def test_a_token_signed_with_another_key_is_rejected() -> None:
    mint = TokenSigner(settings_for(), signing_key="an-attackers-own-signing-key-value")
    token, _ = mint.issue("attacker", "ADMIN", "acme")
    with pytest.raises(TokenError):
        TokenSigner(settings_for(), signing_key=LONG_ENOUGH_KEY).verify(token)


def test_a_tampered_token_is_rejected() -> None:
    signer = TokenSigner(settings_for(), signing_key=LONG_ENOUGH_KEY)
    token, _ = signer.issue("viewer", "VIEWER", "acme")
    header, payload, signature = token.split(".")
    with pytest.raises(TokenError):
        signer.verify(f"{header}.{payload}x.{signature}")


def test_an_unsigned_token_is_rejected() -> None:
    """``alg: none`` is the classic JWT bypass; PyJWT must not accept it here."""
    signer = TokenSigner(settings_for(), signing_key=LONG_ENOUGH_KEY)
    forged = jwt.encode({"sub": "attacker", "role": "ADMIN", "tenant": "acme", "iat": 0, "exp": 9999999999},
                        key="", algorithm="none")
    with pytest.raises(TokenError):
        signer.verify(forged)


def test_an_expired_token_is_rejected() -> None:
    signer = TokenSigner(settings_for(), signing_key=LONG_ENOUGH_KEY)
    signer.ttl = timedelta(seconds=-1)
    token, _ = signer.issue("viewer", "VIEWER", "acme")
    with pytest.raises(TokenError, match="expired"):
        signer.verify(token)


def test_a_token_without_an_expiry_is_rejected() -> None:
    """A token that never expires would outlive any credential rotation."""
    signer = TokenSigner(settings_for(), signing_key=LONG_ENOUGH_KEY)
    forever = jwt.encode({"sub": "viewer", "role": "VIEWER", "tenant": "acme", "iat": 0},
                         LONG_ENOUGH_KEY, algorithm="HS256")
    with pytest.raises(TokenError):
        signer.verify(forever)


def test_missing_and_empty_tokens_are_rejected() -> None:
    signer = TokenSigner(settings_for(), signing_key=LONG_ENOUGH_KEY)
    for value in ("", "   ", "not.a.token"):
        with pytest.raises(TokenError):
            signer.verify(value)
