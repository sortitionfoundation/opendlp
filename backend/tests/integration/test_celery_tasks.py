"""ABOUTME: Integration tests for Celery task functions
ABOUTME: Tests the public Celery task API with database integration"""

import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import gspread
import pytest
from requests.structures import CaseInsensitiveDict
from sortition_algorithms import CSVFileDataSource, GSheetDataSource, RunReport, settings
from sortition_algorithms.errors import (
    InfeasibleQuotasError,
    NotNativeGoogleSheetError,
    SelectionError,
    SelectionMultilineError,
    SpreadsheetNotSharedError,
)
from sortition_algorithms.features import FeatureValueMinMax

from opendlp import config
from opendlp.adapters.sortition_algorithms import CSVGSheetDataSource
from opendlp.bootstrap import bootstrap
from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.entrypoints.celery.tasks import (
    _gsheet_api_error_message,
    _on_task_failure,
    _update_selection_record,
    cleanup_orphaned_tasks,
    load_gsheet,
    manage_old_tabs,
    monitor_selection_periodic,
    prune_monitor_run_records,
    run_select,
)
from opendlp.service_layer.exceptions import SelectionRunRecordNotFoundError
from opendlp.service_layer.monitoring import MonitorResult


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
        solver_backend=config.get_solver_backend(),
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


