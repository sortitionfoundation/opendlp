"""ABOUTME: Shared fixtures for unit tests.
ABOUTME: Provides capture_json_handler to assert on rendered, redacted log output (issue 617)."""

import logging
from collections.abc import Iterator
from io import StringIO

import pytest
import structlog


@pytest.fixture
def capture_json_handler() -> Iterator[StringIO]:
    """Attach a JSON ProcessorFormatter handler wired exactly like logging.py.

    Yields the StringIO buffer the rendered log lines are written to, then
    removes the temporary handler again. Uses the real foreign_pre_chain from
    logging.py so redaction wiring is genuinely exercised.
    """
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
