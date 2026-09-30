"""ABOUTME: Jinja render tests for the form input macros in backoffice/components/input.html
ABOUTME: Covers the switch's checkbox semantics, the select's optgroup support and the input's info icon"""

import re

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
            '{% from "backoffice/components/input.html" import input, select, switch %}' + macro_call,
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

    def test_without_info_there_is_no_icon_and_no_describedby(self):
        html = _render('{{ input("source", label="Source") }}')

        assert "source-info" not in html
        assert "aria-describedby" not in html
