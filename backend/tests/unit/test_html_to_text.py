"""ABOUTME: Unit tests for the stdlib HTML to plain-text converter
ABOUTME: Covers paragraphs, line breaks, links and list bullets"""

import pytest

from opendlp.domain.html_to_text import html_to_text


@pytest.mark.parametrize(
    "html,expected",
    [
        ("plain text", "plain text"),
        ("<p>Hello</p><p>World</p>", "Hello\n\nWorld"),
        ("Line1<br>Line2", "Line1\nLine2"),
        ('<a href="https://example.com">click</a>', "click (https://example.com)"),
        ("<ul><li>one</li><li>two</li></ul>", "- one\n- two"),
        ("<p>Multiple    spaces   here</p>", "Multiple spaces here"),
    ],
)
def test_html_to_text_cases(html: str, expected: str) -> None:
    assert html_to_text(html) == expected


def test_html_to_text_strips_surrounding_whitespace() -> None:
    assert html_to_text("\n\n  <p>Body</p>  \n") == "Body"


def test_html_to_text_collapses_blank_lines() -> None:
    assert html_to_text("<p>a</p><p></p><p>b</p>") == "a\n\nb"
