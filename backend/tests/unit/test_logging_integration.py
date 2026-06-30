"""ABOUTME: End-to-end tests that emails/secrets are redacted in rendered log output.
ABOUTME: Exercises both the structlog path and the foreign (stdlib) path through censor_pii (issue 617)."""

import logging
from io import StringIO

import structlog


def test_structlog_call_redacts_email(capture_json_handler: StringIO) -> None:
    structlog.get_logger("test").info("sent", to="a@b.com")
    output = capture_json_handler.getvalue()
    assert "a@b.com" not in output
    assert "[EMAIL_REDACTED]" in output


def test_stdlib_foreign_call_redacts_email(capture_json_handler: StringIO) -> None:
    logging.getLogger("third_party").warning("mail to a@b.com")
    output = capture_json_handler.getvalue()
    assert "a@b.com" not in output
    assert "[EMAIL_REDACTED]" in output
