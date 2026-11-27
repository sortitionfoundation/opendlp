"""ABOUTME: Fake Google Sheets export target and gspread client, with recorded Google API error bodies
ABOUTME: Part of the tests.fakes package of in-memory test doubles"""

from typing import Any

import gspread

from opendlp.adapters.tabular_export import AbstractGSheetExportTarget, TabularData


class FakeGSheetExportTarget(AbstractGSheetExportTarget):
    """In-memory fake Google Sheets export target for tests.

    Records each ``write_sheet`` call and exposes a fixed result URL and
    spreadsheet title, so component and unit tests can drive the export flow
    without gspread.
    """

    def __init__(
        self,
        result_url: str = "https://docs.google.com/spreadsheets/d/fake",
        result_title: str = "Fake Spreadsheet",
        error: Exception | None = None,
    ) -> None:
        self.writes: list[tuple[str, TabularData]] = []
        self.result_url = result_url
        self.result_title = result_title
        # When set, write_sheet raises this instead of recording the write, so
        # tests can drive the "sheet could not be written" failure path.
        self._error = error

    def write_sheet(self, title: str, table: TabularData) -> None:
        if self._error is not None:
            raise self._error
        self.writes.append((title, table))


# Recorded Google API error bodies, for building gspread APIErrors in tests.
# The Drive 404 body is the same for a missing file and for one that exists but
# is not shared with the service account.
GOOGLE_DRIVE_NOT_FOUND = {
    "error": {
        "code": 404,
        "message": "File not found: abc.",
        "errors": [{"message": "File not found: abc.", "domain": "global", "reason": "notFound"}],
    }
}


GOOGLE_QUOTA_EXCEEDED = {
    "error": {
        "code": 429,
        "message": "Quota exceeded for quota metric 'Read requests'",
        "errors": [{"message": "Quota exceeded", "domain": "global", "reason": "rateLimitExceeded"}],
        "status": "RESOURCE_EXHAUSTED",
    }
}


GOOGLE_SERVER_ERROR = {
    "error": {"code": 503, "message": "The service is currently unavailable.", "status": "UNAVAILABLE"}
}


GOOGLE_SHEETS_MIMETYPE = "application/vnd.google-apps.spreadsheet"


class _FakeGoogleResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body
        self.text = str(body)

    def json(self) -> dict[str, Any]:
        return self._body


def google_api_error(body: dict[str, Any]) -> gspread.exceptions.APIError:
    """A gspread APIError carrying one of the recorded error bodies above."""
    return gspread.exceptions.APIError(_FakeGoogleResponse(body))  # type: ignore[arg-type]


class _FakeGoogleAuth:
    def __init__(self, service_account_email: str) -> None:
        self.service_account_email = service_account_email


class _FakeGSpreadHTTPClient:
    """Answers open_gsheet's Drive files.get, with a fixed metadata body or an exception."""

    def __init__(self, drive_body: dict[str, Any], drive_error: Exception | None, service_account_email: str) -> None:
        self._drive_body = drive_body
        self._drive_error = drive_error
        self.auth = _FakeGoogleAuth(service_account_email)
        self.requests_made = 0

    def request(self, method: str, url: str, params: dict[str, Any] | None = None) -> _FakeGoogleResponse:
        self.requests_made += 1
        if self._drive_error is not None:
            raise self._drive_error
        return _FakeGoogleResponse(self._drive_body)


class _FakeGSpreadWorksheet:
    def __init__(self, title: str) -> None:
        self.title = title


class _FakeGSpreadSpreadsheet:
    def __init__(self, title: str, url: str, tabs: list[str]) -> None:
        self.title = title
        self.url = url
        self._tabs = tabs

    def worksheets(self) -> list[_FakeGSpreadWorksheet]:
        return [_FakeGSpreadWorksheet(tab) for tab in self._tabs]


class FakeGSpreadClient:
    """The slice of a gspread client that sortition_algorithms.open_gsheet() uses.

    Configure what Google would say: the Drive metadata (mimetype, edit access),
    an error from the Drive call, and an error from the Sheets open that
    open_gsheet() makes to classify a Drive 404.
    """

    def __init__(
        self,
        title: str = "Leeds Assembly",
        tabs: list[str] | None = None,
        mimetype: str = GOOGLE_SHEETS_MIMETYPE,
        can_edit: bool = True,
        drive_error: Exception | None = None,
        open_error: Exception | None = None,
        service_account_email: str = "robot@example.com",
        url: str = "https://docs.google.com/spreadsheets/d/abc/edit",
    ) -> None:
        self._spreadsheet = _FakeGSpreadSpreadsheet(title, url, tabs if tabs is not None else [])
        self._open_error = open_error
        self.http_client = _FakeGSpreadHTTPClient(
            {"name": title, "mimeType": mimetype, "capabilities": {"canEdit": can_edit}},
            drive_error=drive_error,
            service_account_email=service_account_email,
        )
        self.opened_keys: list[str] = []

    def open_by_key(self, key: str) -> _FakeGSpreadSpreadsheet:
        self.opened_keys.append(key)
        if self._open_error is not None:
            raise self._open_error
        return self._spreadsheet
