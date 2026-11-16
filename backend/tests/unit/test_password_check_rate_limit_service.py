"""ABOUTME: Unit tests for the live password check's rate limiting
ABOUTME: Tests Redis-based per-IP counting of the sign-up page's password checks"""

import pytest

from opendlp.service_layer.exceptions import RateLimitExceeded
from opendlp.service_layer.password_check_rate_limit_service import (
    _KEY_PREFIX_IP,
    check_password_check_rate_limit,
    record_password_check,
)

pytestmark = pytest.mark.requires_redis


@pytest.fixture(autouse=True)
def clean_redis(test_redis_client):
    """Start and end each test with an empty Redis database."""
    test_redis_client.flushdb()
    yield
    test_redis_client.flushdb()


class TestRecordPasswordCheck:
    def test_increments_ip_counter(self, test_redis_client):
        record_password_check("1.2.3.4", redis_client=test_redis_client)
        assert int(test_redis_client.get(f"{_KEY_PREFIX_IP}1.2.3.4")) == 1

    def test_increments_on_repeated_checks(self, test_redis_client):
        for _ in range(3):
            record_password_check("1.2.3.4", redis_client=test_redis_client)
        assert int(test_redis_client.get(f"{_KEY_PREFIX_IP}1.2.3.4")) == 3

    def test_sets_ttl_on_key(self, test_redis_client):
        record_password_check("1.2.3.4", window_minutes=10, redis_client=test_redis_client)
        ttl = test_redis_client.ttl(f"{_KEY_PREFIX_IP}1.2.3.4")
        assert 0 < ttl <= 10 * 60

    def test_different_ips_have_separate_counters(self, test_redis_client):
        record_password_check("1.2.3.4", redis_client=test_redis_client)
        record_password_check("5.6.7.8", redis_client=test_redis_client)
        assert int(test_redis_client.get(f"{_KEY_PREFIX_IP}1.2.3.4")) == 1
        assert int(test_redis_client.get(f"{_KEY_PREFIX_IP}5.6.7.8")) == 1


class TestCheckPasswordCheckRateLimit:
    def test_allows_when_no_checks_recorded(self, test_redis_client):
        check_password_check_rate_limit("1.2.3.4", max_per_ip=1, redis_client=test_redis_client)

    def test_allows_when_under_limit(self, test_redis_client):
        record_password_check("1.2.3.4", redis_client=test_redis_client)
        check_password_check_rate_limit("1.2.3.4", max_per_ip=2, redis_client=test_redis_client)

    def test_blocks_when_limit_reached(self, test_redis_client):
        for _ in range(2):
            record_password_check("1.2.3.4", redis_client=test_redis_client)
        with pytest.raises(RateLimitExceeded) as excinfo:
            check_password_check_rate_limit("1.2.3.4", max_per_ip=2, window_minutes=10, redis_client=test_redis_client)
        assert excinfo.value.retry_after_seconds == 10 * 60

    def test_other_ips_are_not_blocked(self, test_redis_client):
        for _ in range(2):
            record_password_check("1.2.3.4", redis_client=test_redis_client)
        check_password_check_rate_limit("5.6.7.8", max_per_ip=2, redis_client=test_redis_client)
