"""ABOUTME: End-to-end tests that emails/secrets are redacted in rendered log output.
ABOUTME: Exercises both the structlog path and the foreign (stdlib) path through censor_pii (issue 617)."""

import logging
from collections.abc import Iterator
from io import StringIO

import pytest
import structlog


@pytest.fixture
def capture_json_handler() -> Iterator[StringIO]:
    """Attach a JSON ProcessorFormatter handler wired exactly like logging.py.

    Yields the StringIO buffer the rendered log lines are written to, then
    removes the temporary handler again.
    """
    # Use the real foreign_pre_chain from logging.py so the foreign-path test
    # genuinely verifies that censor_pii is wired into the application config.
    from opendlp.logging import pre_chain

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=pre_chain,
        )
    )
    root = logging.getLogger()
    root.addHandler(handler)
    previous_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        yield stream
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


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
