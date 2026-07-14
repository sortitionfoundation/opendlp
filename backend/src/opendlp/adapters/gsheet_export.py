"""ABOUTME: gspread-backed export target writing respondent data to Google Sheets
ABOUTME: Authenticates with the shared service account and writes one worksheet"""

from collections.abc import Callable
from typing import Any

import gspread
from gspread.exceptions import GSpreadException, WorksheetNotFound

from opendlp import config
from opendlp.adapters.tabular_export import AbstractGSheetExportTarget, ExportTargetError, TabularData

__all__ = ["GSheetExportTarget", "WorksheetNotFound"]

# Enough headroom for a fresh worksheet; Google Sheets grows as needed.
_DEFAULT_ROWS = 1000
_DEFAULT_COLS = 26


def _default_client_factory() -> Any:
    """Build a gspread client from the shared service-account credentials."""
    return gspread.service_account(filename=str(config.get_google_auth_json_path()))


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
            spreadsheet = client.open_by_url(self.spreadsheet_url)
            try:
                worksheet = spreadsheet.worksheet(title)
                worksheet.clear()
            except WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(title=title, rows=_DEFAULT_ROWS, cols=_DEFAULT_COLS)
            worksheet.update([table.headers, *table.rows])
            self.result_url = worksheet.url
            self.result_title = spreadsheet.title
        except GSpreadException as exc:
            # Wrap any Google Sheets failure (missing sheet, no access, API error)
            # so callers handle one export-layer exception, not gspread internals.
            raise ExportTargetError(str(exc)) from exc
