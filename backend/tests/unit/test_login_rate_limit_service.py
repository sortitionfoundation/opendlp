"""ABOUTME: Unit tests for login rate limiting service
ABOUTME: Tests Redis-based rate limiting for login attempts by email and IP address"""

import pytest
from redis import Redis

from opendlp.service_layer.exceptions import RateLimitExceeded
from opendlp.service_layer.login_rate_limit_service import (
    _KEY_PREFIX_EMAIL,
    _KEY_PREFIX_IP,
    check_login_rate_limit,
    record_failed_login,
)


@pytest.fixture
def redis_client():
    """Provide a real Redis client for testing, cleaning up rate limit keys after each test."""
    r = Redis(host="localhost", port=63792, decode_responses=True)
    yield r
    # Clean up all rate limit keys after each test
    for key in r.scan_iter(f"{_KEY_PREFIX_EMAIL}*"):
        r.delete(key)
    for key in r.scan_iter(f"{_KEY_PREFIX_IP}*"):
        r.delete(key)


class TestRecordFailedLogin:
    def test_increments_email_counter(self, redis_client):
        record_failed_login("test@example.com", "1.2.3.4", redis_client=redis_client)
        email_key = f"{_KEY_PREFIX_EMAIL}test@example.com"
        assert int(redis_client.get(email_key)) == 1

    def test_increments_ip_counter(self, redis_client):
        record_failed_login("test@example.com", "1.2.3.4", redis_client=redis_client)
        ip_key = f"{_KEY_PREFIX_IP}1.2.3.4"
        assert int(redis_client.get(ip_key)) == 1

    def test_increments_on_repeated_failures(self, redis_client):
        for _ in range(3):
            record_failed_login("test@example.com", "1.2.3.4", redis_client=redis_client)
        email_key = f"{_KEY_PREFIX_EMAIL}test@example.com"
        assert int(redis_client.get(email_key)) == 3

    def test_sets_ttl_on_keys(self, redis_client):
        record_failed_login("test@example.com", "1.2.3.4", window_minutes=15, redis_client=redis_client)
        email_key = f"{_KEY_PREFIX_EMAIL}test@example.com"
        ip_key = f"{_KEY_PREFIX_IP}1.2.3.4"
        # TTL should be set (allow some tolerance for execution time)
        assert redis_client.ttl(email_key) > 0
        assert redis_client.ttl(email_key) <= 15 * 60
        assert redis_client.ttl(ip_key) > 0
        assert redis_client.ttl(ip_key) <= 15 * 60

    def test_normalises_email_to_lowercase(self, redis_client):
        record_failed_login("Test@Example.COM", "1.2.3.4", redis_client=redis_client)
        email_key = f"{_KEY_PREFIX_EMAIL}test@example.com"
        assert int(redis_client.get(email_key)) == 1

    def test_different_emails_have_separate_counters(self, redis_client):
        record_failed_login("alice@example.com", "1.2.3.4", redis_client=redis_client)
        record_failed_login("bob@example.com", "1.2.3.4", redis_client=redis_client)
        assert int(redis_client.get(f"{_KEY_PREFIX_EMAIL}alice@example.com")) == 1
        assert int(redis_client.get(f"{_KEY_PREFIX_EMAIL}bob@example.com")) == 1

    def test_different_ips_have_separate_counters(self, redis_client):
        record_failed_login("test@example.com", "1.1.1.1", redis_client=redis_client)
        record_failed_login("test@example.com", "2.2.2.2", redis_client=redis_client)
        assert int(redis_client.get(f"{_KEY_PREFIX_IP}1.1.1.1")) == 1
        assert int(redis_client.get(f"{_KEY_PREFIX_IP}2.2.2.2")) == 1


class TestCheckLoginRateLimit:
    def test_allows_login_when_no_failures(self, redis_client):
        # Should not raise
        check_login_rate_limit("test@example.com", "1.2.3.4", redis_client=redis_client)

    def test_allows_login_under_email_limit(self, redis_client):
        for _ in range(4):
            record_failed_login("test@example.com", "1.2.3.4", redis_client=redis_client)
        # 4 failures with limit of 5 — should still be allowed
        check_login_rate_limit("test@example.com", "1.2.3.4", max_per_email=5, redis_client=redis_client)

    def test_blocks_login_at_email_limit(self, redis_client):
        for _ in range(5):
            record_failed_login("test@example.com", "1.2.3.4", redis_client=redis_client)
        with pytest.raises(RateLimitExceeded):
            check_login_rate_limit("test@example.com", "1.2.3.4", max_per_email=5, redis_client=redis_client)

    def test_blocks_login_at_ip_limit(self, redis_client):
        # Different emails, same IP — should hit the IP limit
        for i in range(20):
            record_failed_login(f"user{i}@example.com", "1.2.3.4", redis_client=redis_client)
        with pytest.raises(RateLimitExceeded):
            check_login_rate_limit("new@example.com", "1.2.3.4", max_per_ip=20, redis_client=redis_client)

    def test_email_limit_does_not_block_different_email(self, redis_client):
        for _ in range(5):
            record_failed_login("blocked@example.com", "1.2.3.4", redis_client=redis_client)
        # Different email should not be blocked (assuming IP limit not reached)
        check_login_rate_limit(
            "other@example.com", "5.6.7.8", max_per_email=5, max_per_ip=20, redis_client=redis_client
        )

    def test_ip_limit_does_not_block_different_ip(self, redis_client):
        for i in range(20):
            record_failed_login(f"user{i}@example.com", "1.2.3.4", redis_client=redis_client)
        # Different IP should not be blocked
        check_login_rate_limit("new@example.com", "5.6.7.8", max_per_ip=20, redis_client=redis_client)

    def test_rate_limit_exception_includes_retry_after(self, redis_client):
        for _ in range(5):
            record_failed_login("test@example.com", "1.2.3.4", redis_client=redis_client)
        with pytest.raises(RateLimitExceeded) as exc_info:
            check_login_rate_limit(
                "test@example.com", "1.2.3.4", max_per_email=5, window_minutes=15, redis_client=redis_client
            )
        assert exc_info.value.retry_after_seconds == 15 * 60

    def test_email_check_is_case_insensitive(self, redis_client):
        for _ in range(5):
            record_failed_login("Test@Example.COM", "1.2.3.4", redis_client=redis_client)
        with pytest.raises(RateLimitExceeded):
            check_login_rate_limit("test@example.com", "1.2.3.4", max_per_email=5, redis_client=redis_client)
