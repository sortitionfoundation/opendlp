"""ABOUTME: Adds a default GOV.UK class to rendered HTML elements that have no class of their own
ABOUTME: Changes only those start tags; every other byte of the HTML is passed through untouched"""

import re
from html.parser import HTMLParser

# Matches the classes the GOV.UK starter intro uses: h1 is xl and headings step down from there.
DEFAULT_GOVUK_CLASSES = {
    "h1": "govuk-heading-xl",
    "h2": "govuk-heading-l",
    "h3": "govuk-heading-m",
    "p": "govuk-body",
    "ul": "govuk-list govuk-list--bullet",
    "ol": "govuk-list govuk-list--number",
    "a": "govuk-link",
    "blockquote": "govuk-inset-text",
    "hr": "govuk-section-break govuk-section-break--m govuk-section-break--visible",
}

_TAG_NAME = re.compile(r"<[^\s/>]+")
_ATTRIBUTE = re.compile(r"""\s+([^\s=/>]+)(\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?""")


def _wants_default_class(attrs: list[tuple[str, str | None]]) -> bool:
    """True unless the element already has a non-empty class.

    An inline `style` does not opt out (decision E14 in
    docs/agent/767-registration-intro/tiptap-intro-editor-plan.md): the class
    supplies the GOV.UK look and the inline style adjusts it. An empty
    `class=""` does not opt out either; any class of the author's own does.
    """
    return not any(name == "class" and (value or "").strip() for name, value in attrs)


def _with_class(start_tag: str, css_class: str) -> str:
    """The start tag with `class="css_class"`, replacing an empty class attribute if there is one."""
    name_end = _TAG_NAME.match(start_tag)
    assert name_end is not None
    head, rest = start_tag[: name_end.end()], start_tag[name_end.end() :]
    for attribute in _ATTRIBUTE.finditer(rest):
        if attribute.group(1).lower() == "class":
            return f'{head}{rest[: attribute.start()]} class="{css_class}"{rest[attribute.end() :]}'
    return f'{head} class="{css_class}"{rest}'


class _StartTagEdits(HTMLParser):
    """Collects (start, end, replacement) for each start tag that wants a default class."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=False)
        self.edits: list[tuple[int, int, str]] = []
        self._line_starts = [0] + [index + 1 for index, char in enumerate(html) if char == "\n"]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._edit(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._edit(tag, attrs)

    def _edit(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        css_class = DEFAULT_GOVUK_CLASSES.get(tag)
        start_tag = self.get_starttag_text()
        if css_class is None or start_tag is None or not _wants_default_class(attrs):
            return
        line, column = self.getpos()
        start = self._line_starts[line - 1] + column
        self.edits.append((start, start + len(start_tag), _with_class(start_tag, css_class)))


def apply_default_govuk_classes(html: str) -> str:
    """`html` with a default GOV.UK class on each mapped element that has no class.

    Idempotent: a second pass finds every mapped element already classed.
    """
    parser = _StartTagEdits(html)
    parser.feed(html)
    parser.close()
    pieces = []
    position = 0
    for start, end, replacement in parser.edits:
        pieces.append(html[position:start])
        pieces.append(replacement)
        position = end
    pieces.append(html[position:])
    return "".join(pieces)
