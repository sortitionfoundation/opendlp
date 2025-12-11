"""ABOUTME: Integration tests for Celery task functions
ABOUTME: Tests the public Celery task API with database integration"""

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from requests.structures import CaseInsensitiveDict
from sortition_algorithms import CSVFileDataSource, GSheetDataSource, RunReport, settings
from sortition_algorithms.errors import InfeasibleQuotasError, SelectionMultilineError
from sortition_algorithms.features import FeatureValueMinMax

from opendlp.adapters.sortition_algorithms import CSVGSheetDataSource
from opendlp.bootstrap import bootstrap
from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.entrypoints.celery.tasks import (
    _update_selection_record,
    cleanup_orphaned_tasks,
    load_gsheet,
    manage_old_tabs,
    run_select,
)
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
    already_selected_file = temp_dir / f"already_selected_{uuid.uuid4()}.csv"

    return {
        "features": features_file,
        "people": people_file,
        "selected": selected_file,
        "remaining": remaining_file,
        "already_selected": already_selected_file,
    }


@pytest.fixture
def csv_gsheet_data_source(csv_files):
    """Create a CSVGSheetDataSource for testing."""
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

    def test_update_record_with_infeasible_quotas_error(self, postgres_session_factory):
        """Test updating a record with InfeasibleQuotasError - this has caused particular issues."""
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

        # Update with error in RunReport
        run_report = RunReport()
        features = CaseInsensitiveDict()
        features["feat1"] = CaseInsensitiveDict()
        features["feat1"]["value1"] = FeatureValueMinMax(min=2, max=4)
        quota_msgs = ["quota 1 problem", "quota 2 problem"]
        iq_error = InfeasibleQuotasError(features=features, output=quota_msgs)
        iq_error.args = (features, ["something", *quota_msgs])
        run_report.add_error(iq_error)
        run_report.add_error(SelectionMultilineError(["problemo 1", "problemo 2"]))
        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.FAILED,
            error_message="Something went wrong",
            run_report=run_report,
            session_factory=postgres_session_factory,
        )

        # Verify update
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.FAILED
            assert "quota 1 problem" in updated_record.run_report.as_text()
            assert "problemo 2" in updated_record.run_report.as_text()

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
            success, features, people, already_selected, report = load_gsheet(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                settings=test_settings,
                session_factory=postgres_session_factory,
            )

        # Verify success
        assert success is True
        assert features is not None
        assert people is not None
        assert already_selected is not None
        assert len(features) > 0
        assert people.count > 0
        assert already_selected.count == 0

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
            already_selected_file=tmp_path / "already_selected.csv",
        )

        mock_gsheet = Mock(spec=GSheetDataSource)
        mock_gsheet.feature_tab_name = "Features"
        mock_gsheet.people_tab_name = "People"
        mock_gsheet.already_selected_tab_name = "Already Selected"

        csv_gsheet_data_source = CSVGSheetDataSource(
            csv_data_source=csv_data_source,
            gsheet_data_source=mock_gsheet,
        )

        # Attempt to load data
        with patch.object(load_gsheet, "update_state"):
            success, features, people, already_selected, report = load_gsheet(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                settings=test_settings,
                session_factory=postgres_session_factory,
            )

        # Verify failure
        assert success is False
        assert features is None
        assert people is None
        assert already_selected is None

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


