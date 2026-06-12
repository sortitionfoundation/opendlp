"""ABOUTME: Dependency-free HTML-to-plain-text conversion for templated emails
ABOUTME: Derives the text/plain alternative of an email from its rendered HTML body"""

import re
from html.parser import HTMLParser

# Tags whose boundaries should produce a blank line (block-level layout).
_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "header",
        "footer",
        "main",
        "aside",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "table",
        "tr",
        "blockquote",
        "pre",
        "form",
        "figure",
        "hr",
    }
)

# Tags whose textual content must be discarded entirely.
_SKIP_TAGS = frozenset({"script", "style", "head", "title"})


class _TextExtractor(HTMLParser):
    """Collects a plain-text rendering of an HTML fragment.

    Block elements are separated by blank lines, ``<br>`` becomes a single
    newline, ``<li>`` becomes a ``- `` bullet, and anchors are rendered as
    ``text (href)`` unless the href adds nothing over the visible text.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0
        # Stacks so nested anchors (rare, but valid input) don't corrupt state.
        self._anchor_href: list[str] = []
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "a":
            href = ""
            for key, value in attrs:
                if key == "href":
                    href = value or ""
            self._anchor_href.append(href)
            self._anchor_text.append("")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.parts.append("\n")
        elif tag == "hr":
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if tag == "a" and self._anchor_href:
            href = self._anchor_href.pop()
            text = self._anchor_text.pop().strip()
            # Suppress the parenthesised URL when it duplicates the link text
            # (e.g. a link whose text is the URL, or a mailto: of the address).
            if href and href != text and href != f"mailto:{text}":
                self.parts.append(f" ({href})")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._anchor_href:
            self._anchor_text[-1] += data
        self.parts.append(data)


def html_to_text(html: str) -> str:
    """Convert an HTML fragment to a readable plain-text rendering.

    The output collapses runs of inline whitespace, trims each line, and
    collapses three-or-more consecutive newlines down to a single blank line.
    An empty or whitespace-only input returns an empty string.
    """
    if not html or not html.strip():
        return ""

    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    raw = "".join(extractor.parts)

    # Normalise inline whitespace per line, then tidy vertical whitespace.
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in raw.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
