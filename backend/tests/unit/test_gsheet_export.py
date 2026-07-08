"""ABOUTME: Unit tests for the gspread-backed GSheetExportTarget
ABOUTME: Uses a fake gspread client so no real Google Sheets access is needed"""

from opendlp.adapters.gsheet_export import GSheetExportTarget, WorksheetNotFound
from opendlp.adapters.tabular_export import TabularData


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
    def __init__(self) -> None:
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
