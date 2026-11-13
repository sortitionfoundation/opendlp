"""ABOUTME: Jinja render tests for the inline_edit_row macro in backoffice/components/inline_edit_row.html
ABOUTME: Covers each kind of control, the row at rest and refused, the read-only row, and the htmx wiring"""

import re

from flask import Flask, render_template_string

from opendlp import config
from opendlp.translations import gettext

BASE = (
    'row_id="project-title-row", field="title", label="Project title", action="/save",'
    ' edit_label="Edit project title", save_label="Save project title",'
    ' cancel_label="Cancel editing project title"'
)


def _render(arguments: str) -> str:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    app.config["TESTING"] = True
    app.jinja_env.globals["_"] = gettext
    app.jinja_env.globals["gettext"] = gettext
    app.jinja_env.globals["csrf_token"] = lambda: "token"
    with app.test_request_context("/"):
        return render_template_string(
            '{% from "backoffice/components/inline_edit_row.html" import inline_edit_row %}'
            "{{ inline_edit_row(" + arguments + ") }}"
        )


def _tag(html: str, pattern: str) -> str:
    match = re.search(pattern, html, re.DOTALL)
    assert match is not None, pattern
    return match.group(0)


class TestTheRowAtRest:
    def test_the_row_carries_the_id_htmx_swaps(self):
        html = _render(BASE + ', value="Our panel"')

        assert 'id="project-title-row"' in html
        form = _tag(html, r"<form\b[^>]*>")
        assert 'hx-post="/save"' in form
        assert 'hx-target="#project-title-row"' in form
        assert 'hx-swap="outerHTML"' in form
        assert 'hx-trigger="inline-edit-save"' in form
        assert 'x-data="inlineEdit"' in form
        assert "data-editing" not in form

    def test_the_field_name_is_posted_beside_the_value(self):
        """The route reads `field` to know which value this row sent."""
        html = _render(BASE + ', value="Our panel"')

        assert '<input type="hidden" name="field" value="title">' in html
        assert 'name="title"' in html

    def test_the_stored_value_is_kept_unnamed_for_escape(self):
        html = _render(BASE + ', value="Our panel"')

        saved = _tag(html, r'<input type="hidden" value="Our panel"[^>]*>')
        assert 'x-ref="saved"' in saved
        assert "name=" not in saved

    def test_the_three_buttons_are_named(self):
        html = _render(BASE + ', value="Our panel"')

        assert 'aria-label="Edit project title"' in html
        assert 'aria-label="Save project title"' in html
        assert 'aria-label="Cancel editing project title"' in html

    def test_the_label_names_the_field(self):
        html = _render(BASE + ', value="Our panel"')

        assert '<label for="title">Project title</label>' in html
        assert 'id="title"' in html

    def test_an_empty_value_reads_not_set(self):
        html = _render(BASE + ', value=""')

        assert "Not set" in html

    def test_display_is_shown_in_place_of_the_value(self):
        """A date is held as 2026-04-01 and read as 1 Apr 2026."""
        html = _render(BASE + ', value="2026-04-01", display="1 Apr 2026", kind="date"')

        paragraph = _tag(html, r"<p x-show=\"!editing\".*?</p>")
        assert "1 Apr 2026" in paragraph
        assert "2026-04-01" not in paragraph
        assert 'value="2026-04-01"' in html

    def test_a_save_from_inside_the_row_brings_focus_back_to_the_pencil(self):
        html = _render(BASE + ', value="Our panel", return_focus=true')

        pencil = _tag(html, r'<button\b[^>]*aria-label="Edit project title"[^>]*>')
        assert "autofocus" in pencil


class TestEachKind:
    def test_text_is_a_text_input(self):
        html = _render(BASE + ', value="Our panel"')

        assert 'type="text"' in _tag(html, r'<input\b[^>]*name="title"[^>]*>')

    def test_number_is_a_number_input(self):
        html = _render(BASE + ', value=30, kind="number", field_attrs=\'min="0"\'')

        field = _tag(html, r'<input\b[^>]*name="title"[^>]*>')
        assert 'type="number"' in field
        assert 'min="0"' in field
        assert 'value="30"' in field

    def test_zero_is_a_value_not_an_absence(self):
        html = _render(BASE + ', value=0, kind="number"')

        assert "Not set" not in html
        assert 'value="0"' in _tag(html, r'<input\b[^>]*name="title"[^>]*>')

    def test_date_is_a_date_input(self):
        html = _render(BASE + ', value="2026-04-01", kind="date"')

        assert 'type="date"' in _tag(html, r'<input\b[^>]*name="title"[^>]*>')

    def test_textarea_is_a_textarea_that_saves_on_ctrl_enter(self):
        """Enter adds a line there, so the form listens for the modified key instead."""
        html = _render(BASE + ', value="Line one", kind="textarea"')

        assert "<textarea" in html
        form = _tag(html, r"<form\b[^>]*>")
        assert '@keydown.ctrl.enter="save()"' in form
        assert '@keydown.meta.enter="save()"' in form

    def test_other_kinds_do_not_listen_for_ctrl_enter(self):
        html = _render(BASE + ', value="Our panel"')

        assert "keydown.ctrl.enter" not in html


class TestARefusedValue:
    def test_the_row_opens_editing_with_the_reason_and_what_was_typed(self):
        html = _render(BASE + ', value="Our panel", submitted="ab", error="Too short"')

        assert "data-editing" in _tag(html, r"<form\b[^>]*>")
        field = _tag(html, r'<input\b[^>]*name="title"[^>]*>')
        assert 'value="ab"' in field
        assert "autofocus" in field
        assert 'aria-invalid="true"' in field
        assert "Too short" in html

    def test_escape_still_has_the_stored_value_to_put_back(self):
        html = _render(BASE + ', value="Our panel", submitted="ab", error="Too short"')

        assert '<input type="hidden" value="Our panel" x-ref="saved">' in html


class TestSomeoneWhoMayOnlyRead:
    def test_there_is_no_form_and_no_pencil(self):
        html = _render(BASE + ', value="Our panel", editable=false')

        assert "<form" not in html
        assert "<button" not in html
        assert "<label" not in html
        assert "Our panel" in html
        assert "Project title" in html
