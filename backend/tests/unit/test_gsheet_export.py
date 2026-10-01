"""ABOUTME: Unit tests for the gspread-backed GSheetExportTarget
ABOUTME: Uses a fake gspread client so no real Google Sheets access is needed"""

from unittest.mock import MagicMock

import gspread
import pytest
from sortition_algorithms.errors import (
    NotNativeGoogleSheetError,
    SpreadsheetNotFoundError,
    SpreadsheetNotSharedError,
    SpreadsheetReadOnlyError,
)

from opendlp.adapters import gsheet_export
from opendlp.adapters.gsheet_export import GSheetExportTarget, WorksheetNotFound
from opendlp.adapters.tabular_export import ExportTargetError, TabularData


class _FakeWorksheet:
    def __init__(self, title: str) -> None:
        self.title = title
        self.updated: list[list[str]] | None = None
        self.cleared = False
        self.url = f"https://docs.google.com/spreadsheets/d/fake#{title}"

    def clear(self) -> None:
        self.cleared = True

    def update(self, values: list[list[str]]) -> None:
        self.updated = values


class _FakeSpreadsheet:
    def __init__(self, title: str = "Assembly Data") -> None:
        self.title = title
        self.url = "https://docs.google.com/spreadsheets/d/abc"
        self.worksheets_by_title: dict[str, _FakeWorksheet] = {}
        self.added: list[str] = []

    def worksheet(self, title: str) -> _FakeWorksheet:
        if title not in self.worksheets_by_title:
            raise WorksheetNotFound(title)
        return self.worksheets_by_title[title]

    def add_worksheet(self, title: str, rows: int, cols: int) -> _FakeWorksheet:
        self.added.append(title)
        ws = _FakeWorksheet(title)
        self.worksheets_by_title[title] = ws
        return ws


_NATIVE = "application/vnd.google-apps.spreadsheet"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Recorded Drive response: the same body comes back for a missing file and for
# one that exists but is not shared with the service account.
_DRIVE_NOT_FOUND = {
    "error": {
        "code": 404,
        "message": "File not found: abc.",
        "errors": [{"message": "File not found: abc.", "domain": "global", "reason": "notFound"}],
    }
}


def _api_error(status_code: int, body: dict) -> gspread.exceptions.APIError:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = body
    return gspread.exceptions.APIError(response)


class _FakeHTTPClient:
    """Answers open_gsheet's Drive files.get, with a fixed metadata body or an APIError."""

    def __init__(self, drive_body: dict, drive_error: Exception | None = None) -> None:
        self._drive_body = drive_body
        self._drive_error = drive_error
        self.auth = MagicMock(service_account_email="robot@example.com")

    def request(self, method: str, url: str, params: dict | None = None) -> MagicMock:
        if self._drive_error is not None:
            raise self._drive_error
        response = MagicMock()
        response.json.return_value = self._drive_body
        return response


class _FakeClient:
    def __init__(
        self,
        spreadsheet: _FakeSpreadsheet,
        mimetype: str = _NATIVE,
        can_edit: bool = True,
        drive_error: Exception | None = None,
        open_error: Exception | None = None,
    ) -> None:
        self._spreadsheet = spreadsheet
        self._open_error = open_error
        self.opened_key: str | None = None
        self.http_client = _FakeHTTPClient(
            {"name": spreadsheet.title, "mimeType": mimetype, "capabilities": {"canEdit": can_edit}},
            drive_error=drive_error,
        )

    def open_by_key(self, key: str) -> _FakeSpreadsheet:
        self.opened_key = key
        if self._open_error is not None:
            raise self._open_error
        return self._spreadsheet


_URL = "https://docs.google.com/spreadsheets/d/abc/edit"


