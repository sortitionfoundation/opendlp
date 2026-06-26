"""ABOUTME: Redaction helpers and a structlog processor to keep PII/secrets out of logs.
ABOUTME: Provides email redaction, a sensitive-key denylist, the censor_pii processor, and hash_email."""

import hashlib
import hmac
import re

from structlog.types import EventDict, WrappedLogger

from opendlp import config

# Email addresses anywhere in a string are replaced with this placeholder.
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
EMAIL_PLACEHOLDER = "[EMAIL_REDACTED]"

# Values for keys that match the denylist are replaced with this.
REDACTED = "[REDACTED]"

# Single source of truth for "sensitive" field/header names. Seeded from the
# header denylist that GunicornLogger.header_safe historically maintained, plus
# common PII/secret field names. Exact matches and substring (partial) matches.
# NB: keep partials free of "email"/"id" so email_hash / user_id / request_id
# survive redaction (they are not PII once an account is deleted).
SENSITIVE_EXACT = frozenset({
    "authorization",
    "cookie",
    "csrf_token",
    "csrf-token",
    "password",
    "secret",
    "token",
    "email",
})
SENSITIVE_PARTIAL = (
    "api-key",
    "api_key",
    "authorization",
    "-token",
    "_token",
    "secret",
    "password",
)


def redact_emails(text: str) -> str:
    """Replace any email addresses in ``text`` with a placeholder."""
    return EMAIL_RE.sub(EMAIL_PLACEHOLDER, text)


def is_sensitive_key(key: str) -> bool:
    """Return True if a log field/header name should have its value redacted."""
    lower = key.lower()
    if lower in SENSITIVE_EXACT:
        return True
    return any(part in lower for part in SENSITIVE_PARTIAL)


def _redact_value(value: object) -> object:
    """Recursively scrub emails from strings and sensitive keys from nested dicts.

    Containers (dict/list/tuple) are walked so that PII embedded in structured
    values (e.g. a list of header tuples) is redacted, not just top-level
    strings. Tuple-ness is preserved; scalars pass through unchanged.
    """
    if isinstance(value, str):
        return redact_emails(value)
    if isinstance(value, dict):
        return {k: REDACTED if is_sensitive_key(str(k)) else _redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    return value


def censor_pii(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """structlog processor: redact sensitive field values and scrub emails from strings.

    Registered in both the structlog processor chain and the stdlib
    ``foreign_pre_chain`` so it covers our own structlog calls and foreign
    (stdlib / third-party) log records alike. Values are walked recursively so
    that emails/secrets nested in lists and dicts are redacted too.
    """
    for key, value in event_dict.items():
        if is_sensitive_key(key):
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _redact_value(value)
    return event_dict


def hash_email(email: str, *, secret: str | None = None) -> str:
    """Return a stable, non-reversible HMAC token for an email address.

    Used where we need to correlate log lines about the same email (e.g. login
    rate limiting) without storing the address itself. Normalised so that
    case/whitespace variants hash identically.
    """
    key = (secret if secret is not None else config.get_secret_key()).encode()
    normalised = email.strip().lower().encode()
    digest = hmac.new(key, normalised, hashlib.sha256).hexdigest()
    return f"email#{digest[:12]}"
