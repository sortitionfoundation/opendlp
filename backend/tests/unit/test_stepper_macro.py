"""ABOUTME: Jinja render tests for the stepper macro's ARIA and screen-reader affordances.
ABOUTME: Verifies visually-hidden state text is emitted for done/error, and mode-appropriate ARIA."""

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
            '{% from "backoffice/components/stepper.html" import stepper %}' + macro_call,
        )


_TABS_ITEMS = """items=[
    {"key": "one",   "label": "Registration page",   "href": "?section=form",    "state": "done"},
    {"key": "two",   "label": "Auto-reply email",    "href": "?section=email",   "active": true},
    {"key": "three", "label": "Preview and publish", "href": "?section=preview", "state": "error"}
]"""


class TestStepperScreenReaderState:
    """Regression cover for the /sf-code-review should-fix #5: done/error states
    must not be colour-only. Screen readers should be told the state in words."""

    def test_done_step_carries_visually_hidden_completed_text(self):
        # Anchor on the exact span markup so incidental copy elsewhere in the
        # rendered output (labels, comments) can't accidentally satisfy the assertion.
        html = _render(f'{{{{ stepper(id="s", aria_label="Steps", {_TABS_ITEMS}) }}}}')
        assert '<span class="sr-only"> (completed)</span>' in html

    def test_error_step_carries_visually_hidden_error_text(self):
        html = _render(f'{{{{ stepper(id="s", aria_label="Steps", {_TABS_ITEMS}) }}}}')
        assert '<span class="sr-only"> (has errors)</span>' in html

    def test_active_and_inactive_steps_do_not_get_sr_only_state(self):
        """Active is already announced via aria-selected/aria-current; inactive is the
        default state and doesn't need announcing. Only done and error do."""
        html = _render(
            '{{ stepper(id="s", aria_label="Steps", items=['
            '  {"key": "a", "label": "Active",   "href": "#", "active": true},'
            '  {"key": "b", "label": "Inactive", "href": "#"}'
            "]) }}"
        )
        # No sr-only spans emitted for these two states.
        assert 'class="sr-only"' not in html


class TestStepperAriaByMode:
    def test_tabs_mode_emits_tablist_and_aria_selected(self):
        html = _render(f'{{{{ stepper(id="s", aria_label="Steps", mode="tabs", {_TABS_ITEMS}) }}}}')
        assert 'role="tablist"' in html
        assert 'role="tab"' in html
        # The step marked active carries aria-selected="true"; others "false".
        assert 'aria-selected="true"' in html
        assert 'aria-selected="false"' in html

    def test_wizard_mode_emits_list_and_aria_current(self):
        html = _render(f'{{{{ stepper(id="s", aria_label="Steps", mode="wizard", {_TABS_ITEMS}) }}}}')
        assert 'role="list"' in html
        assert 'aria-current="step"' in html
        # Wizard mode should not emit aria-selected (that's tab semantics).
        assert "aria-selected=" not in html

    def test_disabled_wizard_step_is_non_focusable_span(self):
        html = _render(
            '{{ stepper(id="s", aria_label="Steps", mode="wizard", items=['
            '  {"key": "a", "label": "One",   "href": "#", "state": "done"},'
            '  {"key": "b", "label": "Two",   "href": "#", "active": true},'
            '  {"key": "c", "label": "Three", "href": "#", "disabled": true}'
            "]) }}"
        )
        assert 'aria-disabled="true"' in html


class TestStepperExtraAttrsEscaping:
    """Pass-through attribute values must be HTML-escaped, because the macro joins
    them into a raw string and renders with |safe. An unescaped quote in a value
    would break out of the attribute."""

    def test_quote_in_pass_through_value_is_escaped(self):
        html = _render(
            '{{ stepper(id="s", aria_label="Steps", items=['
            '  {"key": "a", "label": "One", "href": "#", "active": true,'
            '   "data-note": \'evil" onclick="alert(1)\'}'
            "]) }}"
        )
        # The literal attack payload must not appear intact — the quote must be
        # entity-encoded so it cannot terminate the attribute.
        assert 'onclick="alert(1)' not in html
        assert "&#34;" in html or "&quot;" in html

    def test_angle_bracket_in_pass_through_value_is_escaped(self):
        html = _render(
            '{{ stepper(id="s", aria_label="Steps", items=['
            '  {"key": "a", "label": "One", "href": "#", "active": true,'
            "   \"data-note\": '<script>alert(1)</script>'}"
            "]) }}"
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_benign_pass_through_value_still_reaches_output(self):
        html = _render(
            '{{ stepper(id="s", aria_label="Steps", items=['
            '  {"key": "a", "label": "One", "href": "#", "active": true,'
            '   "data-cy": "step-one"}'
            "]) }}"
        )
        assert 'data-cy="step-one"' in html
