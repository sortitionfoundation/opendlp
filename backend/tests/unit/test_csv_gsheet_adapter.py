"""ABOUTME: Unit tests for CSVGSheetDataSource adapter
ABOUTME: Tests the adapter that wraps CSV data sources for use in place of GSheet data sources"""

import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sortition_algorithms import CSVFileDataSource, GSheetDataSource, RunReport

from opendlp.adapters.sortition_algorithms import CSVGSheetDataSource, FakeSpreadsheet


class TestCSVGSheetDataSource:
    """Test the CSVGSheetDataSource adapter."""

    @pytest.fixture(autouse=True)
    def reset_logging(self):
        """Reset logging handlers to avoid database writes in unit tests."""
        # Get the sortition_algorithms user logger
        user_logger = logging.getLogger("sortition_algorithms_user")
        # Store original handlers
        original_handlers = user_logger.handlers.copy()
        # Clear handlers to prevent SelectionRunRecordHandler from being used
        user_logger.handlers.clear()
        user_logger.addHandler(logging.NullHandler())
        yield
        # Restore original handlers
        user_logger.handlers = original_handlers

    @pytest.fixture
    def csv_data_source(self, tmp_path: Path):
        """Create a CSV data source for testing."""
        features_file = tmp_path / "features.csv"
        people_file = tmp_path / "people.csv"
        selected_file = tmp_path / "selected.csv"
        remaining_file = tmp_path / "remaining.csv"

        # Create minimal CSV files
        features_file.write_text("feature,value,min,max,min_flex,max_flex\ngender,Male,5,5,0,5\n")
        people_file.write_text("id,name,gender\n1,John,Male\n")

        return CSVFileDataSource(
            features_file=features_file,
            people_file=people_file,
            selected_file=selected_file,
            remaining_file=remaining_file,
        )

    @pytest.fixture
    def gsheet_data_source(self):
        """Create a mock GSheet data source for testing."""
        mock_gsheet = Mock(spec=GSheetDataSource)
        mock_gsheet.feature_tab_name = "Features"
        mock_gsheet.people_tab_name = "People"
        return mock_gsheet

    @pytest.fixture
    def adapter(self, csv_data_source, gsheet_data_source):
        """Create a CSVGSheetDataSource adapter for testing."""
        return CSVGSheetDataSource(
            csv_data_source=csv_data_source,
            gsheet_data_source=gsheet_data_source,
        )

    def test_initialization(self, adapter, csv_data_source, gsheet_data_source):
        """Test that adapter initializes correctly."""
        assert adapter.csv_data_source == csv_data_source
        assert adapter.gsheet_data_source == gsheet_data_source
        assert isinstance(adapter.spreadsheet, FakeSpreadsheet)
        assert adapter.spreadsheet.title == "spreadsheet title"

    def test_feature_tab_name_property(self, adapter, gsheet_data_source):
        """Test that feature_tab_name delegates to gsheet_data_source."""
        assert adapter.feature_tab_name == gsheet_data_source.feature_tab_name
        assert adapter.feature_tab_name == "Features"

    def test_people_tab_name_property(self, adapter, gsheet_data_source):
        """Test that people_tab_name delegates to gsheet_data_source."""
        assert adapter.people_tab_name == gsheet_data_source.people_tab_name
        assert adapter.people_tab_name == "People"

    def test_read_feature_data_delegates_to_csv(self, adapter):
        """Test that read_feature_data delegates to CSV data source."""
        report = RunReport()

        with adapter.read_feature_data(report) as (headers, rows):
            headers_list = list(headers)
            rows_list = list(rows)

            assert "feature" in headers_list
            assert "value" in headers_list
            assert len(rows_list) == 1
            assert rows_list[0]["feature"] == "gender"
            assert rows_list[0]["value"] == "Male"

    def test_read_people_data_delegates_to_csv(self, adapter):
        """Test that read_people_data delegates to CSV data source."""
        report = RunReport()

        with adapter.read_people_data(report) as (headers, rows):
            headers_list = list(headers)
            rows_list = list(rows)

            assert "id" in headers_list
            assert "name" in headers_list
            assert len(rows_list) == 1
            assert rows_list[0]["id"] == "1"
            assert rows_list[0]["name"] == "John"

    def test_write_selected_delegates_to_csv(self, adapter):
        """Test that write_selected delegates to CSV data source."""
        report = RunReport()
        selected_data = [["header1", "header2"], ["value1", "value2"]]

        adapter.write_selected(selected_data, report)

        # Verify the file was written
        selected_file = adapter.csv_data_source.selected_file
        assert selected_file.exists()
        content = selected_file.read_text()
        assert "header1" in content
        assert "value1" in content

    def test_write_remaining_delegates_to_csv(self, adapter):
        """Test that write_remaining delegates to CSV data source."""
        report = RunReport()
        remaining_data = [["header1", "header2"], ["value1", "value2"]]

        adapter.write_remaining(remaining_data, report)

        # Verify the file was written
        remaining_file = adapter.csv_data_source.remaining_file
        assert remaining_file.exists()
        content = remaining_file.read_text()
        assert "header1" in content
        assert "value1" in content

    def test_highlight_dupes_delegates_to_csv(self, adapter, csv_data_source):
        """Test that highlight_dupes delegates to CSV data source."""
        dupes = [1, 2, 3]

        # Mock the CSV data source method to track calls
        with patch.object(csv_data_source, "highlight_dupes") as mock_highlight:
            adapter.highlight_dupes(dupes)
            mock_highlight.assert_called_once_with(dupes)
