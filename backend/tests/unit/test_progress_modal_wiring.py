"""ABOUTME: Renders the full selection progress modals and asserts on what they show in each state.
ABOUTME: Covers both the DB and gsheet progress modal templates: progress, sections, banner and footer."""

import re
import uuid
from types import SimpleNamespace
from typing import Any

from flask import Flask, render_template
from flask_babel import Babel

from opendlp import config
from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue, target_categories_to_snapshot
from opendlp.domain.value_objects import RespondentStatus, SelectionRunStatus, SelectionTaskType
from opendlp.translations import gettext


def _make_app() -> Flask:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    # Flask-Babel supplies the datetimeformat filter the finished modals use for a run's dates.
    Babel(app)
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


def _make_run_record(
    progress: dict[str, Any] | None,
    task_type: SelectionTaskType,
    status: SelectionRunStatus = SelectionRunStatus.RUNNING,
    selected_ids: list[list[str]] | None = None,
    targets_used: list[dict[str, Any]] | None = None,
) -> SelectionRunRecord:
    return SelectionRunRecord(
        assembly_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        task_type=task_type,
        status=status,
        progress=progress,
        selected_ids=selected_ids,
        targets_used=targets_used or [],
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


def _row_cells(html: str, first_cell: str) -> list[str]:
    """The text of each cell in the table row whose first cell reads ``first_cell``."""
    for row in re.findall(r"<tr.*?</tr>", html, flags=re.DOTALL):
        cells = [re.sub(r"<[^>]+>", "", cell).strip() for cell in re.findall(r"<td.*?</td>", row, flags=re.DOTALL)]
        if cells and cells[0] == first_cell:
            return cells
    return []


class TestDbSelectionModalWiringsProgressIndicator:
    def test_multiplicative_weights_progress_renders_determinate_bar(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = _make_run_record(
            {"phase": "multiplicative_weights", "current": 45, "total": 200},
            SelectionTaskType.SELECT_FROM_DB,
        )
        with app.test_request_context("/"):
            html = render_template(
                "backoffice/components/db_selection_progress_modal.html",
                assembly=assembly,
                csv_status=None,
                run_record=run_record,
                run_names={},
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
        run_record = _make_run_record(None, SelectionTaskType.SELECT_FROM_DB)
        with app.test_request_context("/"):
            html = render_template(
                "backoffice/components/db_selection_progress_modal.html",
                assembly=assembly,
                csv_status=None,
                run_record=run_record,
                run_names={},
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
        run_record = _make_run_record(None, SelectionTaskType.SELECT_FROM_DB)
        with app.test_request_context("/"):
            html = render_template(
                "backoffice/components/db_selection_progress_modal.html",
                assembly=assembly,
                csv_status=None,
                run_record=run_record,
                run_names={},
                log_messages=[],
                run_report=None,
                translated_report_html="",
                current_selection=run_id,
            )
        assert "Processing" in html


class TestDbSelectionModalReportLink:
    def _completed_run_record(self, task_type: SelectionTaskType) -> SelectionRunRecord:
        return _make_run_record(None, task_type, status=SelectionRunStatus.COMPLETED, selected_ids=[["p1", "p2"]])

    def _render(
        self,
        app: Flask,
        run_record: SelectionRunRecord,
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
                run_names={},
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

    def test_download_links_sit_in_a_collapsed_section_with_selected_as_primary(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = self._completed_run_record(SelectionTaskType.SELECT_FROM_DB)

        html = self._render(app, run_record, run_id, assembly)

        downloads = _section(html, "CSV Downloads")
        assert "open" not in downloads[: downloads.index(">")]
        assert "Download selected" in downloads
        assert "Download remaining" in downloads
        assert "Download summary report" in downloads
        primary_start = downloads.index("btn--primary")
        assert "Download selected" in downloads[primary_start : primary_start + 400]
        assert "Download Results" not in html

    def test_finished_run_has_no_footer_and_no_close_link(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()

        for task_type in (SelectionTaskType.SELECT_FROM_DB, SelectionTaskType.TEST_SELECT_FROM_DB):
            html = self._render(app, self._completed_run_record(task_type), run_id, assembly)
            assert 'class="dialog-footer' not in html
            assert ">Close<" not in html

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


def _initial_targets_snapshot() -> list[dict[str, Any]]:
    assembly_id = uuid.uuid4()
    return target_categories_to_snapshot([
        TargetCategory(
            assembly_id=assembly_id,
            name="Gender",
            values=[TargetValue(value="Woman", min=11, max=13), TargetValue(value="Man", min=10, max=12)],
        ),
        TargetCategory(
            assembly_id=assembly_id,
            name="Age",
            sort_order=1,
            values=[TargetValue(value="16-29", min=4, max=6), TargetValue(value="30+", min=17, max=19)],
        ),
    ])


def _replacement_targets_snapshot() -> list[dict[str, Any]]:
    """One category in the shape a replacement run stores: the numbers still needed, beside what was held."""
    return [
        {
            "name": "Gender",
            "sort_order": 0,
            "comment": "",
            "source_url": "",
            "values": [
                {
                    "value": "Woman",
                    "min": 2,
                    "max": 3,
                    "min_flex": 0,
                    "max_flex": 3,
                    "percentage_target": None,
                    "comment": "",
                    "minmax_manual": False,
                    "overall_min": 11,
                    "overall_max": 13,
                    "held": 9,
                    "calculated_min": 2,
                    "calculated_max": 4,
                    "calculated_min_flex": 0,
                    "calculated_max_flex": 4,
                },
            ],
        }
    ]


class TestDbSelectionModalTargets:
    def _render(self, run_record: SelectionRunRecord) -> str:
        app = _make_app()
        with app.test_request_context("/"):
            return render_template(
                "backoffice/components/db_selection_progress_modal.html",
                assembly=_make_assembly(),
                csv_status=None,
                run_record=run_record,
                run_names={},
                log_messages=[],
                run_report=None,
                translated_report_html="",
                current_selection=uuid.uuid4(),
                selected_respondents=[],
            )

    def test_no_section_without_recorded_targets(self):
        run_record = _make_run_record(
            None, SelectionTaskType.SELECT_FROM_DB, status=SelectionRunStatus.COMPLETED, selected_ids=[["p1"]]
        )

        html = self._render(run_record)

        assert "<span>Targets</span>" not in html

    def test_initial_selection_lists_each_target_with_its_min_and_max(self):
        run_record = _make_run_record(
            None,
            SelectionTaskType.SELECT_FROM_DB,
            status=SelectionRunStatus.COMPLETED,
            selected_ids=[["p1"]],
            targets_used=_initial_targets_snapshot(),
        )

        targets = _section(self._render(run_record), "Targets")

        assert "open" not in targets[: targets.index(">")]
        assert targets.count("<table") == 2
        assert targets.index("Gender") < targets.index("Age")
        assert targets.count("<th ") == 6
        for heading in ("Value", "Min", "Max"):
            assert heading in targets
        assert _row_cells(targets, "Woman") == ["Woman", "11", "13"]
        assert _row_cells(targets, "16-29") == ["16-29", "4", "6"]
        assert "Currently selected" not in targets
        assert "Still needed" not in targets

    def test_replacement_selection_shows_what_was_held_beside_what_was_still_needed(self):
        run_record = _make_run_record(
            None,
            SelectionTaskType.SELECT_REPLACEMENT_FROM_DB,
            status=SelectionRunStatus.COMPLETED,
            selected_ids=[["p1"]],
            targets_used=_replacement_targets_snapshot(),
        )

        targets = _section(self._render(run_record), "Targets")

        for heading in ("Value", "Target", "Currently selected", "Still needed (min)", "Still needed (max)"):
            assert heading in targets
        assert targets.count("<th ") == 5
        assert _row_cells(targets, "Woman") == ["Woman", "11–13", "9", "2", "3"]

    def test_targets_show_while_the_run_is_still_going(self):
        run_record = _make_run_record(None, SelectionTaskType.SELECT_FROM_DB, targets_used=_initial_targets_snapshot())

        targets = _section(self._render(run_record), "Targets")

        assert _row_cells(targets, "Man") == ["Man", "10", "12"]


class TestGsheetSelectionModalWiringsProgressIndicator:
    def test_read_gsheet_progress_renders_reading_label(self):
        app = _make_app()
        run_id = uuid.uuid4()
        assembly = _make_assembly()
        run_record = _make_run_record(
            {"phase": "read_gsheet"},
            SelectionTaskType.LOAD_GSHEET,
        )
        with app.test_request_context("/"):
            html = render_template(
                "backoffice/components/selection_progress_modal.html",
                assembly=assembly,
                gsheet=None,
                run_record=run_record,
                run_names={},
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
            {"phase": "write_gsheet"},
            SelectionTaskType.SELECT_GSHEET,
        )
        with app.test_request_context("/"):
            html = render_template(
                "backoffice/components/selection_progress_modal.html",
                assembly=assembly,
                gsheet=None,
                run_record=run_record,
                run_names={},
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
        run_record = _make_run_record(None, SelectionTaskType.SELECT_GSHEET, status=SelectionRunStatus.COMPLETED)
        gsheet = SimpleNamespace(url="https://docs.google.com/spreadsheets/d/abc")
        with app.test_request_context("/"):
            html = render_template(
                "backoffice/components/selection_progress_modal.html",
                assembly=assembly,
                gsheet=gsheet,
                run_record=run_record,
                run_names={},
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
