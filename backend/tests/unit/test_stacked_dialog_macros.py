"""ABOUTME: Jinja render tests for dialogs that open over another dialog
ABOUTME: A stacked dialog wraps its backdrop and panel in .dialog-stacked, which main.css lifts above the dialog below"""

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


def _render(template: str) -> str:
    app = _make_app()
    with app.test_request_context("/"):
        return render_template_string(template)


def _wrapper(html: str) -> str:
    """The element straight inside the x-if template, which holds the backdrop and the positioner."""
    match = re.search(r'<template x-if="[^"]*">\s*(<div[^>]*>)\s*<div class="dialog-backdrop', html)
    assert match is not None, "no dialog wrapper holding a backdrop"
    return match.group(1)


_ALERT = (
    '{% from "backoffice/components/modal.html" import controlled_alert_dialog %}'
    '{% call controlled_alert_dialog(id="a", title="Sure?", description="", open_expr="aOpen",'
    ' close_expr="closeA()"STACKED) %}<button>OK</button>{% endcall %}'
)
_MODAL = (
    '{% from "backoffice/components/modal.html" import controlled_modal %}'
    '{% call controlled_modal(id="m", title="Details", open_expr="mOpen", close_expr="closeM()"STACKED) %}'
    "<p>Body</p>{% endcall %}"
)


class TestControlledDialogs:
    def test_a_dialog_is_not_stacked_by_default(self):
        for template in (_ALERT, _MODAL):
            assert "dialog-stacked" not in _render(template.replace("STACKED", ""))

    def test_a_stacked_alert_dialog_wraps_its_backdrop_and_panel(self):
        html = _render(_ALERT.replace("STACKED", ", stacked=true"))

        assert 'class="dialog-stacked"' in _wrapper(html)

    def test_a_stacked_modal_wraps_its_backdrop_and_panel(self):
        html = _render(_MODAL.replace("STACKED", ", stacked=true"))

        assert 'class="dialog-stacked"' in _wrapper(html)


class TestDialogsThatOpenOverOthers:
    def test_the_leave_guard_is_stacked(self):
        html = _render('{% include "backoffice/components/leave_guard_modal.html" %}')

        assert 'class="dialog-stacked"' in _wrapper(html)

    def test_the_link_dialog_is_stacked(self):
        html = _render('{% include "backoffice/components/rich_editor_link_modal.html" %}')

        assert 'class="dialog-stacked"' in _wrapper(html)
