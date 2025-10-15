"""ABOUTME: Integration tests for Celery task functions
ABOUTME: Tests the internal task functions that interact with database and run selections"""

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from sortition_algorithms import CSVFileDataSource, GSheetDataSource, adapters, settings

from opendlp.adapters.sortition_algorithms import CSVGSheetDataSource
from opendlp.bootstrap import bootstrap
from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.entrypoints.celery.tasks import (
    _internal_load_gsheet,
    _internal_run_select,
    _internal_write_selected,
    _update_selection_record,
)


class TestUpdateSelectionRecord:
    """Test the _update_selection_record helper function."""

    def test_update_record_with_log_message(self, postgres_session_factory):
        """Test updating a record with a single log message."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        # Create initial record using bootstrap
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.LOAD_GSHEET,
                status=SelectionRunStatus.PENDING,
                log_messages=["Initial message"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Update the record
        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.RUNNING,
            log_message="Running now",
            session_factory=postgres_session_factory,
        )

        # Verify update
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.RUNNING
            assert len(updated_record.log_messages) == 2
            assert updated_record.log_messages[0] == "Initial message"
            assert updated_record.log_messages[1] == "Running now"

    def test_update_record_with_log_messages_list(self, postgres_session_factory):
        """Test updating a record with multiple log messages."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        # Create initial record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.LOAD_GSHEET,
                status=SelectionRunStatus.PENDING,
                log_messages=[],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Update with multiple messages
        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.RUNNING,
            log_messages=["Message 1", "Message 2", "Message 3"],
            session_factory=postgres_session_factory,
        )

        # Verify update
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.RUNNING
            assert len(updated_record.log_messages) == 3
            assert updated_record.log_messages[0] == "Message 1"

    def test_update_record_with_error(self, postgres_session_factory):
        """Test updating a record with error message."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        # Create initial record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.LOAD_GSHEET,
                status=SelectionRunStatus.RUNNING,
                log_messages=["Started"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Update with error
        completed_time = datetime.now(UTC)
        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.FAILED,
            error_message="Something went wrong",
            completed_at=completed_time,
            session_factory=postgres_session_factory,
        )

        # Verify update
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.FAILED
            assert updated_record.error_message == "Something went wrong"
            assert updated_record.completed_at is not None

    def test_update_record_not_found_raises_error(self, postgres_session_factory):
        """Test that updating non-existent record raises ValueError."""
        non_existent_task_id = uuid.uuid4()

        with pytest.raises(ValueError, match=f"SelectionRunRecord with task_id {non_existent_task_id} not found"):
            _update_selection_record(
                task_id=non_existent_task_id,
                status=SelectionRunStatus.RUNNING,
                session_factory=postgres_session_factory,
            )


class TestInternalLoadGSheet:
    """Test the _internal_load_gsheet helper function."""

    @pytest.fixture
    def csv_files(self):
        """Create CSV files for testing."""
        test_data_dir = Path(__file__).parent.parent / "csv_fixtures" / "selection_data"
        features_file = test_data_dir / "features.csv"
        people_file = test_data_dir / "candidates.csv"

        temp_dir = Path(tempfile.gettempdir()) / "opendlp_test_output"
        temp_dir.mkdir(exist_ok=True)

        selected_file = temp_dir / f"selected_{uuid.uuid4()}.csv"
        remaining_file = temp_dir / f"remaining_{uuid.uuid4()}.csv"

        return {
            "features": features_file,
            "people": people_file,
            "selected": selected_file,
            "remaining": remaining_file,
        }

    @pytest.fixture
    def csv_gsheet_data_source(self, csv_files):
        """Create a CSVGSheetDataSource for testing."""
        csv_data_source = CSVFileDataSource(
            features_file=csv_files["features"],
            people_file=csv_files["people"],
            selected_file=csv_files["selected"],
            remaining_file=csv_files["remaining"],
        )

        mock_gsheet = Mock(spec=GSheetDataSource)
        mock_gsheet.feature_tab_name = "Features"
        mock_gsheet.people_tab_name = "People"

        return CSVGSheetDataSource(
            csv_data_source=csv_data_source,
            gsheet_data_source=mock_gsheet,
        )

    @pytest.fixture
    def test_settings(self):
        """Create test settings."""
        return settings.Settings(
            id_column="nationbuilder_id",
            check_same_address=False,
            columns_to_keep=["first_name", "last_name", "email"],
        )

    def test_load_gsheet_success(self, postgres_session_factory, csv_gsheet_data_source, test_settings):
        """Test successful loading of GSheet data."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        # Create initial record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.LOAD_GSHEET,
                status=SelectionRunStatus.PENDING,
                log_messages=[],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Create mock task object
        mock_task = Mock()

        # Load data
        select_data = adapters.SelectionData(csv_gsheet_data_source)
        success, features, people, report = _internal_load_gsheet(
            task_obj=mock_task,
            task_id=task_id,
            select_data=select_data,
            settings=test_settings,
            final_task=True,
            session_factory=postgres_session_factory,
        )

        # Verify success
        assert success is True
        assert features is not None
        assert people is not None
        assert len(features) > 0
        assert people.count > 0

        # Verify record was updated
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.COMPLETED
            assert any("Loaded" in msg and "people" in msg for msg in updated_record.log_messages)
            assert any("completed successfully" in msg for msg in updated_record.log_messages)

    def test_load_gsheet_with_invalid_csv(self, postgres_session_factory, test_settings, tmp_path):
        """Test loading with invalid CSV file."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        # Create initial record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.LOAD_GSHEET,
                status=SelectionRunStatus.PENDING,
                log_messages=[],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Create invalid CSV files (empty or malformed)
        invalid_features = tmp_path / "invalid_features.csv"
        invalid_people = tmp_path / "invalid_people.csv"
        invalid_features.write_text("")  # Empty file
        invalid_people.write_text("")  # Empty file

        csv_data_source = CSVFileDataSource(
            features_file=invalid_features,
            people_file=invalid_people,
            selected_file=tmp_path / "selected.csv",
            remaining_file=tmp_path / "remaining.csv",
        )

        mock_gsheet = Mock(spec=GSheetDataSource)
        mock_gsheet.feature_tab_name = "Features"
        mock_gsheet.people_tab_name = "People"

        csv_gsheet_data_source = CSVGSheetDataSource(
            csv_data_source=csv_data_source,
            gsheet_data_source=mock_gsheet,
        )

        mock_task = Mock()

        # Attempt to load data
        select_data = adapters.SelectionData(csv_gsheet_data_source)
        success, features, people, report = _internal_load_gsheet(
            task_obj=mock_task,
            task_id=task_id,
            select_data=select_data,
            settings=test_settings,
            final_task=True,
            session_factory=postgres_session_factory,
        )

        # Verify failure
        assert success is False
        assert features is None
        assert people is None

        # Verify record shows failure
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.FAILED
            assert updated_record.error_message != ""


class TestInternalRunSelect:
    """Test the _internal_run_select helper function."""

    @pytest.fixture
    def simple_csv_files(self, tmp_path):
        """Create simple CSV files for testing."""
        features_file = tmp_path / "features.csv"
        people_file = tmp_path / "people.csv"

        features_file.write_text(
            "feature,value,min,max,min_flex,max_flex\ngender,Male,1,2,0,2\ngender,Female,1,2,0,2\n"
        )

        people_file.write_text("id,gender\np1,Male\np2,Female\np3,Male\np4,Female\n")

        selected_file = tmp_path / "selected.csv"
        remaining_file = tmp_path / "remaining.csv"

        return {
            "features": features_file,
            "people": people_file,
            "selected": selected_file,
            "remaining": remaining_file,
        }

    @pytest.fixture
    def simple_csv_gsheet_data_source(self, simple_csv_files):
        """Create a CSVGSheetDataSource for simple testing."""
        csv_data_source = CSVFileDataSource(
            features_file=simple_csv_files["features"],
            people_file=simple_csv_files["people"],
            selected_file=simple_csv_files["selected"],
            remaining_file=simple_csv_files["remaining"],
        )

        mock_gsheet = Mock(spec=GSheetDataSource)
        mock_gsheet.feature_tab_name = "Features"
        mock_gsheet.people_tab_name = "People"

        return CSVGSheetDataSource(
            csv_data_source=csv_data_source,
            gsheet_data_source=mock_gsheet,
        )

    @pytest.fixture
    def test_settings(self):
        """Create test settings."""
        return settings.Settings(
            id_column="id",
            check_same_address=False,
            columns_to_keep=["id", "gender"],
        )

    def test_run_select_success(self, postgres_session_factory, simple_csv_gsheet_data_source, test_settings):
        """Test successful selection run."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        # Create initial record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.SELECT_GSHEET,
                status=SelectionRunStatus.PENDING,
                log_messages=[],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Load data first
        select_data = adapters.SelectionData(simple_csv_gsheet_data_source)
        features, _ = select_data.load_features()
        people, _ = select_data.load_people(test_settings, features)

        # Run selection
        success, selected_panels, report = _internal_run_select(
            task_id=task_id,
            features=features,
            people=people,
            settings=test_settings,
            number_people_wanted=2,
            test_selection=False,
            final_task=True,
            session_factory=postgres_session_factory,
        )

        # Verify success
        assert success is True
        assert len(selected_panels) > 0
        assert len(selected_panels[0]) == 2

        # Verify record was updated
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.COMPLETED
            assert any("completed successfully" in msg for msg in updated_record.log_messages)

    def test_run_select_with_test_mode(self, postgres_session_factory, simple_csv_gsheet_data_source, test_settings):
        """Test selection run in test mode."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        # Create initial record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.SELECT_GSHEET,
                status=SelectionRunStatus.PENDING,
                log_messages=[],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Load data first
        select_data = adapters.SelectionData(simple_csv_gsheet_data_source)
        features, _ = select_data.load_features()
        people, _ = select_data.load_people(test_settings, features)

        # Run selection in test mode
        success, selected_panels, report = _internal_run_select(
            task_id=task_id,
            features=features,
            people=people,
            settings=test_settings,
            number_people_wanted=2,
            test_selection=True,
            final_task=True,
            session_factory=postgres_session_factory,
        )

        # Verify success and test mode indicator in logs
        assert success is True

        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert any("TEST only" in msg for msg in updated_record.log_messages)


class TestInternalWriteSelected:
    """Test the _internal_write_selected helper function."""

    @pytest.fixture
    def csv_files(self):
        """Create CSV files for testing."""
        temp_dir = Path(tempfile.gettempdir()) / "opendlp_test_write_output"
        temp_dir.mkdir(exist_ok=True)

        test_data_dir = Path(__file__).parent.parent / "csv_fixtures" / "selection_data"
        features_file = test_data_dir / "features.csv"
        people_file = test_data_dir / "candidates.csv"

        selected_file = temp_dir / f"selected_{uuid.uuid4()}.csv"
        remaining_file = temp_dir / f"remaining_{uuid.uuid4()}.csv"

        return {
            "features": features_file,
            "people": people_file,
            "selected": selected_file,
            "remaining": remaining_file,
        }

    @pytest.fixture
    def csv_gsheet_data_source(self, csv_files):
        """Create a CSVGSheetDataSource for testing."""
        csv_data_source = CSVFileDataSource(
            features_file=csv_files["features"],
            people_file=csv_files["people"],
            selected_file=csv_files["selected"],
            remaining_file=csv_files["remaining"],
        )

        mock_gsheet = Mock(spec=GSheetDataSource)
        mock_gsheet.feature_tab_name = "Features"
        mock_gsheet.people_tab_name = "People"

        return CSVGSheetDataSource(
            csv_data_source=csv_data_source,
            gsheet_data_source=mock_gsheet,
        )

    @pytest.fixture
    def test_settings(self):
        """Create test settings."""
        return settings.Settings(
            id_column="nationbuilder_id",
            check_same_address=False,
            columns_to_keep=["nationbuilder_id", "first_name", "last_name", "email"],
        )

    def test_write_selected_success(self, postgres_session_factory, csv_gsheet_data_source, test_settings, csv_files):
        """Test successful writing of selected results."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        # Create initial record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.SELECT_GSHEET,
                status=SelectionRunStatus.RUNNING,
                log_messages=[],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Load data first
        select_data = adapters.SelectionData(csv_gsheet_data_source, gen_rem_tab=True)
        features, _ = select_data.load_features()
        people, _ = select_data.load_people(test_settings, features)

        # Create a simple selected panel (just pick first 20 people)
        selected_panel = frozenset(list(people)[:20])

        # Write selected results
        _internal_write_selected(
            task_id=task_id,
            select_data=select_data,
            features=features,
            people=people,
            settings=test_settings,
            selected_panels=[selected_panel],
            session_factory=postgres_session_factory,
        )

        # Verify files were created
        assert csv_files["selected"].exists()
        assert csv_files["remaining"].exists()

        # Verify record was updated
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.COMPLETED
            assert any("Successfully written" in msg for msg in updated_record.log_messages)
