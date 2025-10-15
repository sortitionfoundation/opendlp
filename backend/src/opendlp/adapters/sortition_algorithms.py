from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass

from sortition_algorithms import AbstractDataSource, CSVFileDataSource, GSheetDataSource, RunReport


@dataclass
class FakeSpreadsheet:
    title: str


class CSVGSheetDataSource(AbstractDataSource):
    """
    This is a fake that can be used by the code in tasks.py that expects a GSheetDataSource
    but where we want to actually use CSV data.

    This is for BDD tests - see `update_data_source_from_assembly_gsheet()` in bootstrap.py
    """

    def __init__(self, csv_data_source: CSVFileDataSource, gsheet_data_source: GSheetDataSource) -> None:
        self.csv_data_source = csv_data_source
        self.gsheet_data_source = gsheet_data_source
        self.spreadsheet = FakeSpreadsheet("spreadsheet title")

    @contextmanager
    def read_feature_data(
        self, report: RunReport
    ) -> Generator[tuple[Iterable[str], Iterable[dict[str, str]]], None, None]:
        with self.csv_data_source.read_feature_data(report) as feature_data:
            yield feature_data

    @contextmanager
    def read_people_data(
        self, report: RunReport
    ) -> Generator[tuple[Iterable[str], Iterable[dict[str, str]]], None, None]:
        with self.csv_data_source.read_people_data(report) as people_data:
            yield people_data

    def write_selected(self, selected: list[list[str]], report: RunReport) -> None:
        self.csv_data_source.write_selected(selected, report)

    def write_remaining(self, remaining: list[list[str]], report: RunReport) -> None:
        self.csv_data_source.write_remaining(remaining, report)

    def highlight_dupes(self, dupes: list[int]) -> None:
        self.csv_data_source.highlight_dupes(dupes)

    @property
    def feature_tab_name(self) -> str:
        return self.gsheet_data_source.feature_tab_name

    @property
    def people_tab_name(self) -> str:
        return self.gsheet_data_source.people_tab_name