class TestOnTaskFailure:
    """Test the _on_task_failure callback."""

    def test_on_task_failure_marks_record_as_failed(self, postgres_session_factory):
        """Test that failure callback updates the SelectionRunRecord to FAILED status."""
        from opendlp.entrypoints.celery.tasks import _on_task_failure

        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()
        celery_task_id = "celery-task-123"

        # Create initial RUNNING record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.SELECT_GSHEET,
                status=SelectionRunStatus.RUNNING,
                celery_task_id=celery_task_id,
                log_messages=["Task started"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Simulate task failure by calling the callback
        test_exception = Exception("Test exception: Out of memory")
        _on_task_failure(
            self=None,  # Task instance (we don't need it for this test)
            exc=test_exception,
            task_id=celery_task_id,
            args=(),
            kwargs={"task_id": task_id, "session_factory": postgres_session_factory},
            einfo=None,
        )

        # Verify record was marked as FAILED
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.FAILED
            assert "Task failed with exception" in updated_record.error_message
            assert "contact the administrators" in updated_record.error_message
            assert updated_record.completed_at is not None
            assert any("ERROR" in msg for msg in updated_record.log_messages)

    def test_on_task_failure_handles_completed_task(self, postgres_session_factory):
        """Test that failure callback doesn't modify already completed tasks."""
        from opendlp.entrypoints.celery.tasks import _on_task_failure

        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()
        celery_task_id = "celery-task-456"

        # Create initial COMPLETED record (task finished before callback ran)
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.SELECT_GSHEET,
                status=SelectionRunStatus.COMPLETED,
                celery_task_id=celery_task_id,
                log_messages=["Task completed successfully"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Simulate task failure callback (shouldn't change anything)
        test_exception = Exception("Test exception")
        _on_task_failure(
            self=None,
            exc=test_exception,
            task_id=celery_task_id,
            args=(),
            kwargs={"task_id": task_id, "session_factory": postgres_session_factory},
            einfo=None,
        )

        # Verify record is still COMPLETED
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated_record = uow.selection_run_records.get_by_task_id(task_id)
            assert updated_record is not None
            assert updated_record.status == SelectionRunStatus.COMPLETED
            # Error message should still be empty
            assert updated_record.error_message == ""

    def test_on_task_failure_with_missing_task_id_in_kwargs(self, postgres_session_factory):
        """Test that failure callback handles missing task_id gracefully."""
        from opendlp.entrypoints.celery.tasks import _on_task_failure

        celery_task_id = "celery-task-789"

        # Call callback with no task_id in kwargs (should log error but not crash)
        test_exception = Exception("Test exception")
        # This should not raise an exception
        _on_task_failure(
            self=None,
            exc=test_exception,
            task_id=celery_task_id,
            args=(),
            kwargs={"session_factory": postgres_session_factory},  # No task_id!
            einfo=None,
        )


class TestCleanupOrphanedTasks:
    """Test the cleanup_orphaned_tasks periodic task."""

    def test_cleanup_finds_and_fixes_orphaned_running_tasks(self, postgres_session_factory):
        """Test that cleanup finds RUNNING tasks with no Celery record and marks them FAILED."""
        task1_id = uuid.uuid4()
        task2_id = uuid.uuid4()
        task3_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        # Create three tasks:
        # 1. RUNNING task with "dead" Celery task (will be marked FAILED)
        # 2. COMPLETED task (should be ignored)
        # 3. RUNNING task with active Celery task (should be left alone)
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Test Assembly")
            uow.assemblies.add(assembly)

            # Task 1: RUNNING but Celery doesn't know about it
            record1 = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task1_id,
                task_type=SelectionTaskType.SELECT_GSHEET,
                status=SelectionRunStatus.RUNNING,
                celery_task_id="dead-celery-task-123",
                log_messages=["Task started"],
            )
            uow.selection_run_records.add(record1)

            # Task 2: Already COMPLETED
            record2 = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task2_id,
                task_type=SelectionTaskType.SELECT_GSHEET,
                status=SelectionRunStatus.COMPLETED,
                celery_task_id="completed-task-456",
                log_messages=["Task completed"],
            )
            uow.selection_run_records.add(record2)

            # Task 3: RUNNING with active Celery task
            record3 = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task3_id,
                task_type=SelectionTaskType.SELECT_GSHEET,
                status=SelectionRunStatus.RUNNING,
                celery_task_id="active-task-789",
                log_messages=["Task started"],
            )
            uow.selection_run_records.add(record3)
            uow.commit()

        # Mock Celery AsyncResult to simulate dead task
        with patch("opendlp.service_layer.sortition.app.app.AsyncResult") as mock_async_result:

            def mock_result_factory(celery_task_id):
                mock_result = Mock()
                if celery_task_id == "dead-celery-task-123":
                    mock_result.state = "PENDING"  # Celery forgot about it
                elif celery_task_id == "active-task-789":
                    mock_result.state = "STARTED"  # Still running
                else:
                    mock_result.state = "SUCCESS"  # Completed
                return mock_result

            mock_async_result.side_effect = mock_result_factory

            # Run the cleanup task
            result = cleanup_orphaned_tasks(session_factory=postgres_session_factory)

        # Verify results
        assert result["checked"] == 2  # Two unfinished tasks checked
        assert result["marked_failed"] == 1  # One marked as failed
        assert result["errors"] == 0

        # Verify task 1 was marked as FAILED
        with bootstrap(session_factory=postgres_session_factory) as uow:
            updated1 = uow.selection_run_records.get_by_task_id(task1_id)
            assert updated1.status == SelectionRunStatus.FAILED
            assert "stopped unexpectedly" in updated1.error_message

            # Verify task 2 is still COMPLETED
            updated2 = uow.selection_run_records.get_by_task_id(task2_id)
            assert updated2.status == SelectionRunStatus.COMPLETED

            # Verify task 3 is still RUNNING
            updated3 = uow.selection_run_records.get_by_task_id(task3_id)
            assert updated3.status == SelectionRunStatus.RUNNING

    def test_cleanup_handles_no_unfinished_tasks(self, postgres_session_factory):
        """Test that cleanup handles case with no unfinished tasks gracefully."""
        # No tasks created

        # Run the cleanup task
        result = cleanup_orphaned_tasks(session_factory=postgres_session_factory)

        # Verify results
        assert result["checked"] == 0
        assert result["marked_failed"] == 0
        assert result["errors"] == 0
