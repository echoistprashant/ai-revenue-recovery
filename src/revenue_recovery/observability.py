"""Structured logging and identifier masking.

Two problems this module exists to solve.

**Log lines are read by machines.** A recovery decision is only auditable if the log
line carrying it can be filtered and joined, so records are emitted as one JSON object
per line with the extras the call site attached. `LOG_FORMAT` is empty by default,
which means "leave the logging configuration alone" — that is what tests, scripts, and
an interactive shell want. Production defaults to JSON without an operator having to
remember a variable.

**Identifiers in logs are not free.** A payment id, a customer id, and a subscription
id are pseudonymous, but they are the join key back to a real person's payment history
in the gateway's dashboard. Logs are copied into places the database is not — a
shipper, a laptop, a support ticket — so this module masks them to a stable digest.
The digest is deterministic, so two log lines about the same customer still correlate,
while the line no longer carries the value needed to look that customer up elsewhere.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import re
import sys

JSON_FORMAT = "json"

# Attributes `logging` puts on every record. Anything outside this set arrived through
# `extra=` at the call site and is the structured payload worth emitting.
_RESERVED = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name",
        "pathname", "process", "processName", "relativeCreated", "stack_info",
        "taskName", "thread", "threadName",
    }
)

# Log keys whose value is never emitted, whatever a call site passes. The list is
# deliberately short: it names the things that would be a disclosure rather than a
# clue, and everything else is masked or emitted as-is on purpose.
_NEVER_LOGGED = frozenset(
    {
        "password", "password_hash", "token", "access_token", "authorization",
        "signature", "secret", "jwt_secret_key", "razorpay_webhook_secret",
        "api_key", "gemini_api_key", "key_secret", "message_body",
    }
)

REDACTED = "<redacted>"
MASK_DIGEST_LENGTH = 12


def mask_identifier(value: str | None, *, prefix_length: int = 4) -> str | None:
    """Return a stable, non-reversible stand-in for a gateway identifier.

    Keeps a short readable prefix so an operator can tell a payment id from a
    customer id at a glance, and appends a truncated SHA-256 of the whole value so
    two lines about the same entity still join. ``None`` and empty stay themselves —
    an absent identifier is information, and inventing a digest for it would hide
    that the field was missing.

    This is masking, not anonymisation: an attacker holding a list of candidate ids
    can hash them and match. It removes the copy-and-paste path from a log line to a
    gateway dashboard, which is the realistic exposure for a log file.
    """
    if value is None:
        return None
    text = str(value)
    if not text:
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:MASK_DIGEST_LENGTH]
    return f"{text[:prefix_length]}***{digest}"


def redact(payload: dict[str, object]) -> dict[str, object]:
    """Replace values whose key names a secret. Applied to every emitted record."""
    return {
        key: (REDACTED if key.lower() in _NEVER_LOGGED else value)
        for key, value in payload.items()
    }


def safe_database_url(url: str) -> str:
    """Return a database URL with any embedded credentials removed.

    A PostgreSQL URL carries the password in its userinfo, so logging the URL as
    configured writes the database password into every log sink. The host and the
    database name are the operationally useful parts and are kept.
    """
    if "://" not in url:
        return url
    scheme, _, remainder = url.partition("://")
    if "@" not in remainder:
        return url
    userinfo, _, host = remainder.rpartition("@")
    user, _, password = userinfo.partition(":")
    if not password:
        return f"{scheme}://{user}@{host}"
    return f"{scheme}://{user}:{REDACTED}@{host}"


_CREDENTIAL_URL = re.compile(r"(?P<scheme>[a-zA-Z][\w+.-]*://)(?P<user>[^\s/:@]+):[^\s/@]+@")

# A secret carried as a query parameter. Google's Generative Language REST API takes
# `?key=<api key>`, so a failing request quoted verbatim would put the Gemini key into
# `tasks.last_error` and onto an operator's screen.
_CREDENTIAL_QUERY = re.compile(
    r"(?P<name>\b(?:key|api[-_]?key|token|access[-_]?token|secret|password|signature)=)"
    r"(?P<value>[^&\s\"']+)",
    re.IGNORECASE,
)

ERROR_TEXT_LIMIT = 1000


def safe_error_text(exc: BaseException, *, limit: int = ERROR_TEXT_LIMIT) -> str:
    """Format an exception for storage or display, without its embedded credentials.

    Third-party exception messages are not written with a log sink in mind. A
    SQLAlchemy connection error quotes the URL it dialled, which for PostgreSQL carries
    the password; an HTTP client error quotes the URL it called, which for Google's
    Generative Language API carries `?key=`. Both end up in ``tasks.last_error``, which
    operators read, so both shapes are stripped before the text is stored.

    Parameter values a driver interpolated into a failing statement are left alone.
    They are the payment and customer identifiers already stored in that same tenant's
    ``payment_events`` row, so removing them would cost an operator the diagnosis and
    disclose nothing new.
    """
    text = f"{type(exc).__name__}: {exc}"
    text = _CREDENTIAL_URL.sub(rf"\g<scheme>\g<user>:{REDACTED}@", text)
    return _CREDENTIAL_QUERY.sub(rf"\g<name>{REDACTED}", text)[:limit]


class JsonFormatter(logging.Formatter):
    """One JSON object per line: timestamp, level, logger, message, then extras."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(redact({k: v for k, v in record.__dict__.items() if k not in _RESERVED}))
        if record.exc_info:
            # The type and message, not the frames: a traceback in a log line is
            # noise, and an exception message can quote input the record should not.
            exc_type, exc_value = record.exc_info[0], record.exc_info[1]
            payload["error_type"] = getattr(exc_type, "__name__", str(exc_type))
            payload["error_message"] = str(exc_value)
        return json.dumps(payload, default=str, sort_keys=True)


def configure_logging(log_format: str, log_level: str = "INFO") -> bool:
    """Install the JSON handler when asked. Returns whether it was installed.

    Deliberately a no-op for any other value, including the empty default. A library
    that reconfigures the root logger on import breaks the host application's own
    setup, so this is called only from process entry points — the ``api:app`` module
    object uvicorn loads, and ``scripts/run_worker.py`` — never from a factory or a
    request path, and it does nothing unless a deployment asked for JSON.

    Existing root handlers are replaced rather than added to, so a deployment gets one
    JSON line per record instead of that line plus uvicorn's plain-text copy. That is
    exactly why it must not run anywhere but an entry point.
    """
    if log_format.strip().lower() != JSON_FORMAT:
        return False
    root = logging.getLogger()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.strip().upper(), logging.INFO))
    return True
