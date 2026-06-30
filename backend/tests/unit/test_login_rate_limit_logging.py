"""ABOUTME: Tests that login rate-limit logging hashes the email instead of logging it raw.
ABOUTME: Uses a fake Redis so it does not require a running Redis (issue 617)."""

from io import StringIO

import pytest

from opendlp.log_redaction import hash_email
from opendlp.service_layer.exceptions import RateLimitExceeded
from opendlp.service_layer.login_rate_limit_service import check_login_rate_limit


class _FakeRedisAtEmailLimit:
    """Returns a count at/over the limit for the email key, zero otherwise."""

    def get(self, key: str) -> str | None:
        return "5" if key.startswith("login_ratelimit:email:") else None


def test_rate_limit_log_hashes_email(capture_json_handler: StringIO) -> None:
    with pytest.raises(RateLimitExceeded):
        check_login_rate_limit("alice@example.com", "1.2.3.4", redis_client=_FakeRedisAtEmailLimit())

    output = capture_json_handler.getvalue()
    assert "alice@example.com" not in output
    assert hash_email("alice@example.com") in output