class TestGSheetExportTarget:
    def test_creates_worksheet_and_writes_values(self):
        spreadsheet = _FakeSpreadsheet()
        client = _FakeClient(spreadsheet)
        target = GSheetExportTarget(spreadsheet_url=_URL, client_factory=lambda: client)

        table = TabularData(headers=["id", "name"], rows=[["R1", "Alice"]])
        target.write_sheet("Respondents", table)

        assert client.opened_key == "abc"
        assert "Respondents" in spreadsheet.added
        ws = spreadsheet.worksheets_by_title["Respondents"]
        assert ws.updated == [["id", "name"], ["R1", "Alice"]]
        assert target.result_url == ws.url
        assert target.result_title == spreadsheet.title

    def test_clears_existing_worksheet(self):
        spreadsheet = _FakeSpreadsheet()
        existing = _FakeWorksheet("Respondents")
        spreadsheet.worksheets_by_title["Respondents"] = existing
        client = _FakeClient(spreadsheet)
        target = GSheetExportTarget(spreadsheet_url=_URL, client_factory=lambda: client)

        target.write_sheet("Respondents", TabularData(headers=["id"], rows=[["R1"]]))

        assert existing.cleared is True
        assert existing.updated == [["id"], ["R1"]]
        assert spreadsheet.added == []

    def _write(self, client: _FakeClient) -> ExportTargetError:
        target = GSheetExportTarget(spreadsheet_url=_URL, client_factory=lambda: client)
        with pytest.raises(ExportTargetError) as excinfo:
            target.write_sheet("Respondents", TabularData(headers=["a"], rows=[["1"]]))
        return excinfo.value

    def test_not_shared_spreadsheet_is_classified(self):
        """Drive says 404, the Sheets API says 403: the library turns that into SpreadsheetNotSharedError."""
        client = _FakeClient(
            _FakeSpreadsheet(),
            drive_error=_api_error(404, _DRIVE_NOT_FOUND),
            open_error=PermissionError(),
        )

        error = self._write(client)

        assert isinstance(error.__cause__, SpreadsheetNotSharedError)
        assert error.__cause__.error_params["service_account_email"] == "robot@example.com"
        assert "not shared" in str(error)

    def test_missing_spreadsheet_is_classified(self):
        client = _FakeClient(
            _FakeSpreadsheet(),
            drive_error=_api_error(404, _DRIVE_NOT_FOUND),
            open_error=gspread.exceptions.SpreadsheetNotFound(MagicMock()),
        )

        error = self._write(client)

        assert isinstance(error.__cause__, SpreadsheetNotFoundError)

    def test_read_only_spreadsheet_is_refused_before_writing(self):
        spreadsheet = _FakeSpreadsheet()
        client = _FakeClient(spreadsheet, can_edit=False)

        error = self._write(client)

        assert isinstance(error.__cause__, SpreadsheetReadOnlyError)
        assert spreadsheet.added == []

    def test_uploaded_xlsx_is_refused(self):
        error = self._write(_FakeClient(_FakeSpreadsheet("Upload.xlsx"), mimetype=_XLSX))

        assert isinstance(error.__cause__, NotNativeGoogleSheetError)
        assert "Upload.xlsx" in str(error)

    def test_worksheet_write_permission_error_is_wrapped(self):
        """gspread raises a bare PermissionError, with no message, if a later call is forbidden."""
        spreadsheet = _FakeSpreadsheet()

        def forbidden(title: str, rows: int, cols: int) -> _FakeWorksheet:
            try:
                raise gspread.exceptions.GSpreadException("APIError: [403]: The caller does not have permission")
            except gspread.exceptions.GSpreadException as exc:
                raise PermissionError from exc

        spreadsheet.add_worksheet = forbidden  # type: ignore[method-assign]

        error = self._write(_FakeClient(spreadsheet))

        assert "does not have permission" in str(error)
        assert isinstance(error.__cause__, PermissionError)


class TestDefaultClientFactory:
    def test_sets_timeout_on_gspread_client(self, monkeypatch) -> None:
        """The real client must carry a timeout so an export cannot hang a worker."""
        fake_client = MagicMock()
        monkeypatch.setattr(gsheet_export.gspread, "service_account", lambda filename: fake_client)

        client = gsheet_export._default_client_factory()

        assert client is fake_client
        fake_client.set_timeout.assert_called_once_with(gsheet_export.GSPREAD_TIMEOUT_SECONDS)
