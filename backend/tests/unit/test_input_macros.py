"""ABOUTME: Jinja render tests for the form input macros in backoffice/components/input.html and the dropdowns
ABOUTME: Covers the switch's checkbox semantics, the select's optgroups, the info icons, inline input and error colours"""

import re

import pytest
from flask import Flask, render_template_string

from opendlp import config
from opendlp.translations import gettext


def _make_app() -> Flask:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    app.config["TESTING"] = True
    app.jinja_env.globals["_"] = gettext
    app.jinja_env.globals["gettext"] = gettext
    return app


def _render(macro_call: str) -> str:
    app = _make_app()
    with app.test_request_context("/"):
        return render_template_string(
            '{% from "backoffice/components/input.html" import input, select, switch, textarea, checkbox, radio_group,'
            " file_input %}"
            '{% from "backoffice/components/select_dropdown.html" import select_dropdown %}'
            '{% from "backoffice/components/search_dropdown.html" import search_dropdown %}' + macro_call,
        )


class TestSwitch:
    def test_is_a_native_checkbox_with_the_switch_role(self):
        html = _render('{{ switch("required", label="Required", checked=true) }}')

        assert re.search(r'<input\s+type="checkbox"\s+role="switch"\s+name="required"', html)
        assert re.search(r"\bchecked\b", html)

    def test_leaves_the_checked_state_to_the_native_checkbox(self):
        # A static aria-checked would contradict the checkbox as soon as it is toggled.
        for checked in ("true", "false"):
            html = _render(f'{{{{ switch("required", label="Required", checked={checked}) }}}}')
            assert "aria-checked" not in html


class TestSelectOptgroups:
    def test_an_entry_with_options_renders_as_an_optgroup(self):
        html = _render(
            """{{ select("kind", options=[
                {"value": "bool", "label": "Checkbox"},
                {"label": "Text", "options": [{"value": "text", "label": "Text"}, {"value": "email", "label": "Email"}]},
            ], value="email") }}"""
        )

        assert re.search(r'<option value="bool"\s*>\s*Checkbox', html)
        group = re.search(r'<optgroup label="Text">(.*?)</optgroup>', html, re.DOTALL)
        assert group is not None
        assert re.findall(r'<option value="([^"]*)"', group.group(1)) == ["text", "email"]
        assert re.search(r'<option value="email" selected>', group.group(1))


class TestInputInfo:
    def test_the_info_text_describes_the_input_without_joining_its_label(self):
        html = _render('{{ input("source", label="Source", info="Where the numbers come from.") }}')

        assert re.search(r'id="source-info"[^>]*>Where the numbers come from\.</span>', html)
        assert 'aria-describedby="source-info"' in html
        label = re.search(r"<label[^>]*>(.*?)</label>", html, re.DOTALL)
        assert label is not None
        assert "Where the numbers come from." not in label.group(1)

    def test_an_error_joins_the_info_in_one_describedby(self):
        html = _render(
            '{{ input("source", label="Source", info="Where the numbers come from.", error="Enter a URL") }}'
        )

        # A second aria-describedby attribute would be ignored, so both ids share one.
        assert html.count("aria-describedby=") == 1
        assert 'aria-describedby="source-info source-error"' in html
        assert 'aria-invalid="true"' in html

    def test_the_info_button_is_named_after_the_label(self):
        html = _render('{{ input("source", label="Source", info="Where the numbers come from.") }}')

        assert 'aria-label="More about Source"' in html

    def test_without_info_there_is_no_icon_and_no_describedby(self):
        html = _render('{{ input("source", label="Source") }}')

        assert "source-info" not in html
        assert "aria-describedby" not in html


class TestInputInline:
    def test_inline_puts_the_label_in_a_column_beside_the_input(self):
        html = _render('{{ input("subject", label="Subject", inline=true) }}')

        assert "md:grid-cols-[11rem_minmax(0,1fr)]" in html

    def test_stacked_is_the_default(self):
        html = _render('{{ input("subject", label="Subject") }}')

        assert "md:grid" not in html

    def test_inline_puts_hint_and_error_under_the_input(self):
        html = _render('{{ input("subject", label="Subject", hint="A hint.", error="Enter a subject", inline=true) }}')

        assert html.index("<input") < html.index('id="subject-hint"') < html.index('id="subject-error"')
        assert re.search(r'id="subject-hint" class="[^"]*md:col-start-2', html)
        assert re.search(r'id="subject-error"\s+class="[^"]*md:col-start-2', html)
        assert 'aria-describedby="subject-hint subject-error"' in html

    def test_a_stacked_hint_comes_before_the_input(self):
        html = _render('{{ input("subject", label="Subject", hint="A hint.") }}')

        assert html.index('id="subject-hint"') < html.index("<input")
        assert "md:col-start-2" not in html


