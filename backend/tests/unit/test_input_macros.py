"""ABOUTME: Jinja render tests for the form input macros in backoffice/components/input.html
ABOUTME: Covers the switch's checkbox semantics and the select's optgroup support"""

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
            '{% from "backoffice/components/input.html" import switch, select %}' + macro_call,
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
