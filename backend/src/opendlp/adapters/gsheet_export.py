"""ABOUTME: gspread-backed export target writing respondent data to Google Sheets
ABOUTME: Authenticates with the shared service account and writes one worksheet"""

from collections.abc import Callable
from typing import Any

import gspread
from gspread.exceptions import GSpreadException, WorksheetNotFound
from gspread.utils import rowcol_to_a1

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


def _default_client_factory(timeout_seconds: int = GSPREAD_TIMEOUT_SECONDS) -> Any:
    """Build a gspread client from the shared service-account credentials."""
    client = gspread.service_account(filename=str(config.get_google_auth_json_path()))
    client.set_timeout(timeout_seconds)
    return client


def _stale_ranges(worksheet: Any, n_rows: int, n_cols: int) -> list[str]:
    """A1 ranges of the worksheet's grid that lie beyond the freshly written block.

    Two ranges at most: the rows below the data (full width) and the columns to
    the right of it (only as tall as the data, since the rows below are already
    covered). Either is omitted when the data reaches that edge of the grid.
    """
    ranges: list[str] = []
    row_count, col_count = worksheet.row_count, worksheet.col_count
    if row_count > n_rows:
        ranges.append(f"{rowcol_to_a1(n_rows + 1, 1)}:{rowcol_to_a1(row_count, col_count)}")
    if col_count > n_cols:
        ranges.append(f"{rowcol_to_a1(1, n_cols + 1)}:{rowcol_to_a1(n_rows, col_count)}")
    return ranges


class GSheetExportTarget(AbstractGSheetExportTarget):
    """Write a table into a worksheet of an existing Google Spreadsheet.

    The service account must have edit access to the target spreadsheet
    (organisers share it with the service-account email). A ``client_factory``
    can be injected in tests so no real Google access is needed.
    """

    def __init__(
        self,
        spreadsheet_url: str,
        client_factory: Callable[[], Any] | None = None,
        timeout_seconds: int = GSPREAD_TIMEOUT_SECONDS,
    ) -> None:
        self.spreadsheet_url = spreadsheet_url
        self._client_factory = client_factory or (lambda: _default_client_factory(timeout_seconds))
        self.result_url: str = ""
        self.result_title: str = ""

    def write_sheet(self, title: str, table: TabularData) -> None:
        """Write the table over whatever the worksheet holds, then clear what lies beyond it.

        Writing first means the tab is never empty: a failure between the two
        calls leaves stale rows below fresh data rather than a blank sheet.
        """
        values = [table.headers, *table.rows]
        try:
            client = self._client_factory()
            spreadsheet = client.open_by_url(self.spreadsheet_url)
            try:
                worksheet = spreadsheet.worksheet(title)
            except WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(title=title, rows=_DEFAULT_ROWS, cols=_DEFAULT_COLS)
            worksheet.update(values)
            stale = _stale_ranges(worksheet, len(values), len(table.headers))
            if stale:
                worksheet.batch_clear(stale)
            self.result_url = worksheet.url
            self.result_title = spreadsheet.title
        except GSpreadException as exc:
            # Wrap any Google Sheets failure (missing sheet, no access, API error)
            # so callers handle one export-layer exception, not gspread internals.
            raise ExportTargetError(str(exc)) from exc