class TestTextareaInfo:
    def test_the_info_text_describes_the_textarea_without_joining_its_label(self):
        html = _render('{{ textarea("body", label="Body", info="Sent as HTML.") }}')

        assert re.search(r'id="body-info"[^>]*>Sent as HTML\.</span>', html)
        assert 'aria-describedby="body-info"' in html
        label = re.search(r"<label[^>]*>(.*?)</label>", html, re.DOTALL)
        assert label is not None
        assert "Sent as HTML." not in label.group(1)

    def test_an_error_joins_the_info_in_one_describedby(self):
        html = _render('{{ textarea("body", label="Body", info="Sent as HTML.", error="Enter a body") }}')

        assert html.count("aria-describedby=") == 1
        assert 'aria-describedby="body-info body-error"' in html

    def test_without_info_there_is_no_icon_and_no_describedby(self):
        html = _render('{{ textarea("body", label="Body") }}')

        assert "body-info" not in html
        assert "aria-describedby" not in html


ERROR = "Enter a value"
OPTIONS = '[{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]'
# Every field macro, in its error state. None is marked required: a required
# field's asterisk is drawn in --color-primary-action, and is not an error.
FIELDS_IN_ERROR = {
    "input": f'{{{{ input("f", label="Field", error="{ERROR}") }}}}',
    "textarea": f'{{{{ textarea("f", label="Field", error="{ERROR}") }}}}',
    "select": f'{{{{ select("f", label="Field", options={OPTIONS}, error="{ERROR}") }}}}',
    "checkbox": f'{{{{ checkbox("f", label="Field", error="{ERROR}") }}}}',
    "radio_group": f'{{{{ radio_group("f", label="Field", options={OPTIONS}, error="{ERROR}") }}}}',
    "file_input": f'{{{{ file_input("f", label="Field", error="{ERROR}") }}}}',
    "switch": f'{{{{ switch("f", label="Field", error="{ERROR}") }}}}',
    "select_dropdown": f'{{{{ select_dropdown("f", {OPTIONS}, label="Field", error="{ERROR}") }}}}',
    "search_dropdown": f'{{{{ search_dropdown("f", label="Field", fetch_url="/search", error="{ERROR}") }}}}',
}
# The macros that draw a border round the field, and turn it red in error.
BORDERED = ("input", "textarea", "select", "select_dropdown", "search_dropdown")


class TestErrorColours:
    """A field in error is drawn in the error colours, never in the brand crimson of the primary action."""

    @pytest.mark.parametrize("macro", FIELDS_IN_ERROR)
    def test_the_message_is_in_the_error_text_colour(self, macro: str) -> None:
        html = _render(FIELDS_IN_ERROR[macro])

        message = re.search(r"<p\b([^>]*)>\s*" + re.escape(ERROR) + r"\s*</p>", html)
        assert message is not None
        assert re.search(r"(?<![-\w])color:\s*var\(--color-error-text\)", message.group(1))

    @pytest.mark.parametrize("macro", BORDERED)
    def test_the_border_is_in_the_error_border_colour(self, macro: str) -> None:
        html = _render(FIELDS_IN_ERROR[macro])

        assert "border: 1px solid var(--color-error-border)" in html

    @pytest.mark.parametrize("macro", FIELDS_IN_ERROR)
    def test_nothing_is_in_the_primary_action_colour(self, macro: str) -> None:
        html = _render(FIELDS_IN_ERROR[macro])

        assert "--color-primary-action" not in html

    @pytest.mark.parametrize("macro", BORDERED)
    def test_without_an_error_the_border_is_the_usual_one(self, macro: str) -> None:
        html = _render(FIELDS_IN_ERROR[macro].replace(f', error="{ERROR}"', ""))

        assert "border: 1px solid var(--color-borders-dividers)" in html
        assert "--color-error-border" not in html
