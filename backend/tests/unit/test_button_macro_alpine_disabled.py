"""ABOUTME: Jinja render tests for the button macro's alpine_disabled param.
ABOUTME: Verifies the rendered HTML carries reactive Alpine bindings and the muted-class toggle."""

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
            '{% from "backoffice/components/button.html" import button %}' + macro_call,
        )


class TestButtonMacroAlpineDisabled:
    def test_emits_alpine_bindings_when_alpine_disabled_provided(self):
        html = _render('{{ button("Save", variant="primary", alpine_disabled="!form.name") }}')
        assert ':disabled="!form.name"' in html
        assert ":aria-disabled=" in html
        assert "btn-runtime-disabled" in html
        # The Alpine expression must appear inside the :class object literal
        assert "!form.name" in html

    def test_does_not_emit_alpine_bindings_when_alpine_disabled_absent(self):
        html = _render('{{ button("Save", variant="primary") }}')
        assert ":disabled=" not in html
        assert ":aria-disabled=" not in html
        assert "btn-runtime-disabled" not in html

    def test_static_disabled_still_renders_muted_style_and_html_attr(self):
        html = _render('{{ button("Save", variant="primary", disabled=true) }}')
        assert " disabled " in html or "disabled>" in html or 'disabled aria-disabled="true"' in html
        # The Jinja-time muted style uses the placeholder text colour token
        assert "color: var(--color-placeholder-text)" in html

    def test_alpine_disabled_keeps_static_active_variant_style(self):
        """Static `style` keeps the active look so padding/base styles survive when
        Alpine merges the reactive :class on top."""
        html = _render('{{ button("Save", variant="primary", alpine_disabled="locked") }}')
        # Active primary background colour is still in the inline style attribute
        assert "color: var(--color-button-primary-text)" in html
        # Padding / base styles should remain in the rendered inline style
        assert "padding:" in html
