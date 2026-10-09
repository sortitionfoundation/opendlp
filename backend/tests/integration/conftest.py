"""ABOUTME: Fixtures shared by the integration tests that drive Celery tasks over CSV-backed data.
ABOUTME: Builds a spreadsheet-shaped data source from the CSV fixtures so no Google call is made."""

import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest
from sortition_algorithms import CSVFileDataSource, GSheetDataSource

from opendlp.adapters.sortition_algorithms import CSVGSheetDataSource


@pytest.fixture
def csv_files():
    """Input CSVs from the fixtures directory and fresh output paths that start out absent."""
    test_data_dir = Path(__file__).parent.parent / "csv_fixtures" / "selection_data"
    temp_dir = Path(tempfile.gettempdir()) / "opendlp_test_celery"
    temp_dir.mkdir(exist_ok=True)
    return {
        "features": test_data_dir / "features.csv",
        "people": test_data_dir / "candidates.csv",
        "selected": temp_dir / f"selected_{uuid.uuid4()}.csv",
        "remaining": temp_dir / f"remaining_{uuid.uuid4()}.csv",
        "already_selected": temp_dir / f"already_selected_{uuid.uuid4()}.csv",
    }


@pytest.fixture
def csv_gsheet_data_source(csv_files):
    """A spreadsheet-shaped data source backed by CSV files, so no Google call is made."""
    csv_data_source = CSVFileDataSource(
        features_file=csv_files["features"],
        people_file=csv_files["people"],
        selected_file=csv_files["selected"],
        remaining_file=csv_files["remaining"],
        already_selected_file=csv_files["already_selected"],
    )
    mock_gsheet = Mock(spec=GSheetDataSource)
    mock_gsheet.feature_tab_name = "Features"
    mock_gsheet.people_tab_name = "People"
    mock_gsheet.already_selected_tab_name = "Already Selected"
    return CSVGSheetDataSource(csv_data_source=csv_data_source, gsheet_data_source=mock_gsheet)
