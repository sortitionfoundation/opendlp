"""ABOUTME: Redis-based rate limiting for account signup
ABOUTME: Caps account creations per IP so open signup cannot be used for mass account creation"""

import structlog
from redis import Redis

from opendlp.config import RedisCfg
from opendlp.service_layer.exceptions import RateLimitExceeded
from opendlp.translations import gettext as _

logger = structlog.get_logger(__name__)

# Redis key prefix for registration rate limiting
_KEY_PREFIX_IP = "signup_ratelimit:ip:"

# Per-IP only: a mass registration attack varies the email address freely, so a
# per-email counter would never fire, while legitimate invited signups from one
# office IP stay far under this ceiling.
DEFAULT_MAX_SIGNUPS_PER_IP = 10
DEFAULT_WINDOW_MINUTES = 60


def _get_redis() -> Redis:
    """Get a Redis connection for rate limiting."""
    return RedisCfg.from_env().create_client(decode_responses=True)


def _ip_key(ip_address: str) -> str:
    """Build the Redis key for per-IP rate limiting."""
    return f"{_KEY_PREFIX_IP}{ip_address}"


def check_signup_rate_limit(
    ip_address: str,
    max_per_ip: int = DEFAULT_MAX_SIGNUPS_PER_IP,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    redis_client: Redis | None = None,
) -> None:
    """Check whether an account signup is allowed under the per-IP rate limit.

    Args:
        ip_address: The IP address of the request.
        max_per_ip: Maximum account creations allowed per IP in the window.
        window_minutes: Time window in minutes for counting registrations.
        redis_client: Optional Redis client (for testing). If None, creates one.

    Raises:
        RateLimitExceeded: If the rate limit is exceeded.
    """
    r = redis_client or _get_redis()

    raw_count: bytes | str | None = r.get(_ip_key(ip_address))
    count = int(raw_count) if raw_count else 0
    if count >= max_per_ip:
        logger.warning("Signup rate limit exceeded for IP", ip_address=ip_address)
        raise RateLimitExceeded(
            operation=_("signup"),
            retry_after_seconds=window_minutes * 60,
        )


def record_signup(
    ip_address: str,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    redis_client: Redis | None = None,
) -> None:
    """Record a successful account creation against the IP's counter.

    Only creations count, not failed form submissions - the resource being
    protected is the account plus its confirmation email, and counting failures
    would let typos lock a shared IP out of registering at all.

    The counter's TTL equals the window, so it expires without manual cleanup.

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
