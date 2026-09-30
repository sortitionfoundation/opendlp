# ABOUTME: Component tests for respondent CSV export over a FakeUnitOfWork
# ABOUTME: Drives the real export route + service against a seeded fake store, no PostgreSQL

import csv
from io import StringIO

import pytest
from flask.testing import FlaskClient

from opendlp.adapters.tabular_export import ExportTargetError
from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import GSheetExportKind, RespondentStatus
from tests.fakes import FakeGSheetExportTarget, FakeStore, FakeUnitOfWork


@pytest.fixture(autouse=True)
def _service_account_configured(monkeypatch):
    """The gsheet option is gated on a configured service account."""
    for target in (
        "opendlp.entrypoints.blueprints.respondents.get_service_account_email",
        "opendlp.entrypoints.gsheet_export_flow.get_service_account_email",
    ):
        monkeypatch.setattr(target, lambda: "sheets-writer@example.iam.gserviceaccount.com")


def _add_respondent(fake_store: FakeStore, assembly_id, external_id: str, status: RespondentStatus) -> None:
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.respondents.add(Respondent(assembly_id=assembly_id, external_id=external_id, selection_status=status))
        uow.commit()


def _export(client: FlaskClient, assembly_id, status: str = ""):
    return client.get(f"/backoffice/assembly/{assembly_id}/respondents/export?status={status}")


def _parse(response) -> list[dict[str, str]]:
    body = response.get_data(as_text=True).lstrip("﻿")
    return list(csv.DictReader(StringIO(body)))


