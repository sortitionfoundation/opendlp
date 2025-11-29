"""ABOUTME: Integration tests for Celery task functions
ABOUTME: Tests the public Celery task API with database integration"""

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sortition_algorithms import CSVFileDataSource, GSheetDataSource, settings

from opendlp.adapters.sortition_algorithms import CSVGSheetDataSource
from opendlp.bootstrap import bootstrap
from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.entrypoints.celery.tasks import _update_selection_record, load_gsheet, manage_old_tabs, run_select
from opendlp.service_layer.exceptions import SelectionRunRecordNotFoundError


@pytest.fixture
def csv_files():
    """Create CSV files for testing."""
    test_data_dir = Path(__file__).parent.parent / "csv_fixtures" / "selection_data"
    features_file = test_data_dir / "features.csv"
    people_file = test_data_dir / "candidates.csv"

    temp_dir = Path(tempfile.gettempdir()) / "opendlp_test_celery"
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
def csv_gsheet_data_source(csv_files):
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
def test_settings():
    """Create test settings."""
    return settings.Settings(
        id_column="nationbuilder_id",
        check_same_address=False,
        columns_to_keep=["nationbuilder_id", "first_name", "last_name", "email"],
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
        """Test that updating non-existent record raises SelectionRunRecordNotFoundError."""
        non_existent_task_id = uuid.uuid4()

        with pytest.raises(
            SelectionRunRecordNotFoundError, match=f"SelectionRunRecord with task_id {non_existent_task_id} not found"
        ):
            _update_selection_record(
                task_id=non_existent_task_id,
                status=SelectionRunStatus.RUNNING,
                session_factory=postgres_session_factory,
            )

    def test_update_record_with_selected_ids(self, postgres_session_factory):
        """Test updating a record with selected_ids."""
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

        # Update with selected_ids
        selected_ids = [["id1", "id2", "id3"], ["id4", "id5", "id6"]]
        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.COMPLETED,
            selected_ids=selected_ids,
            session_factory=postgres_session_factory,
        )

        # Verify update
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.COMPLETED
            assert updated_record.selected_ids == selected_ids
            assert len(updated_record.selected_ids) == 2
            assert updated_record.selected_ids[0] == ["id1", "id2", "id3"]
            assert updated_record.selected_ids[1] == ["id4", "id5", "id6"]


