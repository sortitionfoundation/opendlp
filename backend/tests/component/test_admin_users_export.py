# ABOUTME: Component tests for the Site Admin users export dialog and its CSV and Google Sheets exports
# ABOUTME: Drives the real admin routes over a FakeUnitOfWork, with a fake Google Sheets target

import csv
import re
from io import StringIO

import pytest
from flask.testing import FlaskClient

from opendlp.adapters.tabular_export import ExportTargetError
from tests.fakes import FakeGSheetExportTarget

SHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"
SERVICE_ACCOUNT = "sheets-writer@example.iam.gserviceaccount.com"


@pytest.fixture(autouse=True)
def _service_account_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Google Sheets option is gated on a configured service account."""
    for target in (
        "opendlp.entrypoints.blueprints.admin.get_service_account_email",
        "opendlp.entrypoints.gsheet_export_flow.get_service_account_email",
    ):
        monkeypatch.setattr(target, lambda: SERVICE_ACCOUNT)


def _use_gsheet_target(client: FlaskClient, target: FakeGSheetExportTarget) -> list[str]:
    """Hand every export the given target, and record the spreadsheet URLs it was built for."""
    urls: list[str] = []

    def factory(url: str) -> FakeGSheetExportTarget:
        urls.append(url)
        return target

    client.application.extensions["gsheet_export_target_factory"] = factory
    return urls


class TestExportDialog:
    def test_offers_csv_and_google_sheets(self, logged_in_admin: FlaskClient) -> None:
        body = logged_in_admin.get("/admin/users/export/modal").get_data(as_text=True)

        assert "Export users" in body
        assert re.search(r'<form method="post"\s+action="/admin/users/export/run"', body)
        assert re.search(r'<input type="radio" name="file_type" value="csv"[^>]*checked', body)
        assert re.search(r'<input type="radio" name="file_type" value="gsheet" x-model="fileType">', body)
        assert f"Share the spreadsheet with {SERVICE_ACCOUNT}" in body

    def test_starts_with_no_spreadsheet_and_the_opendlp_users_tab(self, logged_in_admin: FlaskClient) -> None:
        """Nothing is remembered between exports, so the URL is always blank."""
        body = logged_in_admin.get("/admin/users/export/modal").get_data(as_text=True)

        url_input = re.search(r'<input\s+type="url"\s+name="spreadsheet_url"[^>]*>', body)
        assert url_input is not None
        assert "value=" not in url_input.group(0)
        assert re.search(r'name="worksheet_name"\s+id="users-export-tab"\s+value="OpenDLP Users"', body)

    def test_google_sheets_is_off_without_a_service_account(
        self, logged_in_admin: FlaskClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("opendlp.entrypoints.blueprints.admin.get_service_account_email", lambda: "")

        body = logged_in_admin.get("/admin/users/export/modal").get_data(as_text=True)

        assert re.search(r'<input type="radio" name="file_type" value="gsheet" disabled>', body)
        assert "Available when a Google service account is configured." in body

    def test_refused_to_a_regular_user(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/admin/users/export/modal")
        assert response.status_code in (302, 403)


class TestCsvExport:
    def test_downloads_every_user(self, logged_in_admin: FlaskClient, admin_user) -> None:
        response = logged_in_admin.post("/admin/users/export/run", data={"file_type": "csv"})

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert response.headers["Content-Disposition"] == 'attachment; filename="opendlp-users.csv"'
        rows = list(csv.DictReader(StringIO(response.get_data(as_text=True).lstrip("\ufeff"))))
        assert admin_user.email in [row["email"] for row in rows]

    def test_refused_to_a_regular_user(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.post("/admin/users/export/run", data={"file_type": "csv"})
        assert response.status_code in (302, 403)
        assert response.mimetype != "text/csv"


class TestGoogleSheetsExport:
    def test_writes_the_users_to_the_chosen_tab(self, logged_in_admin: FlaskClient, admin_user) -> None:
        target = FakeGSheetExportTarget()
        urls = _use_gsheet_target(logged_in_admin, target)

        response = logged_in_admin.post(
            "/admin/users/export/run",
            data={"file_type": "gsheet", "spreadsheet_url": SHEET_URL, "worksheet_name": "Admins only"},
            follow_redirects=True,
        )

        assert "Users exported to Google Sheets" in response.get_data(as_text=True)
        assert urls == [SHEET_URL]
        ((title, table),) = target.writes
        assert title == "Admins only"
        assert admin_user.email in [row[0] for row in table.rows]

    def test_a_blank_tab_goes_to_opendlp_users(self, logged_in_admin: FlaskClient) -> None:
        target = FakeGSheetExportTarget()
        _use_gsheet_target(logged_in_admin, target)

        logged_in_admin.post(
            "/admin/users/export/run",
            data={"file_type": "gsheet", "spreadsheet_url": SHEET_URL, "worksheet_name": ""},
        )

        ((title, _table),) = target.writes
        assert title == "OpenDLP Users"

    def test_the_spreadsheet_is_not_remembered(self, logged_in_admin: FlaskClient) -> None:
        """After an export the dialog still opens blank."""
        _use_gsheet_target(logged_in_admin, FakeGSheetExportTarget())
        logged_in_admin.post(
            "/admin/users/export/run",
            data={"file_type": "gsheet", "spreadsheet_url": SHEET_URL, "worksheet_name": "Elsewhere"},
        )

        body = logged_in_admin.get("/admin/users/export/modal").get_data(as_text=True)

        assert SHEET_URL not in body
        assert "Elsewhere" not in body
        assert 'value="OpenDLP Users"' in body

    def test_a_missing_url_writes_nothing(self, logged_in_admin: FlaskClient) -> None:
        target = FakeGSheetExportTarget()
        _use_gsheet_target(logged_in_admin, target)

        response = logged_in_admin.post(
            "/admin/users/export/run",
            data={"file_type": "gsheet", "spreadsheet_url": ""},
            follow_redirects=True,
        )

        assert "A spreadsheet URL is required to export to Google Sheets" in response.get_data(as_text=True)
        assert target.writes == []

    def test_a_url_that_is_not_a_google_sheet_writes_nothing(self, logged_in_admin: FlaskClient) -> None:
        target = FakeGSheetExportTarget()
        _use_gsheet_target(logged_in_admin, target)

        response = logged_in_admin.post(
            "/admin/users/export/run",
            data={"file_type": "gsheet", "spreadsheet_url": "https://example.com/sheet"},
            follow_redirects=True,
        )

        assert "Could not export to Google Sheets" in response.get_data(as_text=True)
        assert target.writes == []

    def test_an_unshared_sheet_says_who_to_share_it_with(self, logged_in_admin: FlaskClient) -> None:
        _use_gsheet_target(logged_in_admin, FakeGSheetExportTarget(error=ExportTargetError("forbidden")))

        response = logged_in_admin.post(
            "/admin/users/export/run",
            data={"file_type": "gsheet", "spreadsheet_url": SHEET_URL},
            follow_redirects=True,
        )

        assert f"shared with {SERVICE_ACCOUNT}" in response.get_data(as_text=True)

    def test_unavailable_without_a_service_account(
        self, logged_in_admin: FlaskClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("opendlp.entrypoints.gsheet_export_flow.get_service_account_email", lambda: "")
        target = FakeGSheetExportTarget()
        _use_gsheet_target(logged_in_admin, target)

        response = logged_in_admin.post(
            "/admin/users/export/run",
            data={"file_type": "gsheet", "spreadsheet_url": SHEET_URL},
            follow_redirects=True,
        )

        assert "no Google service account is configured" in response.get_data(as_text=True)
        assert target.writes == []


def test_an_unknown_file_type_is_refused(logged_in_admin: FlaskClient) -> None:
    response = logged_in_admin.post("/admin/users/export/run", data={"file_type": "xlsx"}, follow_redirects=True)
    assert "Only CSV and Google Sheets exports are available for now" in response.get_data(as_text=True)
