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
    def __init__(self, title: str, row_count: int = 1000, col_count: int = 26) -> None:
        self.title = title
        self.row_count = row_count
        self.col_count = col_count
        self.updated: list[list[str]] | None = None
        self.batch_cleared: list[str] = []
        self.calls: list[str] = []
        self.url = f"https://docs.google.com/spreadsheets/d/fake#{title}"

    def update(self, values: list[list[str]]) -> None:
        self.calls.append("update")
        self.updated = values

    def batch_clear(self, ranges: list[str]) -> None:
        self.calls.append("batch_clear")
        self.batch_cleared.extend(ranges)


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

    def test_writes_over_existing_worksheet_then_trims(self):
        """An existing tab is written first and only the cells beyond the data are cleared."""
        spreadsheet = _FakeSpreadsheet()
        existing = _FakeWorksheet("Respondents", row_count=10, col_count=5)
        spreadsheet.worksheets_by_title["Respondents"] = existing
        client = _FakeClient(spreadsheet)
        target = GSheetExportTarget(spreadsheet_url=_URL, client_factory=lambda: client)

        target.write_sheet("Respondents", TabularData(headers=["id", "name"], rows=[["R1", "Alice"], ["R2", "Bob"]]))

        assert existing.calls == ["update", "batch_clear"]
        assert existing.updated == [["id", "name"], ["R1", "Alice"], ["R2", "Bob"]]
        assert existing.batch_cleared == ["A4:E10", "C1:E3"]
        assert spreadsheet.added == []

    def test_nothing_to_trim_when_data_fills_the_grid(self):
        """No clear call is made when the data reaches both edges of the worksheet."""
        spreadsheet = _FakeSpreadsheet()
        existing = _FakeWorksheet("Respondents", row_count=2, col_count=1)
        spreadsheet.worksheets_by_title["Respondents"] = existing
        client = _FakeClient(spreadsheet)
        target = GSheetExportTarget(spreadsheet_url=_URL, client_factory=lambda: client)

        target.write_sheet("Respondents", TabularData(headers=["id"], rows=[["R1"]]))

        assert existing.calls == ["update"]

    def test_trims_only_the_rows_below_when_data_spans_every_column(self):
        spreadsheet = _FakeSpreadsheet()
        existing = _FakeWorksheet("Respondents", row_count=4, col_count=2)
        spreadsheet.worksheets_by_title["Respondents"] = existing
        client = _FakeClient(spreadsheet)
        target = GSheetExportTarget(spreadsheet_url=_URL, client_factory=lambda: client)

        target.write_sheet("Respondents", TabularData(headers=["id", "name"], rows=[["R1", "Alice"]]))

        assert existing.batch_cleared == ["A3:B4"]

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
    def _capture(self, monkeypatch) -> tuple[MagicMock, list[dict]]:
        fake_client = MagicMock()
        calls: list[dict] = []

        def fake_make(auth_json_path, request_timeout, http_client=gspread.BackOffHTTPClient):
            calls.append({"path": auth_json_path, "timeout": request_timeout, "http_client": http_client})
            return fake_client

        monkeypatch.setattr(gsheet_export, "make_gsheet_client", fake_make)
        monkeypatch.setattr(gsheet_export.config, "get_google_auth_json_path", lambda: "/creds.json")
        return fake_client, calls

    def test_web_request_client_fails_fast_with_short_timeout(self, monkeypatch) -> None:
        """In a web request a stalled Google API must not hold a worker: no retries, short timeout."""
        fake_client, calls = self._capture(monkeypatch)

        client = gsheet_export._default_client_factory()

        assert client is fake_client
        assert calls == [
            {"path": "/creds.json", "timeout": gsheet_export.GSPREAD_TIMEOUT_SECONDS, "http_client": gspread.HTTPClient}
        ]

    def test_background_client_retries_with_long_timeout(self, monkeypatch) -> None:
        """A Celery export can afford the library's retrying client and a longer timeout."""
        fake_client, calls = self._capture(monkeypatch)

        client = gsheet_export._default_client_factory(background=True)

        assert client is fake_client
        assert calls == [
            {
                "path": "/creds.json",
                "timeout": gsheet_export.GSPREAD_BACKGROUND_TIMEOUT_SECONDS,
                "http_client": gspread.BackOffHTTPClient,
            }
        ]

    def test_target_background_flag_selects_the_background_client(self, monkeypatch) -> None:
        seen: list[bool] = []
        monkeypatch.setattr(gsheet_export, "_default_client_factory", lambda background=False: seen.append(background))

        GSheetExportTarget(spreadsheet_url=_URL)._client_factory()
        GSheetExportTarget(spreadsheet_url=_URL, background=True)._client_factory()

        assert seen == [False, True]
