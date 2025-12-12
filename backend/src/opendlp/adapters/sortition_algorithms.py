from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from sortition_algorithms import AbstractDataSource, CSVFileDataSource, GSheetDataSource, RunReport, errors


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
        # For testing delete_old_output_tabs functionality
        self._simulated_old_tabs: list[str] = []

    @property
    def people_data_container(self) -> str:
        return self.gsheet_data_source.people_data_container

    @property
    def already_selected_data_container(self) -> str:
        return self.gsheet_data_source.already_selected_data_container

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

    @contextmanager
    def read_already_selected_data(
        self, report: RunReport
    ) -> Generator[tuple[Iterable[str], Iterable[dict[str, str]]], None, None]:
        with self.csv_data_source.read_already_selected_data(report) as people_data:
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

    @property
    def already_selected_tab_name(self) -> str:
        return self.gsheet_data_source.already_selected_tab_name

    @property
    def _g_sheet_name(self) -> str:
        return self.gsheet_data_source._g_sheet_name

    def delete_old_output_tabs(self, dry_run: bool = False) -> list[str]:
        """
        Simulate deleting old output tabs for testing.

        In test mode, this tracks simulated tabs and optionally clears them.

        Args:
            dry_run: If True, return list of tabs without deleting. If False, delete and return list.

        Returns:
            List of tab names that were (or would be) deleted.
        """
        tabs_to_delete = self._simulated_old_tabs.copy()

        if not dry_run:
            # Actually "delete" the tabs by clearing the list
            self._simulated_old_tabs.clear()

        return tabs_to_delete

    def add_simulated_old_tab(self, tab_name: str) -> None:
        """Add a simulated old tab for testing purposes."""
        self._simulated_old_tabs.append(tab_name)

    def customise_features_parse_error(
        self, error: errors.ParseTableMultiError, headers: Sequence[str]
    ) -> errors.SelectionMultilineError:
        return error

    def customise_people_parse_error(
        self, error: errors.ParseTableMultiError, headers: Sequence[str]
    ) -> errors.SelectionMultilineError:
        return error

    def customise_already_selected_parse_error(
        self, error: errors.ParseTableMultiError, headers: Sequence[str]
    ) -> errors.SelectionMultilineError:
        return error
