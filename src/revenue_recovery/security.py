"""Password hashing and access-token signing.

Two rules shape this module:

- **No default signing key exists.** A published default would let anyone mint an
  admin token for every deployment that forgot to set one, so production refuses to
  start without ``JWT_SECRET_KEY`` and development generates a random key per
  process. Development tokens therefore stop working after a restart, which is the
  correct trade against a shared constant.
- **Token claims are not trusted as authority.** A token names a user; the role and
  tenant used for a request are re-read from the ``users`` row on every call
  (:mod:`revenue_recovery.auth`), so revoking or demoting an account takes effect
  immediately instead of at token expiry.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets

import bcrypt
import jwt

from revenue_recovery.clock import to_iso, utc_now
from revenue_recovery.config import MIN_SIGNING_KEY_LENGTH, Settings

# bcrypt truncates at 72 bytes and raises on longer input from 4.1 onward. Rejecting
# early gives a clear error instead of a library traceback on a registration form.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 12


class MissingSigningKeyError(RuntimeError):
    """Raised when a production deployment has no usable JWT signing key."""


class WeakPasswordError(ValueError):
    """Raised when a password cannot be accepted for storage."""


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired, or wrongly signed."""


@dataclass(frozen=True)
class TokenClaims:
    """The verified contents of an access token."""

    username: str
    role: str
    tenant_id: str
    expires_at: str
    issued_at: str


def hash_password(password: str) -> str:
    """Return a bcrypt hash, refusing inputs bcrypt cannot represent."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise WeakPasswordError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against a stored hash, returning False on any bad input.

    A malformed or truncated hash means the stored row is unusable, which is a
    failed login rather than a server error.
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:MAX_PASSWORD_BYTES], password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def resolve_signing_key(settings: Settings) -> str:
    """Return the signing key, or raise in production when none is configured."""
    configured = settings.jwt_secret_key.strip()
    if configured:
        if settings.is_production and len(configured) < MIN_SIGNING_KEY_LENGTH:
            raise MissingSigningKeyError(
                f"JWT_SECRET_KEY must be at least {MIN_SIGNING_KEY_LENGTH} characters in production. "
                "Generate one with `python -c \"import secrets; print(secrets.token_urlsafe(32))\"`."
            )
        return configured
    if settings.is_production:
        raise MissingSigningKeyError(
            "JWT_SECRET_KEY is not set. Production refuses to run with a generated or default "
            "signing key, because anyone holding it can mint an admin token."
        )
    return secrets.token_urlsafe(32)


class TokenSigner:
    """Signs and verifies access tokens for one process."""

    def __init__(self, settings: Settings, signing_key: str | None = None):
        self.settings = settings
        self.signing_key = signing_key if signing_key is not None else resolve_signing_key(settings)
        self.algorithm = settings.jwt_algorithm
        self.ttl = timedelta(minutes=settings.access_token_ttl_minutes)

    def issue(self, username: str, role: str, tenant_id: str) -> tuple[str, int]:
        """Return ``(token, expires_in_seconds)`` for a successful login."""
        issued_at = utc_now()
        expires_at = issued_at + self.ttl
        payload = {
            "sub": username,
            "role": role,
            "tenant": tenant_id,
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(payload, self.signing_key, algorithm=self.algorithm)
        return token, int(self.ttl.total_seconds())

    def verify(self, token: str) -> TokenClaims:
        """Decode a token, raising :class:`TokenError` for anything unusable."""
        if not token or not token.strip():
            raise TokenError("Missing access token")
        try:
            payload = jwt.decode(
                token,
                self.signing_key,
                algorithms=[self.algorithm],
                options={"require": ["sub", "exp", "iat"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("Access token has expired") from exc
        except jwt.InvalidTokenError as exc:
            raise TokenError("Access token is not valid") from exc
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise TokenError("Access token has no subject")
        return TokenClaims(
            username=subject,
            role=str(payload.get("role", "")),
            tenant_id=str(payload.get("tenant", "")),
            expires_at=to_iso(_from_epoch(payload["exp"])),
            issued_at=to_iso(_from_epoch(payload["iat"])),
        )


def _from_epoch(value: int | float) -> datetime:
    return datetime.fromtimestamp(float(value), tz=timezone.utc)
