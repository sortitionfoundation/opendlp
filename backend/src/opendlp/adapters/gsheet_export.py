"""ABOUTME: gspread-backed export target writing respondent data to Google Sheets
ABOUTME: Authenticates with the shared service account and writes one worksheet"""

from collections.abc import Callable
from typing import Any

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
# Note the library's client retries rate-limit and server errors with
# increasing sleeps, so a Google outage can hold a request longer than this.
GSPREAD_TIMEOUT_SECONDS = 20


def _default_client_factory() -> Any:
    """Build a gspread client from the shared service-account credentials, as the selection tasks do."""
    return make_gsheet_client(config.get_google_auth_json_path(), request_timeout=GSPREAD_TIMEOUT_SECONDS)


class GSheetExportTarget(AbstractGSheetExportTarget):
    """Write a table into a worksheet of an existing Google Spreadsheet.

    The service account must have edit access to the target spreadsheet
    (organisers share it with the service-account email). A ``client_factory``
    can be injected in tests so no real Google access is needed.
    """

    def __init__(
        self,
        spreadsheet_url: str,
        client_factory: Callable[[], Any] = _default_client_factory,
    ) -> None:
        self.spreadsheet_url = spreadsheet_url
        self._client_factory = client_factory
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
