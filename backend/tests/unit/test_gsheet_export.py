"""ABOUTME: Unit tests for the gspread-backed GSheetExportTarget
ABOUTME: Uses a fake gspread client so no real Google Sheets access is needed"""

from unittest.mock import MagicMock

from opendlp.adapters import gsheet_export
from opendlp.adapters.gsheet_export import GSheetExportTarget, WorksheetNotFound
from opendlp.adapters.tabular_export import TabularData


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


class _FakeClient:
    def __init__(self, spreadsheet: _FakeSpreadsheet) -> None:
        self._spreadsheet = spreadsheet
        self.opened_url: str | None = None

    def open_by_url(self, url: str) -> _FakeSpreadsheet:
        self.opened_url = url
        return self._spreadsheet


_URL = "https://docs.google.com/spreadsheets/d/abc/edit"


class TestGSheetExportTarget:
    def test_creates_worksheet_and_writes_values(self):
        spreadsheet = _FakeSpreadsheet()
        client = _FakeClient(spreadsheet)
        target = GSheetExportTarget(spreadsheet_url=_URL, client_factory=lambda: client)

        table = TabularData(headers=["id", "name"], rows=[["R1", "Alice"]])
        target.write_sheet("Respondents", table)

        assert client.opened_url == _URL
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


class TestDefaultClientFactory:
    def test_sets_timeout_on_gspread_client(self, monkeypatch) -> None:
        """The real client must carry a timeout so an export cannot hang a worker."""
        fake_client = MagicMock()
        monkeypatch.setattr(gsheet_export.gspread, "service_account", lambda filename: fake_client)

        client = gsheet_export._default_client_factory()

        assert client is fake_client
        fake_client.set_timeout.assert_called_once_with(gsheet_export.GSPREAD_TIMEOUT_SECONDS)

    def test_target_passes_its_timeout_to_the_client(self, monkeypatch) -> None:
        """A target built with a longer timeout hands it to the gspread client it creates."""
        fake_client = MagicMock()
        monkeypatch.setattr(gsheet_export.gspread, "service_account", lambda filename: fake_client)
        target = GSheetExportTarget(spreadsheet_url=_URL, timeout_seconds=120)

        target._client_factory()

        fake_client.set_timeout.assert_called_once_with(120)
