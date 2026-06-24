"""ABOUTME: Unit tests for registration bot protection rate limiting service
ABOUTME: Tests Redis-based rate limiting for registration submissions by IP and email"""

import pytest

from opendlp.service_layer.exceptions import RateLimitExceeded
from opendlp.service_layer.registration_bot_protection_service import (
    _KEY_PREFIX_EMAIL,
    _KEY_PREFIX_IP,
    check_registration_rate_limit,
    record_registration_submission,
)

pytestmark = pytest.mark.requires_redis


@pytest.fixture(autouse=True)
def clean_redis(test_redis_client):
    test_redis_client.flushdb()
    yield
    test_redis_client.flushdb()


class TestRecordRegistrationSubmission:
    def test_increments_ip_counter(self, test_redis_client):
        record_registration_submission("1.2.3.4", "test@example.com", redis_client=test_redis_client)
        ip_key = f"{_KEY_PREFIX_IP}1.2.3.4"
        assert int(test_redis_client.get(ip_key)) == 1

    def test_increments_email_counter(self, test_redis_client):
        record_registration_submission("1.2.3.4", "test@example.com", redis_client=test_redis_client)
        email_key = f"{_KEY_PREFIX_EMAIL}test@example.com"
        assert int(test_redis_client.get(email_key)) == 1

    def test_increments_on_repeated_submissions(self, test_redis_client):
        for _ in range(3):
            record_registration_submission("1.2.3.4", "test@example.com", redis_client=test_redis_client)
        ip_key = f"{_KEY_PREFIX_IP}1.2.3.4"
        email_key = f"{_KEY_PREFIX_EMAIL}test@example.com"
        assert int(test_redis_client.get(ip_key)) == 3
        assert int(test_redis_client.get(email_key)) == 3

    def test_sets_ip_ttl(self, test_redis_client):
        record_registration_submission(
            "1.2.3.4", "test@example.com", ip_window_minutes=60, redis_client=test_redis_client
        )
        ip_key = f"{_KEY_PREFIX_IP}1.2.3.4"
        assert test_redis_client.ttl(ip_key) > 0
        assert test_redis_client.ttl(ip_key) <= 60 * 60

    def test_sets_email_ttl(self, test_redis_client):
        record_registration_submission(
            "1.2.3.4", "test@example.com", email_window_minutes=1440, redis_client=test_redis_client
        )
        email_key = f"{_KEY_PREFIX_EMAIL}test@example.com"
        assert test_redis_client.ttl(email_key) > 0
        assert test_redis_client.ttl(email_key) <= 1440 * 60

    def test_ip_and_email_use_separate_windows(self, test_redis_client):
        record_registration_submission(
            "1.2.3.4",
            "test@example.com",
            ip_window_minutes=60,
            email_window_minutes=1440,
            redis_client=test_redis_client,
        )
        ip_key = f"{_KEY_PREFIX_IP}1.2.3.4"
        email_key = f"{_KEY_PREFIX_EMAIL}test@example.com"
        ip_ttl = test_redis_client.ttl(ip_key)
        email_ttl = test_redis_client.ttl(email_key)
        assert ip_ttl <= 60 * 60
        assert email_ttl > 60 * 60

    def test_normalises_email_to_lowercase(self, test_redis_client):
        record_registration_submission("1.2.3.4", "Test@Example.COM", redis_client=test_redis_client)
        email_key = f"{_KEY_PREFIX_EMAIL}test@example.com"
        assert int(test_redis_client.get(email_key)) == 1

    def test_different_ips_have_separate_counters(self, test_redis_client):
        record_registration_submission("1.1.1.1", "test@example.com", redis_client=test_redis_client)
        record_registration_submission("2.2.2.2", "test@example.com", redis_client=test_redis_client)
        assert int(test_redis_client.get(f"{_KEY_PREFIX_IP}1.1.1.1")) == 1
        assert int(test_redis_client.get(f"{_KEY_PREFIX_IP}2.2.2.2")) == 1

    def test_different_emails_have_separate_counters(self, test_redis_client):
        record_registration_submission("1.2.3.4", "alice@example.com", redis_client=test_redis_client)
        record_registration_submission("1.2.3.4", "bob@example.com", redis_client=test_redis_client)
        assert int(test_redis_client.get(f"{_KEY_PREFIX_EMAIL}alice@example.com")) == 1
        assert int(test_redis_client.get(f"{_KEY_PREFIX_EMAIL}bob@example.com")) == 1


