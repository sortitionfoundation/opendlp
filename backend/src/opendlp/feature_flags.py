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
