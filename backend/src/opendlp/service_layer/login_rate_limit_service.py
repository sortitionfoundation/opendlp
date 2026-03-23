"""ABOUTME: Redis-based rate limiting for login attempts
ABOUTME: Tracks failed login attempts by email and IP address to prevent brute force attacks"""

import logging

from redis import Redis

from opendlp.config import RedisCfg
from opendlp.service_layer.exceptions import RateLimitExceeded
from opendlp.translations import gettext as _

logger = logging.getLogger(__name__)

# Redis key prefixes for login rate limiting
_KEY_PREFIX_EMAIL = "login_ratelimit:email:"
_KEY_PREFIX_IP = "login_ratelimit:ip:"

# Default limits (can be overridden via config)
DEFAULT_MAX_ATTEMPTS_PER_EMAIL = 5
DEFAULT_MAX_ATTEMPTS_PER_IP = 20
DEFAULT_WINDOW_MINUTES = 15


def _get_redis() -> Redis:
    """Get a Redis connection for rate limiting."""
    cfg = RedisCfg.from_env()
    return Redis(host=cfg.host, port=cfg.port, db=cfg.db, decode_responses=True)


def _email_key(email: str) -> str:
    """Build the Redis key for per-email rate limiting."""
    return f"{_KEY_PREFIX_EMAIL}{email.strip().lower()}"


def _ip_key(ip_address: str) -> str:
    """Build the Redis key for per-IP rate limiting."""
    return f"{_KEY_PREFIX_IP}{ip_address}"


def check_login_rate_limit(
    email: str,
    ip_address: str,
    max_per_email: int = DEFAULT_MAX_ATTEMPTS_PER_EMAIL,
    max_per_ip: int = DEFAULT_MAX_ATTEMPTS_PER_IP,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    redis_client: Redis | None = None,
) -> None:
    """Check whether a login attempt is allowed under rate limits.

    Raises RateLimitExceeded if either the per-email or per-IP limit
    has been reached within the sliding window.

    Args:
        email: The email address being used to log in.
        ip_address: The IP address of the request.
        max_per_email: Maximum failed attempts allowed per email.
        max_per_ip: Maximum failed attempts allowed per IP.
        window_minutes: Time window in minutes for counting attempts.
        redis_client: Optional Redis client (for testing). If None, creates one.

    Raises:
        RateLimitExceeded: If rate limit is exceeded.
    """
    r = redis_client or _get_redis()
    retry_after_seconds = window_minutes * 60

    raw_email_count: str | None = r.get(_email_key(email))  # type: ignore[assignment]
    email_count = int(raw_email_count) if raw_email_count else 0
    if email_count >= max_per_email:
        logger.warning("Login rate limit exceeded for email: %s", email)
        raise RateLimitExceeded(
            operation=_("login"),
            retry_after_seconds=retry_after_seconds,
        )

    raw_ip_count: str | None = r.get(_ip_key(ip_address))  # type: ignore[assignment]
    ip_count = int(raw_ip_count) if raw_ip_count else 0
    if ip_count >= max_per_ip:
        logger.warning("Login rate limit exceeded for IP: %s", ip_address)
        raise RateLimitExceeded(
            operation=_("login"),
            retry_after_seconds=retry_after_seconds,
        )


def record_failed_login(
    email: str,
    ip_address: str,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    redis_client: Redis | None = None,
) -> None:
    """Record a failed login attempt, incrementing both email and IP counters.

    Each counter uses a TTL equal to the rate limit window so that counters
    automatically expire without needing manual cleanup.

    Args:
        email: The email address that was used.
        ip_address: The IP address of the request.
        window_minutes: Time window in minutes (used as TTL).
        redis_client: Optional Redis client (for testing). If None, creates one.
    """
    r = redis_client or _get_redis()
    ttl_seconds = window_minutes * 60

    pipe = r.pipeline()

    ek = _email_key(email)
    pipe.incr(ek)
    pipe.expire(ek, ttl_seconds)

    ik = _ip_key(ip_address)
    pipe.incr(ik)
    pipe.expire(ik, ttl_seconds)

    pipe.execute()
