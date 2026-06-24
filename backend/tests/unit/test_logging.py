"""ABOUTME: Tests for logging.py configuration helpers.
ABOUTME: Verifies GunicornLogger.header_safe uses the shared sensitive-key denylist (issue 617)."""

from opendlp.logging import GunicornLogger


class TestHeaderSafe:
    def test_redacted_headers_are_unsafe(self) -> None:
        assert GunicornLogger.header_safe("Authorization") is False
        assert GunicornLogger.header_safe("Cookie") is False
        assert GunicornLogger.header_safe("X-API-Key") is False
        assert GunicornLogger.header_safe("X-Security-Token") is False

    def test_ordinary_headers_are_safe(self) -> None:
        assert GunicornLogger.header_safe("Accept") is True
        assert GunicornLogger.header_safe("Content-Type") is True
        assert GunicornLogger.header_safe("User-Agent") is True
