"""ABOUTME: Jinja filters for rendering user-supplied text safely.
ABOUTME: linkify turns URLs in free text into links; trim_url shortens link text."""

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
    # Styled explicitly: the Tailwind preflight sets `a { color: inherit;
    # text-decoration: inherit }`, so an unstyled link is indistinguishable from
    # the sentence around it.
    url_template = (
        '<a href="{href}" class="underline" style="color: var(--color-links)"'
        ' target="_blank" rel="noopener noreferrer"{attrs}>{url}</a>'
    )


_urlize = _NewTabUrlizer()

# Real source URLs run to 170 characters and more, which wraps over several
# lines and buries the value the comment is about. Longer link text is cut to
# this many characters, the last of which is an ellipsis. The href is untouched.
MAX_URL_TEXT_LENGTH = 40


def linkify(text: str) -> Markup:
    """Turn URLs in free text into links, escaping everything else.

    `autoescape=True` is not the default and is the security-relevant part: the
    text around a URL is escaped, and so is the href. Without it a comment could
    inject markup.

    Only http and https are linked, matching the domain's rule for source URLs;
    `javascript:` and `data:` stay inert text. Email addresses become `mailto:`
    links.
    """
    return Markup(_urlize(text, trim_url_limit=MAX_URL_TEXT_LENGTH, autoescape=True))  # noqa: S704


def trim_url(url: str) -> str:
    """Shorten a URL to the length linkify uses for link text, ending in an ellipsis.

    For a URL that is already a link in the markup, so only the text a reader
    sees is cut - the href it points at is untouched.
    """
    if len(url) <= MAX_URL_TEXT_LENGTH:
        return url
    return url[: MAX_URL_TEXT_LENGTH - 1] + "\u2026"


def register_template_filters(app: Flask) -> None:
    """Register the filters with a Flask app."""
    app.jinja_env.filters["linkify"] = linkify
    app.jinja_env.filters["trim_url"] = trim_url
