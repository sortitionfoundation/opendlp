"""ABOUTME: Unit tests for database-based Celery task helpers
ABOUTME: Tests the _table_to_csv helper function used for on-demand CSV generation"""

from opendlp.service_layer.sortition import _table_to_csv


class TestTableToCsv:
    """Test the _table_to_csv helper function."""

    def test_basic_table(self):
        """Test that header and data rows are formatted correctly."""
        table = [
            ["id", "Gender", "Age"],
            ["NB001", "Male", "30-44"],
            ["NB002", "Female", "16-29"],
        ]
        result = _table_to_csv(table)
        lines = result.strip().split("\n")
        assert lines[0] == "id,Gender,Age"
        assert lines[1] == "NB001,Male,30-44"
        assert lines[2] == "NB002,Female,16-29"

    def test_empty_table(self):
        """Test that an empty table produces an empty string."""
        result = _table_to_csv([])
        assert result == ""

    def test_header_only(self):
        """Test that a single row produces a single line."""
        table = [["id", "Gender"]]
        result = _table_to_csv(table)
        lines = result.strip().split("\n")
        assert len(lines) == 1
        assert lines[0] == "id,Gender"

    def test_values_with_commas_are_quoted(self):
        """Test that values containing commas are quoted per CSV spec."""
        table = [
            ["id", "address"],
            ["NB001", "123 High Street, London"],
        ]
        result = _table_to_csv(table)
        lines = result.strip().split("\n")
        assert lines[0] == "id,address"
        assert '"123 High Street, London"' in lines[1]
