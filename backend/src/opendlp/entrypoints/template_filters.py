"""ABOUTME: Jinja filters for rendering user-supplied text safely.
ABOUTME: Currently just linkify, which turns http(s) URLs in escaped text into links."""

import re

from flask import Flask
from markupsafe import Markup, escape

# Matched against text that has *already* been escaped, so the surrounding markup
# cannot be part of a URL. Stops at the first character that cannot appear in one.
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")

# Trailing punctuation is far more likely to be a sentence ending than part of
# the URL, so it is left outside the link.
TRAILING_PUNCTUATION = ".,;:!?)]}"


def linkify(text: str) -> Markup:
    """Turn http(s) URLs in free text into links, escaping everything first.

    Order matters and is the whole point: the text is escaped, *then* links are
    inserted into the escaped result. Building links from raw input and marking
    the result safe would let a comment inject markup.

    Only http and https are linked. Anything else - `javascript:`, `data:` - stays
    inert text, matching the domain's rule for source URLs.
    """
    escaped = str(escape(text))

    def replace(match: re.Match[str]) -> str:
        url = match.group(0)
        trailing = ""
        while url and url[-1] in TRAILING_PUNCTUATION:
            trailing = url[-1] + trailing
            url = url[:-1]
        if not url:
            return trailing
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>{trailing}'

    return Markup(URL_PATTERN.sub(replace, escaped))  # noqa: S704


def register_template_filters(app: Flask) -> None:
    """Register the filters with a Flask app."""
    app.jinja_env.filters["linkify"] = linkify
