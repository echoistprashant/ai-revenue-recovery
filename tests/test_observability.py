"""Tests for structured logging and the masking of identifiers in log lines.

The property under test is narrow but easy to lose: a log line may carry enough to
correlate and diagnose, and not enough to look a customer up in the gateway dashboard
or to authenticate as anyone.
"""

import json
import logging
from pathlib import Path

from revenue_recovery.observability import (
    REDACTED,
    JsonFormatter,
    configure_logging,
    mask_identifier,
    redact,
    safe_database_url,
    safe_error_text,
)


def record(message: str = "something happened", **extra) -> logging.LogRecord:
    made = logging.LogRecord("test", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(made, key, value)
    return made


def formatted(**extra) -> dict:
    return json.loads(JsonFormatter().format(record(**extra)))


# --- masking ------------------------------------------------------------------


def test_a_masked_identifier_is_stable_and_does_not_contain_the_original() -> None:
    first = mask_identifier("pay_MkL9x2QwErTy")
    assert first == mask_identifier("pay_MkL9x2QwErTy")
    assert "MkL9x2QwErTy" not in first
    # The prefix stays readable so an operator can tell one kind of id from another.
    assert first.startswith("pay_")


def test_different_identifiers_mask_differently() -> None:
    assert mask_identifier("cust_aaa") != mask_identifier("cust_bbb")


def test_absent_and_empty_identifiers_stay_themselves() -> None:
    """An id that was missing is a fact worth keeping; a digest would hide it."""
    assert mask_identifier(None) is None
    assert mask_identifier("") == ""


def test_a_database_url_is_logged_without_its_password() -> None:
    masked = safe_database_url("postgresql+psycopg://revenue:s3cr3t-pw@db.internal:5432/recovery")
    assert "s3cr3t-pw" not in masked
    assert "db.internal:5432/recovery" in masked
    assert "revenue" in masked


def test_a_sqlite_url_is_left_alone() -> None:
    assert safe_database_url("sqlite:///data/revenue_recovery.db") == "sqlite:///data/revenue_recovery.db"


def test_redact_replaces_secret_named_keys_only() -> None:
    cleaned = redact({"password": "hunter2", "token": "abc", "event_id": 7, "action": "RETRY_NOW"})
    assert cleaned["password"] == REDACTED
    assert cleaned["token"] == REDACTED
    assert cleaned["event_id"] == 7
    assert cleaned["action"] == "RETRY_NOW"


# --- exception text that gets stored or shown ---------------------------------
#
# `tasks.last_error` and the analyst's tool-failure reply both hold a third-party
# exception message. Those messages were not written with a log sink in mind.


class Boom(Exception):
    pass


def test_a_connection_error_loses_the_database_password() -> None:
    text = safe_error_text(
        Boom("could not connect to postgresql+psycopg://revenue:s3cr3t-pw@db.internal:5432/recovery")
    )
    assert "s3cr3t-pw" not in text
    assert "db.internal:5432/recovery" in text
    assert text.startswith("Boom: ")


def test_an_api_key_in_a_query_string_is_removed() -> None:
    """Google's Generative Language REST API takes the key as `?key=`."""
    text = safe_error_text(Boom("GET https://generativelanguage.googleapis.com/v1beta/x?key=AIzaSyREAL -> 400"))
    assert "AIzaSyREAL" not in text
    assert "generativelanguage.googleapis.com" in text


def test_other_secret_named_query_parameters_go_too() -> None:
    text = safe_error_text(Boom("auth failed api_key=abc&token=def&signature=ghi"))
    assert "abc" not in text and "def" not in text and "ghi" not in text


def test_a_word_merely_ending_in_key_is_not_a_credential() -> None:
    assert "banana" in safe_error_text(Boom("the monkey=banana was fine"))


def test_driver_interpolated_identifiers_are_kept() -> None:
    """They are already in this tenant's own payment_events row; removing them would
    cost the operator the diagnosis and disclose nothing new."""
    text = safe_error_text(Boom("UNIQUE constraint failed: payment_events.payment_id [pay_abc]"))
    assert "pay_abc" in text


def test_the_text_is_bounded_so_it_fits_the_column() -> None:
    assert len(safe_error_text(Boom("x" * 5000))) == 1000
    assert len(safe_error_text(Boom("x" * 5000), limit=120)) == 120


# --- the JSON formatter -------------------------------------------------------


def test_a_record_becomes_one_json_object_with_its_extras() -> None:
    payload = formatted(event_id=11, action="RETRY_NOW")
    assert payload["message"] == "something happened"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"
    assert payload["event_id"] == 11
    assert payload["action"] == "RETRY_NOW"
    assert payload["timestamp"].endswith("+00:00")


def test_the_formatter_redacts_a_secret_passed_through_extra() -> None:
    """Defence in depth: no call site should pass a secret, and if one does it still
    does not reach the log sink."""
    payload = formatted(razorpay_webhook_secret="real-secret", signature="deadbeef")
    assert payload["razorpay_webhook_secret"] == REDACTED
    assert payload["signature"] == REDACTED


def test_an_exception_is_reduced_to_its_type_and_message() -> None:
    logger = logging.getLogger("test")
    try:
        raise ValueError("bad input 42")
    except ValueError:
        made = logger.makeRecord(
            "test", logging.ERROR, __file__, 1, "failed", None, __import__("sys").exc_info()
        )
    payload = json.loads(JsonFormatter().format(made))
    assert payload["error_type"] == "ValueError"
    assert payload["error_message"] == "bad input 42"
    assert "Traceback" not in json.dumps(payload)


# --- configuration is opt-in --------------------------------------------------


def test_configure_logging_does_nothing_unless_json_was_asked_for() -> None:
    """A library that reconfigures the root logger on import breaks its host."""
    assert configure_logging("") is False
    assert configure_logging("text") is False


def test_configure_logging_installs_the_json_handler_when_asked() -> None:
    root = logging.getLogger()
    original = list(root.handlers)
    original_level = root.level
    try:
        assert configure_logging("JSON", "warning") is True
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
        assert root.level == logging.WARNING
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in original:
            root.addHandler(handler)
        root.setLevel(original_level)


# --- a migration must not switch the application's logging off ------------------


def test_a_programmatic_migration_leaves_existing_loggers_enabled(tmp_path, monkeypatch) -> None:
    """`logging.config.fileConfig` disables pre-existing loggers by default.

    Alembic calls it from `migrations/env.py`. Driven in-process — a deploy script, or
    this test session — the default would leave every logger created before the
    migration marked disabled, so the application would run on silently with no log
    output and no error to explain it. `disable_existing_loggers=False` is what stops it.
    """
    from alembic import command
    from alembic.config import Config

    repo_root = Path(__file__).resolve().parents[1]
    logger = logging.getLogger("revenue_recovery.canary")
    assert logger.disabled is False

    monkeypatch.setenv("REVENUE_RECOVERY_DATABASE", str(tmp_path / "logging_probe.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "migrations"))
    command.upgrade(config, "head")

    assert logger.disabled is False, (
        "The migration disabled a logger that existed before it ran; "
        "migrations/env.py must pass disable_existing_loggers=False."
    )
