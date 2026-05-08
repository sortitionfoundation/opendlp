"""ABOUTME: Utility functions for scroll preservation across redirects
ABOUTME: Provides redirect_preserving_scroll to maintain scroll position after form submissions"""

from flask import redirect, request
from flask.typing import ResponseReturnValue


def redirect_preserving_scroll(url: str) -> ResponseReturnValue:
    """Redirect to a URL while preserving the scroll parameter from the current request.

    When forms use data-preserve-scroll or x-preserve-scroll-on-submit, the JavaScript
    adds a scroll=XXX parameter to the form action. This function preserves that parameter
    in the redirect URL so the browser can restore scroll position after the redirect.

    Args:
        url: The URL to redirect to

    Returns:
        A Flask redirect response with scroll parameter preserved if present

    Example:
        # In a route handler:
        return redirect_preserving_scroll(url_for("my.route", id=item_id))
    """
    scroll = request.args.get("scroll")
    if scroll:
        # Handle hash fragments: query params must come before the hash
        hash_index = url.find("#")
        if hash_index != -1:
            base_url = url[:hash_index]
            hash_fragment = url[hash_index:]
        else:
            base_url = url
            hash_fragment = ""

        # Append scroll parameter to the base URL
        separator = "&" if "?" in base_url else "?"
        url = f"{base_url}{separator}scroll={scroll}{hash_fragment}"
    return redirect(url)
