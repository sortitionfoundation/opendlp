# ABOUTME: Redis-based rate limiting for registration form submissions
# ABOUTME: Tracks registration attempts by IP and email address to prevent bot abuse

import structlog
from redis import Redis

from opendlp.config import RedisCfg
from opendlp.log_redaction import hash_email
from opendlp.service_layer.exceptions import RateLimitExceeded
from opendlp.translations import gettext as _

logger = structlog.get_logger(__name__)

_KEY_PREFIX_IP = "reg_ratelimit:ip:"
_KEY_PREFIX_EMAIL = "reg_ratelimit:email:"

DEFAULT_MAX_PER_IP = 30
DEFAULT_MAX_PER_EMAIL = 5
DEFAULT_IP_WINDOW_MINUTES = 60
DEFAULT_EMAIL_WINDOW_MINUTES = 1440


def _get_redis() -> Redis:
    cfg = RedisCfg.from_env()
    return Redis(host=cfg.host, port=cfg.port, db=cfg.db, decode_responses=True)


def _ip_key(ip_address: str) -> str:
    return f"{_KEY_PREFIX_IP}{ip_address}"


def _email_key(email: str) -> str:
    return f"{_KEY_PREFIX_EMAIL}{email.strip().lower()}"


def check_registration_rate_limit(
    ip_address: str,
    email: str,
    url_slug: str = "",
    max_per_ip: int = DEFAULT_MAX_PER_IP,
    max_per_email: int = DEFAULT_MAX_PER_EMAIL,
    ip_window_minutes: int = DEFAULT_IP_WINDOW_MINUTES,
    email_window_minutes: int = DEFAULT_EMAIL_WINDOW_MINUTES,
    redis_client: Redis | None = None,
) -> None:
    """Check whether a registration submission is allowed under rate limits.

    Raises RateLimitExceeded if either the per-IP or per-email limit has been
    reached within their respective sliding windows.

    Args:
        ip_address: The IP address of the request.
        email: The email address being registered.
        url_slug: The registration page slug, for log correlation.
        max_per_ip: Maximum submissions allowed per IP within the IP window.
        max_per_email: Maximum submissions allowed per email within the email window.
        ip_window_minutes: Time window in minutes for the IP counter.
        email_window_minutes: Time window in minutes for the email counter.
        redis_client: Optional Redis client (for testing). If None, creates one.

    Raises:
        RateLimitExceeded: If either rate limit is exceeded.
    """
    r = redis_client or _get_redis()

    raw_ip_count: bytes | str | None = r.get(_ip_key(ip_address))
    ip_count = int(raw_ip_count) if raw_ip_count else 0
    if ip_count >= max_per_ip:
        logger.warning("Bot protection: IP rate limit exceeded", ip_address=ip_address, slug=url_slug)
        raise RateLimitExceeded(
            operation=_("registration"),
            retry_after_seconds=ip_window_minutes * 60,
        )

    raw_email_count: bytes | str | None = r.get(_email_key(email))
    email_count = int(raw_email_count) if raw_email_count else 0
    if email_count >= max_per_email:
        # Log a stable HMAC of the email (not the address itself) so we can count
        # how many unique emails are being rate limited without storing PII.
        logger.warning("Bot protection: email rate limit exceeded", email_hash=hash_email(email), slug=url_slug)
        raise RateLimitExceeded(
            operation=_("registration"),
            retry_after_seconds=email_window_minutes * 60,
        )


def record_registration_submission(
    ip_address: str,
    email: str,
    ip_window_minutes: int = DEFAULT_IP_WINDOW_MINUTES,
    email_window_minutes: int = DEFAULT_EMAIL_WINDOW_MINUTES,
    redis_client: Redis | None = None,
) -> None:
    """Record a registration submission, incrementing both IP and email counters.

    Each counter uses a TTL equal to its own rate limit window so that counters
    automatically expire without needing manual cleanup.

    Args:
        ip_address: The IP address of the request.
        email: The email address being registered.
        ip_window_minutes: Time window in minutes for the IP counter (used as TTL).
        email_window_minutes: Time window in minutes for the email counter (used as TTL).
        redis_client: Optional Redis client (for testing). If None, creates one.
    """
    r = redis_client or _get_redis()

    ip_ttl_seconds = ip_window_minutes * 60
    email_ttl_seconds = email_window_minutes * 60

    pipe = r.pipeline()

    ik = _ip_key(ip_address)
    pipe.incr(ik)
    pipe.expire(ik, ip_ttl_seconds)

    ek = _email_key(email)
    pipe.incr(ek)
    pipe.expire(ek, email_ttl_seconds)

    pipe.execute()
