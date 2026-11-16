"""ABOUTME: Redis-based rate limiting for the sign-up page's live password checks
ABOUTME: Caps the checks per IP, so the endpoint cannot be used to test passwords in bulk"""

import structlog
from redis import Redis

from opendlp.config import RedisCfg
from opendlp.service_layer.exceptions import RateLimitExceeded
from opendlp.translations import gettext as _

logger = structlog.get_logger(__name__)

# Redis key prefix for password check rate limiting
_KEY_PREFIX_IP = "password_check_ratelimit:ip:"

# Per-IP only, like the signup limit. The page asks once per pause in typing,
# and again when the email or a name changes, so one person signing up makes
# tens of checks; the ceiling leaves room for several people behind one office
# IP.
DEFAULT_MAX_CHECKS_PER_IP = 120
DEFAULT_WINDOW_MINUTES = 10


def _get_redis() -> Redis:
    """Get a Redis connection for rate limiting."""
    return RedisCfg.from_env().create_client(decode_responses=True)


def _ip_key(ip_address: str) -> str:
    """Build the Redis key for per-IP rate limiting."""
    return f"{_KEY_PREFIX_IP}{ip_address}"


def check_password_check_rate_limit(
    ip_address: str,
    max_per_ip: int = DEFAULT_MAX_CHECKS_PER_IP,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    redis_client: Redis | None = None,
) -> None:
    """Check whether a live password check is allowed under the per-IP rate limit.

    Args:
        ip_address: The IP address of the request.
        max_per_ip: Maximum checks allowed per IP in the window.
        window_minutes: Time window in minutes for counting checks.
        redis_client: Optional Redis client (for testing). If None, creates one.

    Raises:
        RateLimitExceeded: If the rate limit is exceeded.
    """
    r = redis_client or _get_redis()

    raw_count: bytes | str | None = r.get(_ip_key(ip_address))
    count = int(raw_count) if raw_count else 0
    if count >= max_per_ip:
        logger.warning("Password check rate limit exceeded for IP", ip_address=ip_address)
        raise RateLimitExceeded(
            operation=_("password check"),
            retry_after_seconds=window_minutes * 60,
        )


def record_password_check(
    ip_address: str,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    redis_client: Redis | None = None,
) -> None:
    """Count an allowed password check against the IP.

    A refused check is not counted, so a page that keeps asking while it is
    over the limit does not keep the limit in place: the counter expires one
    window after the last check that was answered.

    Args:
        ip_address: The IP address of the request.
        window_minutes: Time window in minutes (used as TTL).
        redis_client: Optional Redis client (for testing). If None, creates one.
    """
    r = redis_client or _get_redis()

    pipe = r.pipeline()
    key = _ip_key(ip_address)
    pipe.incr(key)
    pipe.expire(key, window_minutes * 60)
    pipe.execute()
