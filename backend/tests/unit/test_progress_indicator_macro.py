"""ABOUTME: Jinja render tests for the progress_indicator macro in modal.html.
ABOUTME: Verifies determinate bar vs spinner rendering with ProgressInfo objects."""

from flask import Flask, render_template_string

from opendlp import config
from opendlp.domain.value_objects import ProgressInfo
from opendlp.translations import gettext


def _make_app() -> Flask:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    app.config["TESTING"] = True
    app.jinja_env.globals["_"] = gettext
    app.jinja_env.globals["gettext"] = gettext
    return app


def _render_indicator(progress_info: ProgressInfo | None) -> str:
    app = _make_app()
    with app.test_request_context("/"):
        return render_template_string(
            """{% from "backoffice/components/modal.html" import progress_indicator %}{{ progress_indicator(progress_info) }}""",
            progress_info=progress_info,
        )


class TestProgressIndicatorMacro:
    def test_none_renders_generic_spinner(self):
        html = _render_indicator(None)
        assert "Processing" in html
        assert "animate-spin" in html

    def test_spinner_when_total_is_none(self):
        html = _render_indicator(ProgressInfo(label="Reading spreadsheet…", current=0, total=None))
        assert "Reading spreadsheet" in html
        assert "animate-spin" in html
        assert 'role="progressbar"' not in html

    def test_determinate_bar_when_total_is_set(self):
        html = _render_indicator(
            ProgressInfo(label="Finding diverse committees (45 of 200 rounds)", current=45, total=200)
        )
        assert "45" in html
        assert "200" in html
        assert 'role="progressbar"' in html
        assert "Finding diverse committees" in html

    def test_spinner_shows_label(self):
        html = _render_indicator(
            ProgressInfo(label="Optimising for maximin fairness (iteration 17)", current=17, total=None)
        )
        assert "17" in html
        assert "maximin" in html.lower()
        assert 'role="progressbar"' not in html
        assert "animate-spin" in html

    def test_label_rendered_in_determinate_bar(self):
        html = _render_indicator(
            ProgressInfo(label="Optimising for leximin fairness (8 of 50 fixed)", current=8, total=50)
        )
        assert "8" in html
        assert "50" in html
        assert 'role="progressbar"' in html
        assert "leximin" in html.lower()