class TestCheckRegistrationRateLimit:
    def test_allows_submission_with_no_prior_activity(self, test_redis_client):
        # Should not raise
        check_registration_rate_limit("1.2.3.4", "test@example.com", redis_client=test_redis_client)

    def test_allows_submission_under_ip_limit(self, test_redis_client):
        for _ in range(29):
            record_registration_submission("1.2.3.4", f"user{_}@example.com", redis_client=test_redis_client)
        # 29 submissions with limit of 30 — should still be allowed
        check_registration_rate_limit("1.2.3.4", "new@example.com", max_per_ip=30, redis_client=test_redis_client)

    def test_blocks_at_ip_limit(self, test_redis_client):
        for i in range(30):
            record_registration_submission("1.2.3.4", f"user{i}@example.com", redis_client=test_redis_client)
        with pytest.raises(RateLimitExceeded):
            check_registration_rate_limit("1.2.3.4", "new@example.com", max_per_ip=30, redis_client=test_redis_client)

    def test_allows_submission_under_email_limit(self, test_redis_client):
        for _ in range(4):
            record_registration_submission("1.2.3.4", "test@example.com", redis_client=test_redis_client)
        # 4 submissions with limit of 5 — should still be allowed
        check_registration_rate_limit("1.2.3.4", "test@example.com", max_per_email=5, redis_client=test_redis_client)

    def test_blocks_at_email_limit(self, test_redis_client):
        for _ in range(5):
            record_registration_submission("1.2.3.4", "test@example.com", redis_client=test_redis_client)
        with pytest.raises(RateLimitExceeded):
            check_registration_rate_limit(
                "1.2.3.4", "test@example.com", max_per_email=5, redis_client=test_redis_client
            )

    def test_ip_limit_does_not_affect_different_ip(self, test_redis_client):
        for i in range(30):
            record_registration_submission("1.2.3.4", f"user{i}@example.com", redis_client=test_redis_client)
        # Different IP should not be blocked
        check_registration_rate_limit("5.6.7.8", "new@example.com", max_per_ip=30, redis_client=test_redis_client)

    def test_email_limit_does_not_affect_different_email(self, test_redis_client):
        for _ in range(5):
            record_registration_submission("1.2.3.4", "blocked@example.com", redis_client=test_redis_client)
        # Different email should not be blocked (assuming IP limit not reached)
        check_registration_rate_limit(
            "5.6.7.8", "other@example.com", max_per_ip=30, max_per_email=5, redis_client=test_redis_client
        )

    def test_email_check_is_case_insensitive(self, test_redis_client):
        for _ in range(5):
            record_registration_submission("1.2.3.4", "Test@Example.COM", redis_client=test_redis_client)
        with pytest.raises(RateLimitExceeded):
            check_registration_rate_limit(
                "1.2.3.4", "test@example.com", max_per_email=5, redis_client=test_redis_client
            )

    def test_exception_includes_retry_after_seconds(self, test_redis_client):
        for _ in range(5):
            record_registration_submission("1.2.3.4", "test@example.com", redis_client=test_redis_client)
        with pytest.raises(RateLimitExceeded) as exc_info:
            check_registration_rate_limit(
                "1.2.3.4",
                "test@example.com",
                max_per_email=5,
                email_window_minutes=1440,
                redis_client=test_redis_client,
            )
        assert exc_info.value.retry_after_seconds == 1440 * 60
