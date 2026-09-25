"""ABOUTME: Cloudflare Turnstile server-side token verification (siteverify)
ABOUTME: Fail-closed gate used by the account signup form to reject bot submissions"""

import json
import urllib.error
import urllib.parse
import urllib.request

import structlog

logger = structlog.get_logger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_TIMEOUT_SECONDS = 10
# Turnstile tokens are bounded at 2048 characters; anything longer is garbage.
_MAX_TOKEN_LENGTH = 2048


def verify_turnstile_token(
    secret: str,
    token: str,
    expected_action: str,
    expected_hostnames: set[str],
    remote_ip: str = "",
) -> bool:
    """Redeem a cf-turnstile-response token against Cloudflare's siteverify API.

    Returns True only when Cloudflare confirms the token AND the widget action
    matches the protected surface AND the token was solved on an allowlisted
    frontend hostname. Tokens are single-use: a replayed token fails at
    Cloudflare's end. Any network or parsing failure counts as a failed
    verification — fail closed; the visitor can resubmit the form.
    """
    if not secret or not token or len(token) > _MAX_TOKEN_LENGTH or not expected_hostnames:
        return False

    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    request = urllib.request.Request(
        SITEVERIFY_URL,
        data=urllib.parse.urlencode(payload).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed https URL
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        logger.warning("Turnstile siteverify request failed", error=str(e))
        return False

    if not result.get("success"):
        logger.info("Turnstile rejected token", error_codes=result.get("error-codes"))
        return False
    if result.get("action") != expected_action:
        logger.warning("Turnstile action mismatch", action=result.get("action"), expected=expected_action)
        return False
    if result.get("hostname") not in expected_hostnames:
        logger.warning("Turnstile hostname not in allowlist", hostname=result.get("hostname"))
        return False
    return True
