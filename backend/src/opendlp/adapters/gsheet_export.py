"""ABOUTME: gspread-backed export target writing respondent data to Google Sheets
ABOUTME: Authenticates with the shared service account and writes one worksheet"""

from collections.abc import Callable
from typing import Any

import gspread
from gspread.exceptions import GSpreadException, WorksheetNotFound
from sortition_algorithms import make_gsheet_client, open_gsheet
from sortition_algorithms.errors import SelectionError

from opendlp import config
from opendlp.adapters.tabular_export import AbstractGSheetExportTarget, ExportTargetError, TabularData

__all__ = ["GSheetExportTarget", "WorksheetNotFound"]

# Enough headroom for a fresh worksheet; Google Sheets grows as needed.
_DEFAULT_ROWS = 1000
_DEFAULT_COLS = 26

# Exports run inside web requests, so a stalled Google API must fail before
# the gunicorn worker timeout. gspread's default is no timeout at all.
GSPREAD_TIMEOUT_SECONDS = 20
# Background exports have no worker timeout to beat, so give a slow Google API
# more room before declaring the export failed.
GSPREAD_BACKGROUND_TIMEOUT_SECONDS = 120


def _default_client_factory(background: bool = False) -> Any:
    """Build a gspread client from the shared service-account credentials.

    A background (Celery) export gets the library's default client, which
    sleeps and retries on rate limits and server errors, plus a long timeout.
    A web request gets a fail-fast client and a short timeout, so a Google
    outage cannot hold a gunicorn worker.
    """
    if background:
        return make_gsheet_client(
            config.get_google_auth_json_path(), request_timeout=GSPREAD_BACKGROUND_TIMEOUT_SECONDS
        )
    return make_gsheet_client(
        config.get_google_auth_json_path(),
        request_timeout=GSPREAD_TIMEOUT_SECONDS,
        http_client=gspread.HTTPClient,
    )


class GSheetExportTarget(AbstractGSheetExportTarget):
    """Write a table into a worksheet of an existing Google Spreadsheet.

    The service account must have edit access to the target spreadsheet
    (organisers share it with the service-account email). A ``client_factory``
    can be injected in tests so no real Google access is needed. ``background``
    is for callers outside a web request, such as a Celery task: it trades the
    fail-fast client for one that retries, with a longer timeout.
    """

    def __init__(
        self,
        spreadsheet_url: str,
        client_factory: Callable[[], Any] | None = None,
        background: bool = False,
    ) -> None:
        self.spreadsheet_url = spreadsheet_url
        self._client_factory = client_factory or (lambda: _default_client_factory(background))
        self.result_url: str = ""
        self.result_title: str = ""

    def write_sheet(self, title: str, table: TabularData) -> None:
        try:
            client = self._client_factory()
            # open_gsheet classifies the access failures (not found, not shared,
            # uploaded .xlsx) into SelectionErrors with user-facing messages
            info = open_gsheet(client, self.spreadsheet_url)
            info.require_writable()
            spreadsheet = info.spreadsheet
            try:
                worksheet = spreadsheet.worksheet(title)
                worksheet.clear()
            except WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(title=title, rows=_DEFAULT_ROWS, cols=_DEFAULT_COLS)
            worksheet.update([table.headers, *table.rows])
            self.result_url = worksheet.url
            self.result_title = spreadsheet.title
        except (SelectionError, GSpreadException, PermissionError) as exc:
            # Wrap any Google Sheets failure (missing sheet, no access, API error)
            # so callers handle one export-layer exception, not gspread internals.
            # The cause is kept: entrypoints translate a SelectionError cause
            # into a specific message. gspread raises the builtin
            # PermissionError, with an empty message, for a worksheet write the
            # account is not allowed; the readable text is on its cause.
            raise ExportTargetError(str(exc) or str(exc.__cause__)) from exc
