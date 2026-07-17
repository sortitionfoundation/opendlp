"""ABOUTME: Jinja render tests for the button macro's alpine_disabled param.
ABOUTME: Verifies the rendered HTML carries reactive Alpine bindings on the atomic .btn classes."""

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
        # The reactive :disabled attribute drives the .btn[disabled] CSS state
        assert "!form.name" in html

    def test_does_not_emit_alpine_bindings_when_alpine_disabled_absent(self):
        html = _render('{{ button("Save", variant="primary") }}')
        assert ":disabled=" not in html
        assert ":aria-disabled=" not in html

    def test_static_disabled_renders_disabled_attr_on_atomic_button(self):
        html = _render('{{ button("Save", variant="primary", disabled=true) }}')
        assert 'disabled aria-disabled="true"' in html
        # Disabled styling comes from the .btn[disabled] CSS rule, not inline styles
        assert "btn--primary" in html

    def test_alpine_disabled_keeps_static_variant_class(self):
        """The .btn--primary class carries the active look; Alpine's :disabled toggles
        the [disabled] CSS state on top without changing the variant class."""
        html = _render('{{ button("Save", variant="primary", alpine_disabled="locked") }}')
        assert "btn--primary" in html
        assert ':disabled="locked"' in html
