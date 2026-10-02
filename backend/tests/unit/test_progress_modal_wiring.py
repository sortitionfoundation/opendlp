"""ABOUTME: Renders the full selection progress modals and asserts on what they show in each state.
ABOUTME: Covers both the DB and gsheet progress modal templates: progress, sections, banner and footer."""

import uuid
from types import SimpleNamespace

from flask import Flask, render_template

from opendlp import config
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import ProgressInfo, RespondentStatus, SelectionRunStatus, SelectionTaskType
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
        "/db/download-report/<uuid:assembly_id>/<uuid:run_id>",
        endpoint="db_selection_backoffice.download_db_selection_report",
        view_func=lambda assembly_id, run_id: "",
    )
    app.add_url_rule(
        "/gsheets/modal-progress/<uuid:assembly_id>/<uuid:run_id>",
        endpoint="gsheets.selection_progress_modal",
        view_func=lambda assembly_id, run_id: "",
    )
    app.add_url_rule(
        "/respondents/<uuid:assembly_id>/<uuid:respondent_id>",
        endpoint="respondents.view_respondent",
        view_func=lambda assembly_id, respondent_id: "",
    )
    app.add_url_rule(
        "/gsheets/cancel/<uuid:assembly_id>/<uuid:run_id>",
        endpoint="gsheets.cancel_selection_run",
        view_func=lambda assembly_id, run_id: "",
        methods=["POST"],
    )
    return app


def _make_run_record(progress_info: ProgressInfo | None, task_type: SelectionTaskType) -> SimpleNamespace:
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
        progress_info=progress_info,
    )


def _make_assembly():
    return SimpleNamespace(id=uuid.uuid4(), url="https://example.com/sheet", name_fields=["Name"])


def _make_respondent(external_id: str, status: RespondentStatus = RespondentStatus.SELECTED) -> Respondent:
    return Respondent(
        assembly_id=uuid.uuid4(),
        external_id=external_id,
        selection_status=status,
        email=f"{external_id}@example.com",
        attributes={"Name": f"Person {external_id}"},
    )


def _section(html: str, title: str) -> str:
    """The details element whose summary is ``title``, so a test can look inside one section."""
    start = html.index(f"<span>{title}</span>")
    start = html.rindex("<details", 0, start)
    return html[start : html.index("</details>", start)]


