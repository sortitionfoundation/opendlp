"""ABOUTME: Unit tests for login rate limiting service
ABOUTME: Tests Redis-based rate limiting for login attempts by email and IP address"""

import pytest

from opendlp.service_layer.exceptions import RateLimitExceeded
from opendlp.service_layer.login_rate_limit_service import (
    _KEY_PREFIX_EMAIL,
    _KEY_PREFIX_IP,
    check_login_rate_limit,
    record_failed_login,
)


@pytest.fixture(autouse=True)
def clean_redis(test_redis_client):
    """Flush the per-worker Redis database before each test."""
    test_redis_client.flushdb()
    yield
    test_redis_client.flushdb()


class TestRecordFailedLogin:
    def test_increments_email_counter(self, test_redis_client):
        record_failed_login("test@example.com", "1.2.3.4", redis_client=test_redis_client)
        email_key = f"{_KEY_PREFIX_EMAIL}test@example.com"
        assert int(test_redis_client.get(email_key)) == 1

    def test_increments_ip_counter(self, test_redis_client):
        record_failed_login("test@example.com", "1.2.3.4", redis_client=test_redis_client)
        ip_key = f"{_KEY_PREFIX_IP}1.2.3.4"
        assert int(test_redis_client.get(ip_key)) == 1

    def test_increments_on_repeated_failures(self, test_redis_client):
        for _ in range(3):
            record_failed_login("test@example.com", "1.2.3.4", redis_client=test_redis_client)
        email_key = f"{_KEY_PREFIX_EMAIL}test@example.com"
        assert int(test_redis_client.get(email_key)) == 3

    def test_sets_ttl_on_keys(self, test_redis_client):
        record_failed_login("test@example.com", "1.2.3.4", window_minutes=15, redis_client=test_redis_client)
        email_key = f"{_KEY_PREFIX_EMAIL}test@example.com"
        ip_key = f"{_KEY_PREFIX_IP}1.2.3.4"
        # TTL should be set (allow some tolerance for execution time)
        assert test_redis_client.ttl(email_key) > 0
        assert test_redis_client.ttl(email_key) <= 15 * 60
        assert test_redis_client.ttl(ip_key) > 0
        assert test_redis_client.ttl(ip_key) <= 15 * 60

    def test_normalises_email_to_lowercase(self, test_redis_client):
        record_failed_login("Test@Example.COM", "1.2.3.4", redis_client=test_redis_client)
        email_key = f"{_KEY_PREFIX_EMAIL}test@example.com"
        assert int(test_redis_client.get(email_key)) == 1

    def test_different_emails_have_separate_counters(self, test_redis_client):
        record_failed_login("alice@example.com", "1.2.3.4", redis_client=test_redis_client)
        record_failed_login("bob@example.com", "1.2.3.4", redis_client=test_redis_client)
        assert int(test_redis_client.get(f"{_KEY_PREFIX_EMAIL}alice@example.com")) == 1
        assert int(test_redis_client.get(f"{_KEY_PREFIX_EMAIL}bob@example.com")) == 1

    def test_different_ips_have_separate_counters(self, test_redis_client):
        record_failed_login("test@example.com", "1.1.1.1", redis_client=test_redis_client)
        record_failed_login("test@example.com", "2.2.2.2", redis_client=test_redis_client)
        assert int(test_redis_client.get(f"{_KEY_PREFIX_IP}1.1.1.1")) == 1
        assert int(test_redis_client.get(f"{_KEY_PREFIX_IP}2.2.2.2")) == 1


class TestCheckLoginRateLimit:
    def test_allows_login_when_no_failures(self, test_redis_client):
        # Should not raise
        check_login_rate_limit("test@example.com", "1.2.3.4", redis_client=test_redis_client)

    def test_allows_login_under_email_limit(self, test_redis_client):
        for _ in range(4):
            record_failed_login("test@example.com", "1.2.3.4", redis_client=test_redis_client)
        # 4 failures with limit of 5 — should still be allowed
        check_login_rate_limit("test@example.com", "1.2.3.4", max_per_email=5, redis_client=test_redis_client)

    def test_blocks_login_at_email_limit(self, test_redis_client):
        for _ in range(5):
            record_failed_login("test@example.com", "1.2.3.4", redis_client=test_redis_client)
        with pytest.raises(RateLimitExceeded):
            check_login_rate_limit("test@example.com", "1.2.3.4", max_per_email=5, redis_client=test_redis_client)

    def test_blocks_login_at_ip_limit(self, test_redis_client):
        # Different emails, same IP — should hit the IP limit
        for i in range(20):
            record_failed_login(f"user{i}@example.com", "1.2.3.4", redis_client=test_redis_client)
        with pytest.raises(RateLimitExceeded):
            check_login_rate_limit("new@example.com", "1.2.3.4", max_per_ip=20, redis_client=test_redis_client)

    def test_email_limit_does_not_block_different_email(self, test_redis_client):
        for _ in range(5):
            record_failed_login("blocked@example.com", "1.2.3.4", redis_client=test_redis_client)
        # Different email should not be blocked (assuming IP limit not reached)
        check_login_rate_limit(
            "other@example.com", "5.6.7.8", max_per_email=5, max_per_ip=20, redis_client=test_redis_client
        )

    def test_ip_limit_does_not_block_different_ip(self, test_redis_client):
        for i in range(20):
            record_failed_login(f"user{i}@example.com", "1.2.3.4", redis_client=test_redis_client)
        # Different IP should not be blocked
        check_login_rate_limit("new@example.com", "5.6.7.8", max_per_ip=20, redis_client=test_redis_client)

    def test_rate_limit_exception_includes_retry_after(self, test_redis_client):
        for _ in range(5):
            record_failed_login("test@example.com", "1.2.3.4", redis_client=test_redis_client)
        with pytest.raises(RateLimitExceeded) as exc_info:
            check_login_rate_limit(
                "test@example.com", "1.2.3.4", max_per_email=5, window_minutes=15, redis_client=test_redis_client
            )
        assert exc_info.value.retry_after_seconds == 15 * 60

    def test_email_check_is_case_insensitive(self, test_redis_client):
        for _ in range(5):
            record_failed_login("Test@Example.COM", "1.2.3.4", redis_client=test_redis_client)
        with pytest.raises(RateLimitExceeded):
            check_login_rate_limit("test@example.com", "1.2.3.4", max_per_email=5, redis_client=test_redis_client)
