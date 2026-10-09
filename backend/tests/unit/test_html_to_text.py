"""ABOUTME: Unit tests for the stdlib HTML to plain-text converter
ABOUTME: Covers paragraphs, line breaks, links and list bullets"""

import pytest

from opendlp.domain.html_to_text import html_to_text


@pytest.mark.parametrize(
    ("html", "expected"),
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


# The visual editor (Tiptap) wraps each list item's text in a <p>, and saves its
# HTML one block per line, indented by nesting. The plain-text part of an email
# made in it must read the same as one written by hand.


def test_html_to_text_list_item_paragraph_stays_on_the_bullet_line() -> None:
    assert html_to_text("<ul><li><p>one</p></li><li><p>two</p></li></ul>") == "- one\n- two"


def test_html_to_text_later_paragraphs_in_a_list_item_start_a_new_line() -> None:
    assert html_to_text("<ul><li><p>one</p><p>more</p></li><li><p>two</p></li></ul>") == "- one\nmore\n- two"


def test_html_to_text_nested_list_has_no_blank_line() -> None:
    html = "<ul><li><p>one</p><ul><li><p>inner</p></li></ul></li><li><p>two</p></li></ul>"
    assert html_to_text(html) == "- one\n- inner\n- two"


def test_html_to_text_list_is_set_apart_from_the_paragraphs_around_it() -> None:
    assert html_to_text("<p>Before</p><ul><li><p>one</p></li></ul><p>After</p>") == "Before\n\n- one\n\nAfter"


def test_html_to_text_ignores_the_editor_layout_whitespace() -> None:
    html = "<p>Hi</p>\n<ul>\n  <li>\n    <p>One</p>\n  </li>\n  <li>\n    <p>Two</p>\n  </li>\n</ul>\n<p>Bye</p>"
    assert html_to_text(html) == "Hi\n\n- One\n- Two\n\nBye"


def test_html_to_text_quotes_each_line_of_a_blockquote() -> None:
    html = "<p>She said:</p>\n<blockquote>\n  <p>First</p>\n  <p>Second</p>\n</blockquote>\n<p>End</p>"
    assert html_to_text(html) == "She said:\n\n> First\n>\n> Second\n\nEnd"


def test_html_to_text_quotes_a_list_inside_a_blockquote() -> None:
    assert html_to_text("<blockquote><ul><li><p>one</p></li></ul></blockquote>") == "> - one"


def test_html_to_text_quotes_an_unclosed_blockquote() -> None:
    assert html_to_text("<blockquote><p>Cut off") == "> Cut off"


def test_html_to_text_shows_a_horizontal_rule_as_a_line() -> None:
    assert html_to_text("<p>Above</p>\n<hr>\n<p>Below</p>") == "Above\n\n---\n\nBelow"
