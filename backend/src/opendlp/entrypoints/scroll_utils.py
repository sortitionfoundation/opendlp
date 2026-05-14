"""ABOUTME: Utility functions for scroll preservation across redirects
ABOUTME: Provides redirect_preserving_scroll to maintain scroll position after form submissions"""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

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
    # Validate scroll is a non-negative integer to prevent injection
    if scroll and scroll.isdigit():
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        params["scroll"] = [scroll]
        new_query = urlencode(params, doseq=True)
        url = urlunparse(parsed._replace(query=new_query))
    return redirect(url)