class TestDbSelectionModalWiringsProgressIndicator:
    def test_multiplicative_weights_progress_renders_determinate_bar(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = _make_run_record(
            ProgressInfo(label="Finding diverse panels (45 of 200 rounds)", current=45, total=200),
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
        assert "Finding diverse panels" in html

    def test_messages_section_is_open_while_running(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = _make_run_record(ProgressInfo(label="Processing…"), SelectionTaskType.SELECT_FROM_DB)
        with app.test_request_context("/"):
            html = render_template(
                "backoffice/components/db_selection_progress_modal.html",
                assembly=assembly,
                csv_status=None,
                run_record=run_record,
                log_messages=["Reading respondents"],
                run_report=None,
                translated_report_html="",
                current_selection=run_id,
            )
        messages = _section(html, "Messages")
        assert messages.startswith('<details class="group mb-2" open>')
        assert "Reading respondents" in messages
        assert "Full run report" not in html
        assert "<span>Selected</span>" not in html

    def test_no_progress_payload_still_renders_generic_spinner(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = _make_run_record(ProgressInfo(label="Processing…"), SelectionTaskType.SELECT_FROM_DB)
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


class TestDbSelectionModalReportLink:
    def _completed_run_record(self, task_type: SelectionTaskType) -> SimpleNamespace:
        return SimpleNamespace(
            task_type=task_type,
            task_type_verbose=task_type.value.replace("_", " "),
            status=SelectionRunStatus.COMPLETED,
            is_pending=False,
            is_running=False,
            is_completed=True,
            is_failed=False,
            is_cancelled=False,
            has_finished=True,
            error_message="",
            log_messages=[],
            selected_ids=[["p1", "p2"]],
            created_at=None,
            completed_at=None,
            progress_info=None,
        )

    def _render(
        self,
        app: Flask,
        run_record: SimpleNamespace,
        run_id: uuid.UUID,
        assembly: SimpleNamespace,
        log_messages: list[str] | None = None,
        translated_report_html: str = "",
        selected_respondents: list[Respondent] | None = None,
    ) -> str:
        with app.test_request_context("/"):
            return render_template(
                "backoffice/components/db_selection_progress_modal.html",
                assembly=assembly,
                csv_status=None,
                run_record=run_record,
                log_messages=log_messages or [],
                run_report=None,
                translated_report_html=translated_report_html,
                current_selection=run_id,
                selected_respondents=selected_respondents or [],
            )

    def test_real_selection_renders_report_download_link(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = self._completed_run_record(SelectionTaskType.SELECT_FROM_DB)

        html = self._render(app, run_record, run_id, assembly)

        assert f"/db/download-report/{assembly.id}/{run_id}" in html
        assert "Download summary report" in html

    def test_test_selection_renders_report_download_link(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = self._completed_run_record(SelectionTaskType.TEST_SELECT_FROM_DB)

        html = self._render(app, run_record, run_id, assembly)

        assert f"/db/download-report/{assembly.id}/{run_id}" in html
        assert "Download summary report" in html
        assert "This was a test selection" in html

    def test_download_links_sit_in_the_footer_with_selected_as_primary(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = self._completed_run_record(SelectionTaskType.SELECT_FROM_DB)

        html = self._render(app, run_record, run_id, assembly)

        footer = html[html.index('class="dialog-footer') :]
        assert "Download selected" in footer
        assert "Download remaining" in footer
        assert "Download summary report" in footer
        assert "Close" in footer
        primary_start = footer.index("btn--primary")
        assert "Download selected" in footer[primary_start : primary_start + 400]
        assert "Download Results" not in html

    def test_banner_carries_the_closing_log_message(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = self._completed_run_record(SelectionTaskType.SELECT_FROM_DB)

        html = self._render(
            app,
            run_record,
            run_id,
            assembly,
            log_messages=["Reading respondents", "Successfully selected 2 people. 8 remain in pool."],
        )

        assert 'role="alert"' in html
        assert "Task completed successfully. Successfully selected 2 people. 8 remain in pool." in html
        assert "Result:" not in html

    def test_sections_are_collapsed_once_finished(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = self._completed_run_record(SelectionTaskType.SELECT_FROM_DB)

        html = self._render(
            app,
            run_record,
            run_id,
            assembly,
            log_messages=["Reading respondents"],
            translated_report_html="<p>Found 4 targets</p>",
        )

        for title in ("Messages", "Full run report", "Selected"):
            section = _section(html, title)
            assert "open" not in section[: section.index(">")], title
        assert "Reading respondents" in _section(html, "Messages")
        assert "Found 4 targets" in _section(html, "Full run report")

    def test_selected_section_lists_the_respondents_with_view_links(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = self._completed_run_record(SelectionTaskType.SELECT_FROM_DB)
        respondents = [_make_respondent("p1"), _make_respondent("p2", RespondentStatus.DELETED)]

        html = self._render(app, run_record, run_id, assembly, selected_respondents=respondents)

        selected = _section(html, "Selected")
        assert "Person p1" in selected
        assert "p1@example.com" in selected
        assert f"/respondents/{assembly.id}/{respondents[0].id}" in selected
        assert "Name deleted" in selected
        assert selected.count(">View</a>") == 2
        assert "Edit" not in selected

    def test_selected_section_explains_an_empty_list(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = self._completed_run_record(SelectionTaskType.SELECT_FROM_DB)

        html = self._render(app, run_record, run_id, assembly)

        assert "None of the people this run selected are in the respondent list any more." in _section(html, "Selected")


class TestGsheetSelectionModalWiringsProgressIndicator:
    def test_read_gsheet_progress_renders_reading_label(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = _make_run_record(
            ProgressInfo(label="Reading spreadsheet…", current=0, total=None),
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
            ProgressInfo(label="Writing results back to spreadsheet…", current=0, total=None),
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


class TestGsheetSelectionModalCompleted:
    def _render(self, log_messages: list[str], translated_report_html: str = "") -> tuple[str, SimpleNamespace]:
        app = _make_app()
        assembly = _make_assembly()
        run_record = _make_run_record(None, SelectionTaskType.SELECT_GSHEET)
        run_record.status = SelectionRunStatus.COMPLETED
        run_record.is_running = False
        run_record.is_completed = True
        run_record.has_finished = True
        gsheet = SimpleNamespace(url="https://docs.google.com/spreadsheets/d/abc")
        with app.test_request_context("/"):
            html = render_template(
                "backoffice/components/selection_progress_modal.html",
                assembly=assembly,
                gsheet=gsheet,
                run_record=run_record,
                log_messages=log_messages,
                run_report=None,
                translated_report_html=translated_report_html,
                current_selection=uuid.uuid4(),
            )
        return html, gsheet

    def test_banner_carries_the_closing_log_message_and_the_sheet_link(self):
        html, gsheet = self._render(["Successfully written 30 selected and 70 remaining to spreadsheet."])

        assert 'role="alert"' in html
        assert "Task completed successfully. Successfully written 30 selected and 70 remaining to spreadsheet." in html
        assert gsheet.url in html
        assert "Result:" not in html

    def test_sections_are_collapsed_and_there_is_no_selected_section(self):
        html, _gsheet = self._render(["Loaded"], translated_report_html="<p>Found 4 targets</p>")

        for title in ("Messages", "Full run report"):
            section = _section(html, title)
            assert "open" not in section[: section.index(">")], title
        assert "<span>Selected</span>" not in html
        assert "Download" not in html
        footer = html[html.index('class="dialog-footer') :]
        assert "Close" in footer
