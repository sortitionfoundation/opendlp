"""ABOUTME: Jinja render tests for the progress_indicator macro in modal.html.
ABOUTME: Verifies phase → label mapping, determinate bar vs spinner, and unknown-phase fallback."""

from flask import Flask, render_template_string

from opendlp import config
from opendlp.translations import gettext


def _make_app() -> Flask:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    app.config["TESTING"] = True
    app.jinja_env.globals["_"] = gettext
    app.jinja_env.globals["gettext"] = gettext
    return app


def _render_indicator(progress: dict | None) -> str:
    app = _make_app()
    with app.test_request_context("/"):
        return render_template_string(
            """{% from "backoffice/components/modal.html" import progress_indicator %}{{ progress_indicator(progress) }}""",
            progress=progress,
        )


class TestProgressIndicatorMacro:
    def test_none_progress_renders_generic_spinner(self):
        html = _render_indicator(None)
        assert "Processing" in html
        assert "animate-spin" in html  # spinner class

    def test_read_gsheet_phase_shows_reading_label(self):
        html = _render_indicator({"phase": "read_gsheet", "current": 0, "total": None})
        assert "Reading spreadsheet" in html
        assert "animate-spin" in html
        # No determinate bar when total is None
        assert 'role="progressbar"' not in html

    def test_write_gsheet_phase_shows_writing_label(self):
        html = _render_indicator({"phase": "write_gsheet", "current": 0, "total": None})
        assert "Writing results" in html
        assert "animate-spin" in html

    def test_multiplicative_weights_shows_determinate_bar(self):
        html = _render_indicator({"phase": "multiplicative_weights", "current": 45, "total": 200})
        assert "45" in html
        assert "200" in html
        assert 'role="progressbar"' in html
        assert "Finding diverse committees" in html

    def test_maximin_optimization_shows_iteration_counter(self):
        html = _render_indicator({"phase": "maximin_optimization", "current": 17, "total": None})
        assert "17" in html
        assert "maximin" in html.lower()
        assert 'role="progressbar"' not in html
        assert "animate-spin" in html

    def test_nash_optimization_shows_iteration_counter(self):
        html = _render_indicator({"phase": "nash_optimization", "current": 9, "total": None})
        assert "9" in html
        assert "nash" in html.lower()
        assert "animate-spin" in html

    def test_leximin_outer_shows_determinate_bar(self):
        html = _render_indicator({"phase": "leximin_outer", "current": 8, "total": 50})
        assert "8" in html
        assert "50" in html
        assert 'role="progressbar"' in html
        assert "leximin" in html.lower()

    def test_legacy_attempt_shows_determinate_attempt_counter(self):
        html = _render_indicator({"phase": "legacy_attempt", "current": 2, "total": 10})
        assert "2" in html
        assert "10" in html
        assert 'role="progressbar"' in html

    def test_diversimax_shows_spinner_label(self):
        html = _render_indicator({"phase": "diversimax", "current": 0, "total": None})
        assert "diversimax" in html.lower()
        assert "animate-spin" in html

    def test_unknown_phase_falls_back_to_raw_name(self):
        html = _render_indicator({"phase": "mystery_future_phase", "current": 5, "total": 10})
        assert "mystery_future_phase" in html
        # Should not crash, should show some indication of progress
        assert "animate-spin" in html or 'role="progressbar"' in html