class TestRespondentExportCsv:
    def test_exports_all_as_csv_download(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R-pool", RespondentStatus.POOL)
        _add_respondent(fake_store, existing_assembly.id, "R-selected", RespondentStatus.SELECTED)

        response = _export(logged_in_admin, existing_assembly.id)

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert "attachment" in response.headers["Content-Disposition"]
        ids = {row["external_id"] for row in _parse(response)}
        assert ids == {"R-pool", "R-selected"}

    def test_single_status_filter(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R-pool", RespondentStatus.POOL)
        _add_respondent(fake_store, existing_assembly.id, "R-selected", RespondentStatus.SELECTED)

        response = _export(logged_in_admin, existing_assembly.id, status="SELECTED")

        ids = {row["external_id"] for row in _parse(response)}
        assert ids == {"R-selected"}

    def test_selected_or_confirmed_filter(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R-pool", RespondentStatus.POOL)
        _add_respondent(fake_store, existing_assembly.id, "R-selected", RespondentStatus.SELECTED)
        _add_respondent(fake_store, existing_assembly.id, "R-confirmed", RespondentStatus.CONFIRMED)

        response = _export(logged_in_admin, existing_assembly.id, status="selected_or_confirmed")

        ids = {row["external_id"] for row in _parse(response)}
        assert ids == {"R-selected", "R-confirmed"}

    def test_deleted_never_exported(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R-deleted", RespondentStatus.DELETED)

        response = _export(logged_in_admin, existing_assembly.id)

        assert _parse(response) == []

    def test_invalid_status_redirects_with_flash(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _export(logged_in_admin, existing_assembly.id, status="not-a-status")
        assert response.status_code == 302

    def test_permission_denied_for_regular_user(self, logged_in_user: FlaskClient, existing_assembly: Assembly) -> None:
        response = _export(logged_in_user, existing_assembly.id)
        assert response.status_code == 302


_SHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"


class TestExportModal:
    def test_modal_renders_with_options(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.POOL)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/export/modal")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'name="destination"' in body
        assert 'name="spreadsheet_url"' in body
        assert "Selected or confirmed" in body

    def test_modal_warns_about_overwriting_the_tab(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.POOL)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/export/modal")

        body = response.get_data(as_text=True)
        assert "overwrite" in body.lower()
        assert "other tabs" in body.lower()

    def test_modal_preselects_status_from_query(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.SELECTED)

        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/export/modal?status=SELECTED"
        )

        body = response.get_data(as_text=True)
        assert '<option value="SELECTED" selected>' in body

    def test_modal_prefills_saved_gsheet_config(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.assembly_export_gsheets.add(
                AssemblyExportGSheet(
                    assembly_id=existing_assembly.id,
                    export_kind=GSheetExportKind.RESPONDENTS,
                    url=_SHEET_URL,
                    worksheet_name="Saved Tab",
                )
            )
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/export/modal")
        body = response.get_data(as_text=True)
        assert _SHEET_URL in body
        assert "Saved Tab" in body


class TestRespondentsPageGSheetLink:
    _WORKSHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit#gid=7"

    def test_link_shown_when_export_config_exists(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.POOL)
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.assembly_export_gsheets.add(
                AssemblyExportGSheet(
                    assembly_id=existing_assembly.id,
                    export_kind=GSheetExportKind.RESPONDENTS,
                    url=_SHEET_URL,
                    worksheet_name="Export tab",
                    spreadsheet_title="Assembly Data",
                    worksheet_url=self._WORKSHEET_URL,
                )
            )
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Exported to Google Sheets" in body
        assert self._WORKSHEET_URL in body
        assert "Assembly Data" in body

    def test_no_link_when_no_export_config(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.POOL)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents")

        assert "Exported to Google Sheets" not in response.get_data(as_text=True)


class TestRunExport:
    def test_run_csv_returns_download(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.SELECTED)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/export/run",
            data={"destination": "csv", "status": "SELECTED"},
        )

        assert response.status_code == 200
        assert response.mimetype == "text/csv"

    def test_run_gsheet_writes_and_saves_config(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        captured: list = []

        def factory(url: str) -> FakeGSheetExportTarget:
            target = FakeGSheetExportTarget()
            captured.append((url, target))
            return target

        logged_in_admin.application.extensions["gsheet_export_target_factory"] = factory
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.POOL)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/export/run",
            data={
                "destination": "gsheet",
                "status": "",
                "spreadsheet_url": _SHEET_URL,
                "worksheet_name": "Export tab",
            },
        )

        assert response.status_code == 302
        assert captured and captured[0][0] == _SHEET_URL
        assert captured[0][1].writes  # something was written
        with FakeUnitOfWork(store=fake_store) as uow:
            config = uow.assembly_export_gsheets.get_by_assembly_and_kind(
                existing_assembly.id, GSheetExportKind.RESPONDENTS
            )
            assert config is not None
            assert config.url == _SHEET_URL
            assert config.worksheet_name == "Export tab"

    def test_run_gsheet_flashes_success_without_url(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        def factory(url: str) -> FakeGSheetExportTarget:
            return FakeGSheetExportTarget(result_url="https://docs.google.com/spreadsheets/d/fake#gid=0")

        logged_in_admin.application.extensions["gsheet_export_target_factory"] = factory
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.POOL)

        logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/export/run",
            data={
                "destination": "gsheet",
                "status": "",
                "spreadsheet_url": _SHEET_URL,
                "worksheet_name": "Export tab",
            },
        )

        with logged_in_admin.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
        categories = [category for category, _message in flashes]
        assert "success" in categories
        # The bare worksheet URL is no longer flashed; the link lives on the page.
        assert "info" not in categories
        assert all("docs.google.com" not in message for _category, message in flashes)

    def test_run_gsheet_without_url_flashes_error(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.POOL)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/export/run",
            data={"destination": "gsheet", "status": "", "spreadsheet_url": "", "worksheet_name": "T"},
        )

        assert response.status_code == 302

    def test_run_gsheet_write_failure_flashes_error_and_saves_nothing(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        # Simulate the sheet not being shared with the service account: the target
        # raises ExportTargetError (as the real gspread adapter does on failure).
        def factory(url: str) -> FakeGSheetExportTarget:
            return FakeGSheetExportTarget(error=ExportTargetError("no access"))

        logged_in_admin.application.extensions["gsheet_export_target_factory"] = factory
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.POOL)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/export/run",
            data={
                "destination": "gsheet",
                "status": "",
                "spreadsheet_url": _SHEET_URL,
                "worksheet_name": "Export tab",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert "Could not write to the spreadsheet" in response.get_data(as_text=True)
        # The write failed before commit, so no config row should have been saved.
        with FakeUnitOfWork(store=fake_store) as uow:
            saved = uow.assembly_export_gsheets.get_by_assembly_and_kind(
                existing_assembly.id, GSheetExportKind.RESPONDENTS
            )
        assert saved is None


def _save_config(fake_store: FakeStore, assembly_id, **kwargs) -> None:
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.assembly_export_gsheets.add(
            AssemblyExportGSheet(
                assembly_id=assembly_id,
                export_kind=GSheetExportKind.RESPONDENTS,
                url=_SHEET_URL,
                worksheet_name="Export tab",
                spreadsheet_title="Assembly Data",
                worksheet_url=_SHEET_URL + "#gid=7",
                **kwargs,
            )
        )
        uow.commit()


def _saved_config(fake_store: FakeStore, assembly_id) -> AssemblyExportGSheet | None:
    with FakeUnitOfWork(store=fake_store) as uow:
        return uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly_id, GSheetExportKind.RESPONDENTS)


class TestAutoExportInModal:
    def test_modal_offers_the_checkbox_unticked_by_default(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/export/modal")

        body = response.get_data(as_text=True)
        assert 'name="auto_export"' in body
        assert "checked" not in body.split('name="auto_export"')[1].split("/>")[0]

    def test_modal_preticks_the_checkbox_when_saved_on(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _save_config(fake_store, existing_assembly.id, auto_export=True, auto_export_status_filter="")

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/export/modal")

        checkbox = response.get_data(as_text=True).split('name="auto_export"')[1].split("/>")[0]
        assert "checked" in checkbox


class TestRunExportWithAutoExport:
    def test_ticked_box_saves_the_flag_and_filter(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        """A successful export with the box ticked switches auto-export on for the chosen status."""
        logged_in_admin.application.extensions["gsheet_export_target_factory"] = lambda url: FakeGSheetExportTarget()
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.POOL)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/export/run",
            data={
                "destination": "gsheet",
                "status": "selected_or_confirmed",
                "spreadsheet_url": _SHEET_URL,
                "worksheet_name": "Export tab",
                "auto_export": "1",
            },
            follow_redirects=True,
        )

        assert "The sheet will now update automatically" in response.get_data(as_text=True)
        config = _saved_config(fake_store, existing_assembly.id)
        assert config is not None
        assert config.auto_export is True
        assert config.auto_export_status_filter == "selected_or_confirmed"

    def test_failed_write_leaves_auto_export_off(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        """The initial export must succeed before auto-export is switched on."""
        logged_in_admin.application.extensions["gsheet_export_target_factory"] = lambda url: FakeGSheetExportTarget(
            error=ExportTargetError("no access")
        )
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.POOL)

        logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/export/run",
            data={
                "destination": "gsheet",
                "status": "",
                "spreadsheet_url": _SHEET_URL,
                "worksheet_name": "Export tab",
                "auto_export": "1",
            },
        )

        assert _saved_config(fake_store, existing_assembly.id) is None

    def test_unticked_box_switches_auto_export_off(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        logged_in_admin.application.extensions["gsheet_export_target_factory"] = lambda url: FakeGSheetExportTarget()
        _save_config(fake_store, existing_assembly.id, auto_export=True, auto_export_status_filter="POOL")

        logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/export/run",
            data={
                "destination": "gsheet",
                "status": "",
                "spreadsheet_url": _SHEET_URL,
                "worksheet_name": "Export tab",
            },
        )

        config = _saved_config(fake_store, existing_assembly.id)
        assert config is not None
        assert config.auto_export is False

    def test_csv_download_leaves_auto_export_alone(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _save_config(fake_store, existing_assembly.id, auto_export=True, auto_export_status_filter="POOL")
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.POOL)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/export/run",
            data={"destination": "csv", "status": ""},
        )

        assert response.mimetype == "text/csv"
        config = _saved_config(fake_store, existing_assembly.id)
        assert config is not None
        assert config.auto_export is True
        assert config.auto_export_status_filter == "POOL"


