"""ABOUTME: Renders the full selection progress modals and asserts progress_indicator output is present.
ABOUTME: Covers both the DB and gsheet progress modal templates."""

import uuid
from types import SimpleNamespace

from flask import Flask, render_template

from opendlp import config
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.translations import gettext


def _make_app() -> Flask:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.jinja_env.globals["_"] = gettext
    app.jinja_env.globals["gettext"] = gettext
    app.jinja_env.globals["csrf_token"] = lambda: "fake-csrf-token"

    @app.route("/assembly/<uuid:assembly_id>/selection")
    def _view_assembly_selection(assembly_id):
        return ""

    @app.route("/db-modal/<uuid:assembly_id>/<uuid:run_id>")
    def _db_modal(assembly_id, run_id):
        return ""

    @app.route("/gsheet-modal/<uuid:assembly_id>/<uuid:run_id>")
    def _gsheet_modal(assembly_id, run_id):
        return ""

    @app.route("/cancel-db/<uuid:assembly_id>/<uuid:run_id>", methods=["POST"])
    def _cancel_db(assembly_id, run_id):
        return ""

    @app.route("/cancel-gsheet/<uuid:assembly_id>/<uuid:run_id>", methods=["POST"])
    def _cancel_gsheet(assembly_id, run_id):
        return ""

    @app.route("/download-selected/<uuid:assembly_id>/<uuid:run_id>")
    def _download_selected(assembly_id, run_id):
        return ""

    @app.route("/download-remaining/<uuid:assembly_id>/<uuid:run_id>")
    def _download_remaining(assembly_id, run_id):
        return ""

    # Map to the real endpoint names the templates expect via url_for.
    app.add_url_rule(
        "/gsheets/view_selection/<uuid:assembly_id>",
        endpoint="gsheets.view_assembly_selection",
        view_func=lambda assembly_id: "",
    )
    app.add_url_rule(
        "/db/modal-progress/<uuid:assembly_id>/<uuid:run_id>",
        endpoint="db_selection_backoffice.db_selection_progress_modal",
        view_func=lambda assembly_id, run_id: "",
    )
    app.add_url_rule(
        "/db/cancel/<uuid:assembly_id>/<uuid:run_id>",
        endpoint="db_selection_backoffice.cancel_db_selection",
        view_func=lambda assembly_id, run_id: "",
        methods=["POST"],
    )
    app.add_url_rule(
        "/db/download-selected/<uuid:assembly_id>/<uuid:run_id>",
        endpoint="db_selection_backoffice.download_db_selected",
        view_func=lambda assembly_id, run_id: "",
    )
    app.add_url_rule(
        "/db/download-remaining/<uuid:assembly_id>/<uuid:run_id>",
        endpoint="db_selection_backoffice.download_db_remaining",
        view_func=lambda assembly_id, run_id: "",
    )
    app.add_url_rule(
        "/gsheets/modal-progress/<uuid:assembly_id>/<uuid:run_id>",
        endpoint="gsheets.selection_progress_modal",
        view_func=lambda assembly_id, run_id: "",
    )
    app.add_url_rule(
        "/gsheets/cancel/<uuid:assembly_id>/<uuid:run_id>",
        endpoint="gsheets.cancel_selection_run",
        view_func=lambda assembly_id, run_id: "",
        methods=["POST"],
    )
    return app


def _make_run_record(progress: dict | None, task_type: SelectionTaskType) -> SimpleNamespace:
    return SimpleNamespace(
        task_type=task_type,
        task_type_verbose=task_type.value.replace("_", " "),
        status=SelectionRunStatus.RUNNING,
        is_pending=False,
        is_running=True,
        is_completed=False,
        is_failed=False,
        is_cancelled=False,
        has_finished=False,
        error_message="",
        log_messages=[],
        selected_ids=None,
        created_at=None,
        completed_at=None,
        progress=progress,
    )


def _make_assembly():
    return SimpleNamespace(id=uuid.uuid4(), url="https://example.com/sheet")


class TestDbSelectionModalWiringsProgressIndicator:
    def test_multiplicative_weights_progress_renders_determinate_bar(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = _make_run_record(
            {"phase": "multiplicative_weights", "current": 45, "total": 200, "updated_at": "x"},
            SelectionTaskType.SELECT_FROM_DB,
        )
        with app.test_request_context("/"):
            html = render_template(
                "backoffice/components/db_selection_progress_modal.html",
                assembly=assembly,
                csv_status=None,
                run_record=run_record,
                log_messages=[],
                run_report=None,
                translated_report_html="",
                current_selection=run_id,
            )
        assert 'role="progressbar"' in html
        assert "Finding diverse committees" in html

    def test_no_progress_payload_still_renders_generic_spinner(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = _make_run_record(None, SelectionTaskType.SELECT_FROM_DB)
        with app.test_request_context("/"):
            html = render_template(
                "backoffice/components/db_selection_progress_modal.html",
                assembly=assembly,
                csv_status=None,
                run_record=run_record,
                log_messages=[],
                run_report=None,
                translated_report_html="",
                current_selection=run_id,
            )
        assert "Processing" in html


class TestGsheetSelectionModalWiringsProgressIndicator:
    def test_read_gsheet_progress_renders_reading_label(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = _make_run_record(
            {"phase": "read_gsheet", "current": 0, "total": None, "updated_at": "x"},
            SelectionTaskType.LOAD_GSHEET,
        )
        with app.test_request_context("/"):
            html = render_template(
                "backoffice/components/selection_progress_modal.html",
                assembly=assembly,
                gsheet=None,
                run_record=run_record,
                log_messages=[],
                run_report=None,
                translated_report_html="",
                current_selection=run_id,
            )
        assert "Reading spreadsheet" in html

    def test_write_gsheet_progress_renders_writing_label(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = _make_run_record(
            {"phase": "write_gsheet", "current": 0, "total": None, "updated_at": "x"},
            SelectionTaskType.SELECT_GSHEET,
        )
        with app.test_request_context("/"):
            html = render_template(
                "backoffice/components/selection_progress_modal.html",
                assembly=assembly,
                gsheet=None,
                run_record=run_record,
                log_messages=[],
                run_report=None,
                translated_report_html="",
                current_selection=run_id,
            )
        assert "Writing results" in html
