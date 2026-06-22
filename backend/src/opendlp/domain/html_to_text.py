"""ABOUTME: Stdlib HTML to plain-text converter for email text/plain bodies
ABOUTME: Handles paragraphs, line breaks, links and list bullets without dependencies"""

import re
from html.parser import HTMLParser

_BLOCK_TAGS = frozenset({
    "p",
    "div",
    "section",
    "article",
    "header",
    "footer",
    "ul",
    "ol",
    "table",
    "tr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
})


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._href: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self._chunks.append("\n")
        elif tag == "li":
            self._chunks.append("\n- ")
        elif tag == "a":
            self._href = dict(attrs).get("href") or ""
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self._chunks.append(f" ({self._href})")
            self._href = ""
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n\n")

    def handle_data(self, data: str) -> None:
        self._chunks.append(re.sub(r"\s+", " ", data))

    def get_text(self) -> str:
        text = "".join(self._chunks)
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.get_text()