class TestStopAutoExport:
    def test_page_shows_status_and_stop_button_when_on(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.POOL)
        _save_config(fake_store, existing_assembly.id, auto_export=True)

        body = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents").get_data(as_text=True)

        assert "Automatically exported to Google Sheets" in body
        assert "Stop automatic export" in body

    def test_page_hides_stop_button_when_off(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R1", RespondentStatus.POOL)
        _save_config(fake_store, existing_assembly.id)

        body = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents").get_data(as_text=True)

        assert "Automatically exported" not in body
        assert "Stop automatic export" not in body

    def test_stop_clears_the_flag_and_flashes(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        """Stopping never builds a Google Sheets target: it must work when the sheet is broken."""

        def factory(url: str) -> FakeGSheetExportTarget:
            raise AssertionError("stop must not touch Google Sheets")

        logged_in_admin.application.extensions["gsheet_export_target_factory"] = factory
        _save_config(fake_store, existing_assembly.id, auto_export=True)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/export/auto/stop", follow_redirects=True
        )

        assert "Automatic export stopped" in response.get_data(as_text=True)
        config = _saved_config(fake_store, existing_assembly.id)
        assert config is not None
        assert config.auto_export is False
        assert config.url == _SHEET_URL

    def test_stop_denied_for_regular_user(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _save_config(fake_store, existing_assembly.id, auto_export=True)

        response = logged_in_user.post(f"/backoffice/assembly/{existing_assembly.id}/respondents/export/auto/stop")

        assert response.status_code == 302
        config = _saved_config(fake_store, existing_assembly.id)
        assert config is not None
        assert config.auto_export is True
