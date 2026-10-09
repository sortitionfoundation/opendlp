"""ABOUTME: Stdlib HTML to plain-text converter for email text/plain bodies
ABOUTME: Handles paragraphs, line breaks, links, list bullets, quotes and rules without dependencies"""

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

_LIST_TAGS = frozenset({"ul", "ol"})


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in _tidy(text).split("\n"))


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._href: str = ""
        # The text outside each open <blockquote>, so its own text can be quoted when it closes.
        self._outer_chunks: list[list[str]] = []
        # Inside a list item, blocks are lines of the item rather than paragraphs: the first
        # sits on the bullet's line, and each later one starts a new line.
        self._list_item_depth = 0
        self._list_item_empty = False

    def _start_block_in_list_item(self, tag: str) -> None:
        if tag not in _LIST_TAGS and not self._list_item_empty:
            self._chunks.append("\n")
        self._list_item_empty = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self._chunks.append("\n")
        elif tag == "li":
            self._chunks.append("\n- ")
            self._list_item_depth += 1
            self._list_item_empty = True
        elif tag == "a":
            self._href = dict(attrs).get("href") or ""
        elif tag == "hr":
            self._chunks.append("\n\n---\n\n")
        elif tag == "blockquote":
            self._outer_chunks.append(self._chunks)
            self._chunks = []
        elif tag in _BLOCK_TAGS:
            if self._list_item_depth:
                self._start_block_in_list_item(tag)
            else:
                self._chunks.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self._chunks.append(f" ({self._href})")
            self._href = ""
        elif tag == "li" and self._list_item_depth:
            self._list_item_depth -= 1
            self._list_item_empty = False
        elif tag == "blockquote" and self._outer_chunks:
            self._close_blockquote()
        elif tag in _BLOCK_TAGS and not self._list_item_depth:
            self._chunks.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self._list_item_empty and not data.strip():
            # Layout whitespace between <li> and its first block, not part of the item.
            return
        if data.strip():
            self._list_item_empty = False
        self._chunks.append(re.sub(r"\s+", " ", data))

    def _close_blockquote(self) -> None:
        quoted = _quote("".join(self._chunks))
        self._chunks = self._outer_chunks.pop()
        self._chunks.append(f"\n\n{quoted}\n\n")

    def get_text(self) -> str:
        while self._outer_chunks:
            self._close_blockquote()
        return _tidy("".join(self._chunks))


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.get_text()