class TestLoadGSheetTask:
    """Test the load_gsheet Celery task."""

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

        # Call the actual Celery task (bind=True automatically injects self)
        # Mock update_state since we're not going through Celery's async infrastructure
        with patch.object(load_gsheet, "update_state"):
            success, features, people, _report = load_gsheet(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                settings=test_settings,
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

        # Attempt to load data
        with patch.object(load_gsheet, "update_state"):
            success, features, people, _report = load_gsheet(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                settings=test_settings,
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


class TestRunSelectTask:
    """Test the run_select Celery task (full selection workflow)."""

    def test_run_select_success(self, postgres_session_factory, csv_gsheet_data_source, test_settings, csv_files):
        """Test successful full selection workflow (load, select, write)."""
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

        # Run the full selection task
        with patch.object(run_select, "update_state"):
            success, selected_panels, _report = run_select(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                number_people_wanted=22,
                settings=test_settings,
                test_selection=False,
                gen_rem_tab=True,
                session_factory=postgres_session_factory,
            )

        # Verify success
        assert success is True
        assert len(selected_panels) > 0
        assert len(selected_panels[0]) == 22

        # Verify files were created
        assert csv_files["selected"].exists()
        assert csv_files["remaining"].exists()

        # Verify record was updated through all stages
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.COMPLETED

            # Check for log messages from different stages
            log_text = " ".join(updated_record.log_messages)
            assert "Loaded" in log_text and "people" in log_text  # From load stage
            assert "Selection completed successfully" in log_text  # From selection stage
            assert "Successfully written" in log_text  # From write stage

    def test_run_select_test_mode(self, postgres_session_factory, csv_gsheet_data_source, test_settings, csv_files):
        """Test selection in test mode (doesn't write results)."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        # Create initial record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.TEST_SELECT_GSHEET,
                status=SelectionRunStatus.PENDING,
                log_messages=[],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Run selection in test mode
        with patch.object(run_select, "update_state"):
            success, selected_panels, _report = run_select(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                number_people_wanted=22,
                settings=test_settings,
                test_selection=True,
                gen_rem_tab=True,
                session_factory=postgres_session_factory,
            )

        # Verify success
        assert success is True
        assert len(selected_panels) > 0

        # Verify test mode indicator in logs
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert any("TEST only" in msg for msg in updated_record.log_messages)

    def test_run_select_saves_selected_ids(
        self, postgres_session_factory, csv_gsheet_data_source, test_settings, csv_files
    ):
        """Test that selected_ids are properly saved when selection succeeds."""
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

        # Run the full selection task
        with patch.object(run_select, "update_state"):
            success, selected_panels, report = run_select(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                number_people_wanted=22,
                settings=test_settings,
                test_selection=False,
                gen_rem_tab=True,
                session_factory=postgres_session_factory,
            )

        # Verify success
        assert success is True
        assert len(selected_panels) > 0
        assert len(selected_panels[0]) == 22

        # Verify selected_ids were saved to the record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.selected_ids is not None
            assert len(updated_record.selected_ids) == len(selected_panels)
            # Verify conversion from frozenset to list
            assert isinstance(updated_record.selected_ids[0], list)
            # Verify the content matches
            expected_selected_ids = [list(panel) for panel in selected_panels]
            assert updated_record.selected_ids == expected_selected_ids


class TestManageOldTabsTask:
    """Test the manage_old_tabs Celery task."""

    def test_manage_old_tabs_list_success(self, postgres_session_factory, csv_gsheet_data_source):
        """Test listing old tabs with dry_run=True."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        # Add simulated old tabs
        csv_gsheet_data_source.add_simulated_old_tab("Original Selected - output - 2024-01-01")
        csv_gsheet_data_source.add_simulated_old_tab("Remaining - output - 2024-01-01")
        csv_gsheet_data_source.add_simulated_old_tab("Original Selected - output - 2024-01-02")

        # Create initial record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.DELETE_OLD_TABS,
                status=SelectionRunStatus.PENDING,
                log_messages=[],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Call the task with dry_run=True
        with patch.object(manage_old_tabs, "update_state"):
            success, tab_names, report = manage_old_tabs(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                dry_run=True,
                session_factory=postgres_session_factory,
            )

        # Verify success
        assert success is True
        assert len(tab_names) == 3
        assert "Original Selected - output - 2024-01-01" in tab_names
        assert "Remaining - output - 2024-01-01" in tab_names
        assert "Original Selected - output - 2024-01-02" in tab_names

        # Verify tabs were NOT deleted (dry run)
        assert len(csv_gsheet_data_source._simulated_old_tabs) == 3

        # Verify record was updated
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.COMPLETED
            assert any("Found 3 old output tab(s)" in msg for msg in updated_record.log_messages)

    def test_manage_old_tabs_delete_success(self, postgres_session_factory, csv_gsheet_data_source):
        """Test deleting old tabs with dry_run=False."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        # Add simulated old tabs
        csv_gsheet_data_source.add_simulated_old_tab("Original Selected - output - 2024-01-01")
        csv_gsheet_data_source.add_simulated_old_tab("Remaining - output - 2024-01-01")

        # Create initial record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.DELETE_OLD_TABS,
                status=SelectionRunStatus.PENDING,
                log_messages=[],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Call the task with dry_run=False
        with patch.object(manage_old_tabs, "update_state"):
            success, tab_names, report = manage_old_tabs(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                dry_run=False,
                session_factory=postgres_session_factory,
            )

        # Verify success
        assert success is True
        assert len(tab_names) == 2
        assert "Original Selected - output - 2024-01-01" in tab_names
        assert "Remaining - output - 2024-01-01" in tab_names

        # Verify tabs WERE deleted
        assert len(csv_gsheet_data_source._simulated_old_tabs) == 0

        # Verify record was updated
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.COMPLETED
            assert any("Successfully deleted 2 old output tab(s)" in msg for msg in updated_record.log_messages)

    def test_manage_old_tabs_empty_list(self, postgres_session_factory, csv_gsheet_data_source):
        """Test managing old tabs when there are none."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        # Don't add any simulated tabs

        # Create initial record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.DELETE_OLD_TABS,
                status=SelectionRunStatus.PENDING,
                log_messages=[],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Call the task
        with patch.object(manage_old_tabs, "update_state"):
            success, tab_names, report = manage_old_tabs(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                dry_run=False,
                session_factory=postgres_session_factory,
            )

        # Verify success with empty list
        assert success is True
        assert len(tab_names) == 0

        # Verify record was updated
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.COMPLETED
            assert any("No old output tabs found" in msg for msg in updated_record.log_messages)
