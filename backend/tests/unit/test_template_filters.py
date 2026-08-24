"""ABOUTME: Unit tests for the linkify Jinja filter
ABOUTME: The escaping order is the security-relevant part, so it is tested directly"""

import pytest

from opendlp.entrypoints.template_filters import linkify


class TestLinkify:
    def test_turns_an_http_url_into_a_link(self):
        result = str(linkify("see https://www.ons.gov.uk/data for details"))

        assert '<a href="https://www.ons.gov.uk/data"' in result
        assert 'rel="noopener noreferrer"' in result
        assert 'target="_blank"' in result

    def test_escapes_markup_in_the_surrounding_text(self):
        """Escape first, then linkify - the other order lets a comment inject markup."""
        result = str(linkify("<script>alert(1)</script> and https://ok.com"))

        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    @pytest.mark.parametrize("scheme", ["javascript:alert(1)", "data:text/html,<b>", "ftp://example.com"])
    def test_leaves_other_schemes_as_inert_text(self, scheme):
        result = str(linkify(f"go to {scheme} now"))

        assert "<a href" not in result

    def test_a_quote_cannot_break_out_of_the_href(self):
        result = str(linkify('https://x.com/"onmouseover="alert(1)'))

        assert 'onmouseover="alert' not in result
        assert "&#34;" in result

    def test_trailing_punctuation_stays_outside_the_link(self):
        result = str(linkify("see https://example.com/a."))

        assert ">https://example.com/a</a>." in result

    def test_plain_text_is_unchanged(self):
        assert str(linkify("no urls here")) == "no urls here"

    def test_empty_text(self):
        assert str(linkify("")) == ""
