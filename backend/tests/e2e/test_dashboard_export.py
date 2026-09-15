"""ABOUTME: End-to-end smoke tests for the dashboard export routes
ABOUTME: Real Flask + PostgreSQL round trip for the modal fragment, CSV download, and gsheet write"""

import csv
from io import StringIO

from opendlp.adapters.tabular_export import ExportTargetError
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.value_objects import GSheetExportKind
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.fakes import FakeGSheetExportTarget

VALID_DESTINATION = "https://docs.google.com/spreadsheets/d/1234567890abcdef/edit"


def _seed_gender_targets(postgres_session_factory, assembly_id):
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        uow.target_categories.add(
            TargetCategory(
                assembly_id=assembly_id,
                name="Gender",
                values=[
                    TargetValue(value="Male", min=14, max=16, percentage_target=50.0),
                    TargetValue(value="Female", min=14, max=16, percentage_target=50.0),
                ],
            )
        )
        uow.commit()


class TestDashboardExportSmoke:
    def test_export_modal_fragment(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/dashboard/export/modal")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"/backoffice/assembly/{existing_assembly.id}/dashboard/export/run" in body
        assert 'name="file_type"' in body

    def test_export_dashboard_csv(self, logged_in_admin, existing_assembly, postgres_session_factory):
        _seed_gender_targets(postgres_session_factory, existing_assembly.id)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/dashboard/export/run",
            data={"file_type": "csv"},
        )

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert "attachment" in response.headers["Content-Disposition"]
        body = response.get_data(as_text=True).lstrip("﻿")
        rows = list(csv.DictReader(StringIO(body)))
        assert {row["Value"] for row in rows} == {"Male", "Female"}
        assert rows[0]["Target"] == "Gender"

    def test_export_rejects_disabled_file_type(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/dashboard/export/run",
            data={"file_type": "xlsx"},
        )

        assert response.status_code == 302


def _fake_target_factory(captured):
    """A gsheet-target factory recording (url, target) per call, like the respondents tests."""

    def factory(url):
        target = FakeGSheetExportTarget(
            result_url="https://docs.google.com/spreadsheets/d/1234567890abcdef/edit#gid=7",
            result_title="Assembly with GSheet",
        )
        captured.append((url, target))
        return target

    return factory


class TestDashboardGSheetExportSmoke:
    def test_modal_always_asks_for_a_spreadsheet_url(self, logged_in_admin, existing_assembly, assembly_with_gsheet):
        # The destination is always caller-supplied — a gsheet-sourced assembly
        # gets the same form as any other.
        assembly, _gsheet = assembly_with_gsheet
        for assembly_id in (assembly.id, existing_assembly.id):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/dashboard/export/modal")
            assert response.status_code == 200
            body = response.get_data(as_text=True)
            assert '<input type="radio" name="file_type" value="gsheet" x-model="fileType">' in body
            assert 'name="spreadsheet_url"' in body
            assert 'name="worksheet_name"' in body

    def test_export_writes_the_supplied_spreadsheet_and_saves_config(
        self, logged_in_admin, existing_assembly, postgres_session_factory
    ):
        _seed_gender_targets(postgres_session_factory, existing_assembly.id)
        captured = []
        logged_in_admin.application.extensions["gsheet_export_target_factory"] = _fake_target_factory(captured)
        destination = "https://docs.google.com/spreadsheets/d/1234567890abcdef/edit"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/dashboard/export/run",
            data={"file_type": "gsheet", "spreadsheet_url": destination, "worksheet_name": ""},
        )

        assert response.status_code == 302
        assert captured and captured[0][0] == destination
        (title, table) = captured[0][1].writes[0]
        assert title == "Results"
        assert "Target" in table.headers

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            config = uow.assembly_export_gsheets.get_by_assembly_and_kind(
                existing_assembly.id, GSheetExportKind.DASHBOARD
            )
            assert config is not None
            assert config.url == destination
            assert config.worksheet_name == "Results"

    def test_export_requires_a_spreadsheet_url(self, logged_in_admin, existing_assembly):
        captured = []
        logged_in_admin.application.extensions["gsheet_export_target_factory"] = _fake_target_factory(captured)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/dashboard/export/run",
            data={"file_type": "gsheet", "spreadsheet_url": ""},
            follow_redirects=True,
        )

        assert "A spreadsheet URL is required" in response.get_data(as_text=True)
        assert not captured

    def test_export_rejects_a_malformed_spreadsheet_url(
        self, logged_in_admin, existing_assembly, postgres_session_factory
    ):
        _seed_gender_targets(postgres_session_factory, existing_assembly.id)
        captured = []
        logged_in_admin.application.extensions["gsheet_export_target_factory"] = _fake_target_factory(captured)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/dashboard/export/run",
            data={"file_type": "gsheet", "spreadsheet_url": "https://example.com/not-a-sheet"},
            follow_redirects=True,
        )

        assert "Could not export to Google Sheets" in response.get_data(as_text=True)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert (
                uow.assembly_export_gsheets.get_by_assembly_and_kind(existing_assembly.id, GSheetExportKind.DASHBOARD)
                is None
            )

    def test_export_flashes_when_the_sheet_cannot_be_written(
        self, logged_in_admin, existing_assembly, postgres_session_factory
    ):
        _seed_gender_targets(postgres_session_factory, existing_assembly.id)

        def failing_factory(url):
            return FakeGSheetExportTarget(error=ExportTargetError("no access"))

        logged_in_admin.application.extensions["gsheet_export_target_factory"] = failing_factory

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/dashboard/export/run",
            data={"file_type": "gsheet", "spreadsheet_url": VALID_DESTINATION},
            follow_redirects=True,
        )

        assert "Could not write to the spreadsheet" in response.get_data(as_text=True)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert (
                uow.assembly_export_gsheets.get_by_assembly_and_kind(existing_assembly.id, GSheetExportKind.DASHBOARD)
                is None
            )

    def test_write_failure_without_a_service_account_email_flashes_the_generic_message(
        self, logged_in_admin, existing_assembly, postgres_session_factory, monkeypatch
    ):
        _seed_gender_targets(postgres_session_factory, existing_assembly.id)
        monkeypatch.setattr("opendlp.entrypoints.blueprints.backoffice.get_service_account_email", lambda: "")

        def failing_factory(url):
            return FakeGSheetExportTarget(error=ExportTargetError("no access"))

        logged_in_admin.application.extensions["gsheet_export_target_factory"] = failing_factory

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/dashboard/export/run",
            data={"file_type": "gsheet", "spreadsheet_url": VALID_DESTINATION},
            follow_redirects=True,
        )

        assert "Check the URL and sharing settings" in response.get_data(as_text=True)
