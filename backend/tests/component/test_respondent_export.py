# ABOUTME: Component tests for respondent CSV export over a FakeUnitOfWork
# ABOUTME: Drives the real export route + service against a seeded fake store, no PostgreSQL

import csv
from io import StringIO

from flask.testing import FlaskClient

from opendlp.adapters.tabular_export import ExportTargetError
from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_respondent_gsheet import AssemblyRespondentGSheet
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentStatus
from tests.fakes import FakeGSheetExportTarget, FakeStore, FakeUnitOfWork


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
            uow.assembly_respondent_gsheets.add(
                AssemblyRespondentGSheet(assembly_id=existing_assembly.id, url=_SHEET_URL, worksheet_name="Saved Tab")
            )
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/export/modal")
        body = response.get_data(as_text=True)
        assert _SHEET_URL in body
        assert "Saved Tab" in body


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
            config = uow.assembly_respondent_gsheets.get_by_assembly_id(existing_assembly.id)
            assert config is not None
            assert config.url == _SHEET_URL
            assert config.worksheet_name == "Export tab"

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
        assert "Could not write to the Google Sheet" in response.get_data(as_text=True)
        # The write failed before commit, so no config row should have been saved.
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.assembly_respondent_gsheets.get_by_assembly_id(existing_assembly.id) is None
