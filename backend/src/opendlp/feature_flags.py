"""ABOUTME: Feature flag system controlled by environment variables with the FF_ prefix.
ABOUTME: Provides has_feature() to check if a feature is enabled at runtime."""

import os

from opendlp.config import to_bool

# Scan environment at import time: collect all FF_* vars, strip prefix, normalise to lowercase
_flags: dict[str, bool] = {}
for _key, _value in os.environ.items():
    if _key.startswith("FF_"):
        _name = _key[3:].lower()
        _flags[_name] = to_bool(_value, context_str=f"{_key}=")


def has_feature(name: str) -> bool:
    """Check whether a feature flag is enabled.

    Looks up by normalised name (case-insensitive). Returns False for unknown flags.
    """
    return _flags.get(name.lower(), False)


def reload_flags() -> None:
    """Re-scan environment variables for FF_* flags. Useful in tests."""
    _flags.clear()
    for key, value in os.environ.items():
        if key.startswith("FF_"):
            flag_name = key[3:].lower()
            _flags[flag_name] = to_bool(value, context_str=f"{key}=")


# Endpoints for the legacy ("old") dashboard and the backoffice ("new") dashboard.
OLD_DASHBOARD_ENDPOINT = "main.dashboard"
NEW_DASHBOARD_ENDPOINT = "backoffice.dashboard"


def default_dashboard_endpoint() -> str:
    """Return the Flask endpoint for the user's default dashboard.

    Controlled by FF_OLD_DEFAULT_DASHBOARD: when enabled, the old dashboard is
    the default landing page; otherwise the new backoffice dashboard is.
    """
    if has_feature("old_default_dashboard"):
        return OLD_DASHBOARD_ENDPOINT
    return NEW_DASHBOARD_ENDPOINT


def old_dashboard_route_enabled() -> bool:
    """Whether the legacy /dashboard route should be reachable at all.

    The route stays on while either flag is set: FF_OLD_DEFAULT_DASHBOARD (the
    user lands there after login) or FF_LINK_TO_OLD_DASHBOARD (the footer link
    needs a working target). When both are off, the route is fully disabled.
    """
    return has_feature("old_default_dashboard") or has_feature("link_to_old_dashboard")
