"""ABOUTME: Jinja filters for rendering user-supplied text safely.
ABOUTME: Currently just linkify, which turns URLs in free text into links."""

import re

from django.utils.html import Urlizer
from flask import Flask
from markupsafe import Markup


class _NewTabUrlizer(Urlizer):  # type: ignore[no-any-unimported]
    """Django's urlize, restricted to explicit http(s) URLs and opening in a new tab.

    Subclassed rather than reimplemented: getting this right means handling
    wrapping and trailing punctuation, unicode and IDN quoting, and length
    limits, all of which Django has already done and tested.
    """

    # `simple_url_2_re` is the branch that links bare `www.example.com` and gTLD
    # hostnames. Django builds those links by reading settings.URLIZE_ASSUME_HTTPS,
    # and this is a Flask app with no Django settings configured, so the branch
    # raises ImproperlyConfigured on any comment containing one. `(?!)` never
    # matches, which disables it. Doing so also keeps the rule the domain applies
    # to source URLs: only what is explicitly http or https becomes a link.
    # Django 7.0 drops the setting, at which point this override can go.
    simple_url_2_re = re.compile(r"(?!)")

    # Comments are read alongside the targets they explain, so a source opens
    # beside the page rather than replacing it.
    url_template = '<a href="{href}" target="_blank" rel="noopener noreferrer"{attrs}>{url}</a>'


_urlize = _NewTabUrlizer()


def linkify(text: str) -> Markup:
    """Turn URLs in free text into links, escaping everything else.

    `autoescape=True` is not the default and is the security-relevant part: the
    text around a URL is escaped, and so is the href. Without it a comment could
    inject markup.

    Only http and https are linked, matching the domain's rule for source URLs;
    `javascript:` and `data:` stay inert text. Email addresses become `mailto:`
    links.
    """
    return Markup(_urlize(text, autoescape=True))  # noqa: S704


def register_template_filters(app: Flask) -> None:
    """Register the filters with a Flask app."""
    app.jinja_env.filters["linkify"] = linkify
