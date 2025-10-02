"""ABOUTME: Flask context processors for adding variables to template context
ABOUTME: Provides functions that inject common variables into all templates"""

import hashlib
from functools import cache

from opendlp.config import get_static_path


@cache
def get_css_hash() -> str:
    """
    Generate a short hash of the application.css file for cache-busting.

    Uses SHA256 hash of file contents, truncated to 8 characters.
    Results are cached using functools.cache to avoid re-reading the file on every request.

    Returns:
        8-character hash string, or empty string if file doesn't exist
    """
    css_path = get_static_path() / "css" / "application.css"

    if not css_path.exists():
        return ""

    content = css_path.read_bytes()
    hash_value = hashlib.sha256(content).hexdigest()
    return hash_value[:8]


def static_versioning_context_processor() -> dict[str, str]:
    """
    Flask context processor that adds static file version hashes to template context.

    Returns:
        Dictionary with css_hash key for use in templates
    """
    return {"css_hash": get_css_hash()}
