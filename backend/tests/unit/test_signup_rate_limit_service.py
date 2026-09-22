"""ABOUTME: Unit tests for registration rate limiting service
ABOUTME: Tests Redis-based per-IP rate limiting of account signups"""

import pytest

from opendlp.service_layer.exceptions import RateLimitExceeded
from opendlp.service_layer.signup_rate_limit_service import (
    _KEY_PREFIX_IP,
    check_signup_rate_limit,
    record_signup,
)

pytestmark = pytest.mark.requires_redis


@pytest.fixture(autouse=True)
def clean_redis(test_redis_client):
    """Flush the per-worker Redis database before each test."""
    test_redis_client.flushdb()
    yield
    test_redis_client.flushdb()


class TestRecordRegistration:
    def test_increments_ip_counter(self, test_redis_client):
        record_signup("1.2.3.4", redis_client=test_redis_client)
        assert int(test_redis_client.get(f"{_KEY_PREFIX_IP}1.2.3.4")) == 1

    def test_increments_on_repeated_registrations(self, test_redis_client):
        for _ in range(3):
            record_signup("1.2.3.4", redis_client=test_redis_client)
        assert int(test_redis_client.get(f"{_KEY_PREFIX_IP}1.2.3.4")) == 3

    def test_sets_ttl_on_key(self, test_redis_client):
        record_signup("1.2.3.4", window_minutes=60, redis_client=test_redis_client)
        ttl = test_redis_client.ttl(f"{_KEY_PREFIX_IP}1.2.3.4")
        assert 0 < ttl <= 60 * 60

    def test_different_ips_have_separate_counters(self, test_redis_client):
        record_signup("1.2.3.4", redis_client=test_redis_client)
        record_signup("5.6.7.8", redis_client=test_redis_client)
        assert int(test_redis_client.get(f"{_KEY_PREFIX_IP}1.2.3.4")) == 1
        assert int(test_redis_client.get(f"{_KEY_PREFIX_IP}5.6.7.8")) == 1


class TestCheckRegistrationRateLimit:
    def test_allows_when_under_limit(self, test_redis_client):
        record_signup("1.2.3.4", redis_client=test_redis_client)
        check_signup_rate_limit("1.2.3.4", max_per_ip=2, redis_client=test_redis_client)

    def test_allows_when_no_registrations_recorded(self, test_redis_client):
        check_signup_rate_limit("1.2.3.4", max_per_ip=1, redis_client=test_redis_client)

    def test_blocks_when_limit_reached(self, test_redis_client):
        for _ in range(2):
            record_signup("1.2.3.4", redis_client=test_redis_client)
        with pytest.raises(RateLimitExceeded):
            check_signup_rate_limit("1.2.3.4", max_per_ip=2, redis_client=test_redis_client)

    def test_other_ips_are_not_blocked(self, test_redis_client):
        for _ in range(2):
            record_signup("1.2.3.4", redis_client=test_redis_client)
        check_signup_rate_limit("5.6.7.8", max_per_ip=2, redis_client=test_redis_client)