class TestUpdateSelectionRecordClearsProgress:
    """Terminal-status transitions should clear the live progress payload."""

    def _seed_running_record_with_progress(self, session_factory, task_id, assembly_id):
        with bootstrap(session_factory=session_factory) as uow:
            uow.assemblies.add(Assembly(assembly_id=assembly_id, title="Test Assembly"))
            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.SELECT_GSHEET,
                status=SelectionRunStatus.RUNNING,
                progress={
                    "phase": "multiplicative_weights",
                    "current": 45,
                    "total": 200,
                    "updated_at": "2026-04-09T16:00:00+00:00",
                },
            )
            uow.selection_run_records.add(record)
            uow.commit()

    def test_update_to_completed_clears_progress(self, postgres_session_factory):
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()
        self._seed_running_record_with_progress(postgres_session_factory, task_id, assembly_id)

        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.COMPLETED,
            session_factory=postgres_session_factory,
        )

        with bootstrap(session_factory=postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record is not None
            assert record.progress is None

    def test_update_to_failed_clears_progress(self, postgres_session_factory):
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()
        self._seed_running_record_with_progress(postgres_session_factory, task_id, assembly_id)

        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.FAILED,
            error_message="boom",
            session_factory=postgres_session_factory,
        )

        with bootstrap(session_factory=postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record is not None
            assert record.progress is None

    def test_update_to_cancelled_clears_progress(self, postgres_session_factory):
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()
        self._seed_running_record_with_progress(postgres_session_factory, task_id, assembly_id)

        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.CANCELLED,
            session_factory=postgres_session_factory,
        )

        with bootstrap(session_factory=postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record is not None
            assert record.progress is None

    def test_update_to_running_preserves_progress(self, postgres_session_factory):
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()
        self._seed_running_record_with_progress(postgres_session_factory, task_id, assembly_id)

        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.RUNNING,
            log_message="still going",
            session_factory=postgres_session_factory,
        )

        with bootstrap(session_factory=postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record is not None
            assert record.progress is not None
            assert record.progress["phase"] == "multiplicative_weights"
            assert record.progress["current"] == 45


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
            success, features, people, already_selected, _ = load_gsheet(
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
            success, features, people, already_selected, _ = load_gsheet(
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


def _api_error(status_code: int, body: dict) -> gspread.exceptions.APIError:
    """Build a gspread APIError from a recorded Google response body."""
    response = Mock()
    response.status_code = status_code
    response.json.return_value = body
    return gspread.exceptions.APIError(response)


# Recorded from the real Drive API. It answers 404 whether the file does not
# exist or merely is not shared with the service account.
DRIVE_NOT_FOUND_BODY = {
    "error": {
        "code": 404,
        "message": "File not found: 1j0j0FYnWp6Kl44Oym22pK3F2F-L2Y-uP6xAcedOHjnA.",
        "errors": [
            {
                "message": "File not found: 1j0j0FYnWp6Kl44Oym22pK3F2F-L2Y-uP6xAcedOHjnA.",
                "domain": "global",
                "reason": "notFound",
                "location": "fileId",
                "locationType": "parameter",
            }
        ],
    }
}
SERVER_ERROR_BODY = {"error": {"code": 500, "message": "Internal <b>error</b>", "status": "INTERNAL"}}


class TestLoadGsheetOpenFailures:
    """
    Every failure to open the spreadsheet must be caught by the task and
    written to the record. If one escapes, the user only sees the Celery
    failure callback's "Task failed with exception" message.
    """

    def _create_record(self, session_factory, task_id):
        with bootstrap(session_factory=session_factory) as uow:
            assembly_id = uuid.uuid4()
            uow.assemblies.add(Assembly(assembly_id=assembly_id, title="Test Assembly"))
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly_id,
                    task_id=task_id,
                    task_type=SelectionTaskType.LOAD_GSHEET,
                    status=SelectionRunStatus.PENDING,
                    log_messages=[],
                )
            )
            uow.commit()

    def _run_with_open_error(self, session_factory, csv_gsheet_data_source, test_settings, error):
        task_id = uuid.uuid4()
        self._create_record(session_factory, task_id)
        with (
            patch.object(load_gsheet, "update_state"),
            patch.object(csv_gsheet_data_source, "get_title", side_effect=error),
        ):
            success, features, people, already_selected, _ = load_gsheet(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                settings=test_settings,
                session_factory=session_factory,
            )
        assert success is False
        assert features is None and people is None and already_selected is None
        with bootstrap(session_factory=session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record is not None
            assert record.status == SelectionRunStatus.FAILED
            return record.error_message

    def test_unclassified_api_error_shows_google_status_and_sharing_hint(
        self, postgres_session_factory, csv_gsheet_data_source, test_settings
    ):
        """An APIError the library could not classify still reaches the record with Google's text."""
        error_message = self._run_with_open_error(
            postgres_session_factory,
            csv_gsheet_data_source,
            test_settings,
            _api_error(404, DRIVE_NOT_FOUND_BODY),
        )
        assert "404" in error_message
        assert "File not found" in error_message
        assert "shared with" in error_message
        assert "Task failed with exception" not in error_message

    def test_not_shared_error_is_translated(self, postgres_session_factory, csv_gsheet_data_source, test_settings):
        error = SpreadsheetNotSharedError(
            spreadsheet_name="https://example.com/sheet", service_account_email="robot@example.com"
        )
        error_message = self._run_with_open_error(
            postgres_session_factory, csv_gsheet_data_source, test_settings, error
        )
        assert "not shared with the service account robot@example.com" in error_message

    def test_read_only_share_fails_before_loading(
        self, postgres_session_factory, csv_gsheet_data_source, test_settings
    ):
        """A sheet shared as Viewer is refused up front, since the selection writes output tabs."""
        task_id = uuid.uuid4()
        self._create_record(postgres_session_factory, task_id)
        csv_gsheet_data_source.simulate_read_only()
        with patch.object(load_gsheet, "update_state"):
            success, features, _people, _already, _ = load_gsheet(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                settings=test_settings,
                session_factory=postgres_session_factory,
            )
        assert success is False
        assert features is None
        with bootstrap(session_factory=postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record is not None
            assert record.status == SelectionRunStatus.FAILED
            assert "read-only" in record.error_message
            assert not any("Loading targets" in msg for msg in record.log_messages)

    def test_other_api_error_shows_google_status_and_escapes_it(
        self, postgres_session_factory, csv_gsheet_data_source, test_settings
    ):
        error_message = self._run_with_open_error(
            postgres_session_factory,
            csv_gsheet_data_source,
            test_settings,
            _api_error(500, SERVER_ERROR_BODY),
        )
        assert "500" in error_message
        assert "Internal &lt;b&gt;error&lt;/b&gt;" in error_message
        assert "<b>" not in error_message

    def test_permission_error_mentions_sharing(self, postgres_session_factory, csv_gsheet_data_source, test_settings):
        error_message = self._run_with_open_error(
            postgres_session_factory, csv_gsheet_data_source, test_settings, PermissionError()
        )
        assert "permissions issues" in error_message
        assert "shared with" in error_message

    def test_spreadsheet_not_found_selection_error_is_translated(
        self, postgres_session_factory, csv_gsheet_data_source, test_settings
    ):
        error = SelectionError(
            message="Google spreadsheet not found: https://example.com/sheet.",
            error_code="spreadsheet_not_found",
            error_params={"spreadsheet_name": "https://example.com/sheet"},
        )
        error_message = self._run_with_open_error(
            postgres_session_factory, csv_gsheet_data_source, test_settings, error
        )
        assert "https://example.com/sheet" in error_message
        assert "not found" in error_message

    def test_not_native_gsheet_gives_conversion_instructions(
        self, postgres_session_factory, csv_gsheet_data_source, test_settings
    ):
        error = NotNativeGoogleSheetError(
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            file_name="Upload.xlsx",
        )
        error_message = self._run_with_open_error(
            postgres_session_factory, csv_gsheet_data_source, test_settings, error
        )
        assert "Upload.xlsx" in error_message
        assert "Save as Google Sheets" in error_message


class TestGsheetApiErrorMessage:
    def test_includes_google_code_and_message(self):
        message = _gsheet_api_error_message(_api_error(429, {"error": {"code": 429, "message": "Quota exceeded"}}))
        assert "429" in message
        assert "Quota exceeded" in message


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
            success, selected_panels, _ = run_select(
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
            success, tab_names, _ = manage_old_tabs(
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
            success, tab_names, _ = manage_old_tabs(
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

    def test_manage_old_tabs_api_error_is_reported(self, postgres_session_factory, csv_gsheet_data_source):
        """A Drive 404 while opening the spreadsheet is written to the record, not left to Celery."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()
        with bootstrap(session_factory=postgres_session_factory) as uow:
            uow.assemblies.add(Assembly(assembly_id=assembly_id, title="Test Assembly"))
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly_id,
                    task_id=task_id,
                    task_type=SelectionTaskType.DELETE_OLD_TABS,
                    status=SelectionRunStatus.PENDING,
                    log_messages=[],
                )
            )
            uow.commit()

        with (
            patch.object(manage_old_tabs, "update_state"),
            patch.object(
                csv_gsheet_data_source, "delete_old_output_tabs", side_effect=_api_error(404, DRIVE_NOT_FOUND_BODY)
            ),
        ):
            success, tab_names, _ = manage_old_tabs(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                dry_run=True,
                session_factory=postgres_session_factory,
            )

        assert success is False
        assert tab_names == []
        with bootstrap(session_factory=postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record is not None
            assert record.status == SelectionRunStatus.FAILED
            assert "404" in record.error_message
            assert "shared with" in record.error_message
            assert "Task failed with exception" not in record.error_message

    def _create_delete_tabs_record(self, session_factory, task_id):
        with bootstrap(session_factory=session_factory) as uow:
            assembly_id = uuid.uuid4()
            uow.assemblies.add(Assembly(assembly_id=assembly_id, title="Test Assembly"))
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly_id,
                    task_id=task_id,
                    task_type=SelectionTaskType.DELETE_OLD_TABS,
                    status=SelectionRunStatus.PENDING,
                    log_messages=[],
                )
            )
            uow.commit()

    def test_manage_old_tabs_delete_refuses_read_only_share(self, postgres_session_factory, csv_gsheet_data_source):
        task_id = uuid.uuid4()
        self._create_delete_tabs_record(postgres_session_factory, task_id)
        csv_gsheet_data_source.add_simulated_old_tab("Remaining - output - 2024-01-01")
        csv_gsheet_data_source.simulate_read_only()

        with patch.object(manage_old_tabs, "update_state"):
            success, tab_names, _ = manage_old_tabs(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                dry_run=False,
                session_factory=postgres_session_factory,
            )

        assert success is False
        assert tab_names == []
        assert csv_gsheet_data_source._simulated_old_tabs == ["Remaining - output - 2024-01-01"]
        with bootstrap(session_factory=postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record is not None
            assert record.status == SelectionRunStatus.FAILED
            assert "read-only" in record.error_message

    def test_manage_old_tabs_list_allowed_on_read_only_share(self, postgres_session_factory, csv_gsheet_data_source):
        """Listing does not write, so a Viewer share is enough."""
        task_id = uuid.uuid4()
        self._create_delete_tabs_record(postgres_session_factory, task_id)
        csv_gsheet_data_source.add_simulated_old_tab("Remaining - output - 2024-01-01")
        csv_gsheet_data_source.simulate_read_only()

        with patch.object(manage_old_tabs, "update_state"):
            success, tab_names, _ = manage_old_tabs(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                dry_run=True,
                session_factory=postgres_session_factory,
            )

        assert success is True
        assert tab_names == ["Remaining - output - 2024-01-01"]

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
            success, tab_names, _ = manage_old_tabs(
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

    def test_cleanup_fails_a_record_stuck_in_pending_for_over_an_hour(self, postgres_session_factory):
        """A PENDING record older than the pending timeout is FAILED so it stops holding its assembly."""
        stuck_id = uuid.uuid4()
        fresh_id = uuid.uuid4()
        assembly_id = uuid.uuid4()
        with bootstrap(session_factory=postgres_session_factory) as uow:
            uow.assemblies.add(Assembly(assembly_id=assembly_id, title="Test Assembly"))
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly_id,
                    task_id=stuck_id,
                    task_type=SelectionTaskType.SELECT_FROM_DB,
                    status=SelectionRunStatus.PENDING,
                    celery_task_id="lost-message-1",
                    created_at=datetime.now(UTC) - timedelta(minutes=config.PENDING_TASK_TIMEOUT_MINUTES + 5),
                )
            )
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly_id,
                    task_id=fresh_id,
                    task_type=SelectionTaskType.SELECT_FROM_DB,
                    status=SelectionRunStatus.PENDING,
                    celery_task_id="queued-2",
                    created_at=datetime.now(UTC) - timedelta(minutes=1),
                )
            )
            uow.commit()

        with patch("opendlp.service_layer.sortition.app.app.AsyncResult") as mock_async_result:
            mock_async_result.return_value = Mock(state="PENDING", info={})
            result = cleanup_orphaned_tasks(session_factory=postgres_session_factory)

        assert result == {"checked": 2, "marked_failed": 1, "errors": 0}
        with bootstrap(session_factory=postgres_session_factory) as uow:
            stuck = uow.selection_run_records.get_by_task_id(stuck_id)
            assert stuck.status == SelectionRunStatus.FAILED
            assert "did not start" in stuck.error_message
            assert uow.selection_run_records.get_by_task_id(fresh_id).status == SelectionRunStatus.PENDING

    def test_cleanup_handles_no_unfinished_tasks(self, postgres_session_factory):
        """Test that cleanup handles case with no unfinished tasks gracefully."""
        # No tasks created

        # Run the cleanup task
        result = cleanup_orphaned_tasks(session_factory=postgres_session_factory)

        # Verify results
        assert result["checked"] == 0
        assert result["marked_failed"] == 0
        assert result["errors"] == 0


class TestMonitorBeatTasks:
    """Tests for the monitor_selection_periodic and prune_monitor_run_records tasks."""

    def test_monitor_selection_periodic_invokes_service_and_returns_dict(self, postgres_session_factory, temp_env_vars):
        temp_env_vars(
            MONITOR_ASSEMBLY_ID=str(uuid.uuid4()),
            MONITOR_USER_ID=str(uuid.uuid4()),
        )

        fake_task_id = uuid.uuid4()
        with patch(
            "opendlp.service_layer.monitoring.run_monitoring_selection",
            return_value=MonitorResult(
                success=True,
                task_id=fake_task_id,
                duration_seconds=4.5,
                message="ok",
            ),
        ) as mock_service:
            result = monitor_selection_periodic(session_factory=postgres_session_factory)

        mock_service.assert_called_once()
        assert result == {
            "success": True,
            "duration_seconds": 4.5,
            "message": "ok",
            "task_id": str(fake_task_id),
        }

    def test_prune_monitor_run_records_keeps_successful_and_failed_buckets(
        self, postgres_session_factory, temp_env_vars
    ):
        assembly_id = uuid.uuid4()
        temp_env_vars(MONITOR_ASSEMBLY_ID=str(assembly_id), MONITOR_USER_ID=str(uuid.uuid4()))

        with bootstrap(session_factory=postgres_session_factory) as uow:
            assembly = Assembly(assembly_id=assembly_id, title="Monitor Assembly")
            uow.assemblies.add(assembly)
            uow.commit()

        with bootstrap(session_factory=postgres_session_factory) as uow:
            for i in range(5):
                uow.selection_run_records.add(
                    SelectionRunRecord(
                        assembly_id=assembly_id,
                        task_id=uuid.uuid4(),
                        status=SelectionRunStatus.COMPLETED,
                        task_type=SelectionTaskType.SELECT_GSHEET,
                        created_at=datetime.now(UTC) - timedelta(minutes=100 - i),
                    )
                )
            for i in range(3):
                uow.selection_run_records.add(
                    SelectionRunRecord(
                        assembly_id=assembly_id,
                        task_id=uuid.uuid4(),
                        status=SelectionRunStatus.FAILED,
                        task_type=SelectionTaskType.SELECT_GSHEET,
                        created_at=datetime.now(UTC) - timedelta(minutes=50 - i),
                    )
                )
            uow.commit()

        deleted = prune_monitor_run_records(session_factory=postgres_session_factory, keep_successful=2, keep_failed=2)

        # 3 completed + 1 failed pruned, newest 2 of each kept
        assert deleted == 4
        with bootstrap(session_factory=postgres_session_factory) as uow:
            remaining = list(uow.selection_run_records.get_by_assembly_id(assembly_id))
            completed = [r for r in remaining if r.status == SelectionRunStatus.COMPLETED]
            failed = [r for r in remaining if r.status == SelectionRunStatus.FAILED]
            assert len(completed) == 2
            assert len(failed) == 2

    def test_prune_monitor_run_records_no_op_when_unconfigured(self, postgres_session_factory, clear_env_vars):
        clear_env_vars("MONITOR_ASSEMBLY_ID")

        deleted = prune_monitor_run_records(session_factory=postgres_session_factory)

        assert deleted == 0
