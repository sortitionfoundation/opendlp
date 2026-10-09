"""ABOUTME: Unit tests for adding default GOV.UK classes to rendered intro HTML
ABOUTME: Covers the mapping, the opt-out rules (decision E14) and byte-for-byte preservation of everything else"""

import pytest

from opendlp.domain.html_default_classes import DEFAULT_GOVUK_CLASSES, apply_default_govuk_classes
from opendlp.domain.value_objects import ContentStyle, content_style_labels


class TestMapping:
    @pytest.mark.parametrize(("tag", "css_class"), sorted(DEFAULT_GOVUK_CLASSES.items()))
    def test_every_mapped_element_gets_its_class(self, tag: str, css_class: str):
        assert apply_default_govuk_classes(f"<{tag}>x</{tag}>") == f'<{tag} class="{css_class}">x</{tag}>'

    def test_headings_step_down_from_xl(self):
        assert DEFAULT_GOVUK_CLASSES["h1"] == "govuk-heading-xl"
        assert DEFAULT_GOVUK_CLASSES["h2"] == "govuk-heading-l"
        assert DEFAULT_GOVUK_CLASSES["h3"] == "govuk-heading-m"

    @pytest.mark.parametrize("html", ["<div>x</div>", "<li>x</li>", "<img src='/a.png' alt=''>", "<h4>x</h4>"])
    def test_unmapped_elements_are_untouched(self, html: str):
        assert apply_default_govuk_classes(html) == html

    def test_tables_are_untouched_until_layout_or_data_is_decided(self):
        """Q6 in the plan: a class now would commit every table to one answer."""
        html = "<table><tbody><tr><th>h</th><td>x</td></tr></tbody></table>"
        assert apply_default_govuk_classes(html) == html

    @pytest.mark.parametrize(
        ("hr", "expected"),
        [
            ("<hr>", '<hr class="{0}">'),
            ("<hr/>", '<hr class="{0}"/>'),
            ("<hr />", '<hr class="{0}" />'),
        ],
    )
    def test_a_horizontal_rule_gets_a_visible_section_break(self, hr: str, expected: str):
        section_break = "govuk-section-break govuk-section-break--m govuk-section-break--visible"
        assert apply_default_govuk_classes(hr) == expected.format(section_break)

    def test_keeps_other_attributes(self):
        assert apply_default_govuk_classes('<a href="/x" title="t">l</a>') == (
            '<a class="govuk-link" href="/x" title="t">l</a>'
        )

    def test_handles_upper_case_tags(self):
        assert apply_default_govuk_classes("<P>x</P>") == '<P class="govuk-body">x</P>'


class TestOptingOut:
    def test_an_authors_own_class_is_left_alone(self):
        assert apply_default_govuk_classes('<p class="plain">x</p>') == '<p class="plain">x</p>'

    def test_an_existing_govuk_class_is_left_alone(self):
        html = '<h1 class="govuk-heading-l">x</h1>'
        assert apply_default_govuk_classes(html) == html

    @pytest.mark.parametrize("empty", ['class=""', "class=''", 'class="  "', "class"])
    def test_an_empty_class_gets_the_default(self, empty: str):
        """Q5: an empty class is not a choice of no styling - use a class of your own for that."""
        assert apply_default_govuk_classes(f"<p {empty}>x</p>") == '<p class="govuk-body">x</p>'

    def test_an_inline_style_does_not_opt_out(self):
        """Decision E14: the class gives the GOV.UK look and the inline style adjusts it."""
        assert apply_default_govuk_classes('<p style="text-align: center;">x</p>') == (
            '<p class="govuk-body" style="text-align: center;">x</p>'
        )


class TestPreservation:
    def test_is_idempotent(self):
        html = "<h1>T</h1><p>a</p><ul><li><a href='/x'>l</a></li></ul>"
        once = apply_default_govuk_classes(html)
        assert apply_default_govuk_classes(once) == once

    def test_preserves_everything_but_the_changed_start_tags(self):
        html = (
            "<!DOCTYPE html>\n<!-- a <p> in a comment -->\n"
            "<p>Fish &amp; chips&nbsp;&#169; {{ not_a_variable }}<br/>line<br></p>\r\n"
            "<div data-x='1'>  <img src=\"/a.png\" alt=''/></div></P >"
        )
        assert apply_default_govuk_classes(html) == html.replace("<p>Fish", '<p class="govuk-body">Fish')

    def test_does_not_mistake_class_inside_another_attribute_for_the_class(self):
        assert apply_default_govuk_classes('<p title="a class b">x</p>') == (
            '<p class="govuk-body" title="a class b">x</p>'
        )

    def test_self_closing_start_tag(self):
        assert apply_default_govuk_classes("<p/>") == '<p class="govuk-body"/>'

    def test_positions_survive_multiple_lines(self):
        html = "<div>\n  <h2>One</h2>\n\n  <p>Two</p>\n</div>\n"
        assert apply_default_govuk_classes(html) == (
            '<div>\n  <h2 class="govuk-heading-l">One</h2>\n\n  <p class="govuk-body">Two</p>\n</div>\n'
        )

    def test_empty_html(self):
        assert apply_default_govuk_classes("") == ""


class TestContentStyleLabels:
    @pytest.mark.parametrize("style", list(ContentStyle))
    def test_every_content_style_has_a_label(self, style: ContentStyle):
        assert content_style_labels[style]
