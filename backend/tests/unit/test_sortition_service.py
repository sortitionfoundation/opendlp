"""ABOUTME: Unit tests for sortition service layer operations
ABOUTME: Tests Google Sheets loading task management and selection run monitoring with fake repositories"""

import pickle
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sortition_algorithms import GSheetDataSource, RunReport

from opendlp.adapters.sortition_data_adapter import DB_ID_COLUMN
from opendlp.domain.assembly import Assembly, AssemblyGSheet, SelectionRunRecord
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondents import Respondent
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import (
    GlobalRole,
    ManageOldTabsState,
    RespondentStatus,
    SelectionRunStatus,
    SelectionTaskType,
)
from opendlp.service_layer import sortition
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    GoogleSheetConfigNotFoundError,
    InsufficientPermissions,
    InvalidSelection,
)
from opendlp.service_layer.task_runner import TaskDispatchError, TaskStatus
from tests.data import VALID_GSHEET_URL
from tests.fakes import FakeUnitOfWork
from tests.fakes.tasks import RecordingTaskRunner


class _StatusRecordingTaskRunner(RecordingTaskRunner):
    """Records each id ``status`` is asked about, for tests that the backend was not consulted."""

    def __init__(self) -> None:
        super().__init__()
        self.status_queries: list[str] = []

    def status(self, celery_task_id: str) -> TaskStatus:
        self.status_queries.append(celery_task_id)
        return super().status(celery_task_id)


class _UnreachableStatusTaskRunner(RecordingTaskRunner):
    """A task backend that cannot be reached when asked about a task."""

    def status(self, celery_task_id: str) -> TaskStatus:
        raise ConnectionError("result backend down")


class _FailingRevokeTaskRunner(RecordingTaskRunner):
    """A task backend that cannot be reached when asked to revoke a task."""

    def revoke(self, celery_task_id: str) -> None:
        raise ConnectionError("Celery connection error")


class TestStartGsheetLoadTask:
    """Test starting Google Sheets loading tasks."""

    def test_start_gsheet_load_task_success_admin(self, uow, task_runner):
        """Test successful task start by admin user."""

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Create gsheet configuration
        gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
        )
        uow.assembly_gsheets.add(gsheet)

        # Create selection settings (selection fields moved from gsheet to SelectionSettings)
        sel_settings = SelectionSettings(
            assembly_id=assembly.id,
            check_same_address_cols=["address1", "postcode"],  # Required when check_same_address=True
            columns_to_keep=["first_name", "last_name", "age"],  # Required by Settings
        )
        assembly.selection_settings = sel_settings

        task_id = sortition.start_gsheet_load_task(uow, admin_user.id, assembly.id, task_runner=task_runner)

        # Verify task creation
        assert isinstance(task_id, uuid.UUID)

        # Verify SelectionRunRecord was created
        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.assembly_id == assembly.id
        assert record.task_id == task_id
        assert record.status == SelectionRunStatus.PENDING
        assert "Task submitted for Google Sheets loading" in record.log_messages
        assert "url" in record.settings_used
        assert record.settings_used["url"] == VALID_GSHEET_URL

        assert record.celery_task_id == str(task_id)

        # Verify the task was sent
        assert [t.name for t in task_runner.submitted] == ["load_gsheet"]
        sent = task_runner.submitted[0].kwargs
        assert sent["task_id"] == task_id
        assert isinstance(sent["data_source"], GSheetDataSource)
        assert sent["data_source"].feature_tab_name == gsheet.select_targets_tab
        assert sent["data_source"].people_tab_name == gsheet.select_registrants_tab
        assert task_runner.submitted[0].options == {"task_id": str(task_id)}

        assert uow.committed

    def test_start_gsheet_load_task_assembly_not_found(self, uow, task_runner):
        """Test error when assembly doesn't exist."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        non_existent_id = uuid.uuid4()

        with pytest.raises(AssemblyNotFoundError, match=f"Assembly {non_existent_id} not found"):
            sortition.start_gsheet_load_task(uow, admin_user.id, non_existent_id, task_runner=task_runner)

    def test_start_gsheet_load_task_no_gsheet_config(self, uow, task_runner):
        """Test error when assembly has no Google Sheets configuration."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)
        # No gsheet configuration added

        with pytest.raises(
            GoogleSheetConfigNotFoundError, match=f"No Google Sheets configuration found for assembly {assembly.id}"
        ):
            sortition.start_gsheet_load_task(uow, admin_user.id, assembly.id, task_runner=task_runner)

    def test_start_gsheet_load_task_insufficient_permissions(self, uow, task_runner):
        """Test error when user doesn't have management permissions."""
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
        )
        uow.assembly_gsheets.add(gsheet)

        sel_settings = SelectionSettings(
            assembly_id=assembly.id,
            check_same_address_cols=["address1", "postcode"],
            columns_to_keep=["first_name", "last_name", "age"],
        )
        assembly.selection_settings = sel_settings

        with pytest.raises(InsufficientPermissions):
            sortition.start_gsheet_load_task(uow, regular_user.id, assembly.id, task_runner=task_runner)


class TestGetSelectionRunStatus:
    """Test getting selection run status."""

    def test_get_selection_run_status_exists(self, uow, task_runner):
        """Test getting status for existing task."""

        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        record = SelectionRunRecord(
            assembly_id=assembly_id,
            task_id=task_id,
            task_type=SelectionTaskType.LOAD_GSHEET,
            status=SelectionRunStatus.RUNNING,
            log_messages=["Task started", "Loading data"],
        )
        uow.selection_run_records.add(record)

        result = sortition.get_selection_run_status(uow, task_id, task_runner=task_runner)
        run_record = result.run_record

        assert run_record is not None
        assert run_record.task_id == task_id
        assert run_record.assembly_id == assembly_id
        assert run_record.status == SelectionRunStatus.RUNNING
        assert len(run_record.log_messages) == 2

    def test_get_selection_run_status_without_celery_task_id_skips_celery(self, uow):
        """A record with no Celery id (task creation failed) must not ask the
        task runner about it - Celery's AsyncResult with an empty id raises
        when garbage-collected."""
        task_runner = _StatusRecordingTaskRunner()
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.LOAD_GSHEET,
            status=SelectionRunStatus.RUNNING,
        )
        assert record.celery_task_id == ""
        uow.selection_run_records.add(record)

        result = sortition.get_selection_run_status(uow, task_id, task_runner=task_runner)

        assert task_runner.status_queries == []
        assert result.run_record is not None

    def test_get_selection_run_status_not_found(self, uow, task_runner):
        """Test getting status for non-existent task."""

        non_existent_id = uuid.uuid4()
        result = sortition.get_selection_run_status(uow, non_existent_id, task_runner=task_runner)

        assert result.run_record is None

    def test_get_selection_run_status_returns_log_messages_while_running(self, uow, task_runner):
        """While the task is running (PROGRESS state in celery), the result must
        include log_messages from the DB record so the modal shows live updates."""
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            celery_task_id="celery-progress",
            log_messages=["Task submitted", "Loading features", "Loaded 5 features"],
        )
        uow.selection_run_records.add(record)

        task_runner.set_state("celery-progress", "PROGRESS")

        result = sortition.get_selection_run_status(uow, task_id, task_runner=task_runner)

        assert result.log_messages == [
            "Task submitted",
            "Loading features",
            "Loaded 5 features",
        ]

    def test_get_selection_run_status_returns_log_messages_while_pending(self, uow, task_runner):
        """While the task is still queued (PENDING in celery), the result must
        still include the initial submission log message from the DB record."""
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.PENDING,
            celery_task_id="celery-pending",
            log_messages=["Task submitted"],
        )
        uow.selection_run_records.add(record)

        # The runner reports PENDING for a task it has not been told about.
        result = sortition.get_selection_run_status(uow, task_id, task_runner=task_runner)

        assert result.log_messages == ["Task submitted"]

    def test_get_selection_run_status_returns_the_final_value_of_a_successful_task(self, uow, task_runner):
        """A task the backend reports SUCCESS gives the typed result built from its return value."""
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.COMPLETED,
            celery_task_id="celery-done",
            log_messages=["Done"],
        )
        uow.selection_run_records.add(record)
        run_report = RunReport()
        selected = [frozenset({"P1", "P2"})]
        task_runner.finish("celery-done", (True, selected, run_report))

        result = sortition.get_selection_run_status(uow, task_id, task_runner=task_runner)

        assert isinstance(result, sortition.SelectionRunResult)
        assert result.success is True
        assert result.selected_ids == selected


class TestGetSelectedRespondents:
    """The respondents a finished run selected, looked up from its stored IDs."""

    def _record(self, assembly_id: uuid.UUID, selected_ids: list[list[str]] | None) -> SelectionRunRecord:
        return SelectionRunRecord(
            assembly_id=assembly_id,
            task_id=uuid.uuid4(),
            task_type=SelectionTaskType.SELECT_FROM_DB,
            status=SelectionRunStatus.COMPLETED,
            selected_ids=selected_ids,
        )

    def test_returns_the_selected_respondents_ordered_by_external_id(self, uow, task_runner):
        assembly_id = uuid.uuid4()
        for ext_id in ("1", "2", "3"):
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id=ext_id))
        uow.respondents.add(Respondent(assembly_id=uuid.uuid4(), external_id="2"))

        selected = sortition.get_selected_respondents(uow, self._record(assembly_id, [["3", "1"]]))

        assert [r.external_id for r in selected] == ["1", "3"]
        assert all(r.assembly_id == assembly_id for r in selected)

    def test_includes_a_respondent_deleted_since_the_run(self, uow, task_runner):
        assembly_id = uuid.uuid4()
        uow.respondents.add(Respondent(assembly_id=assembly_id, external_id="1"))
        uow.respondents.add(
            Respondent(assembly_id=assembly_id, external_id="2", selection_status=RespondentStatus.DELETED)
        )

        selected = sortition.get_selected_respondents(uow, self._record(assembly_id, [["1", "2"]]))

        assert [r.external_id for r in selected] == ["1", "2"]

    def test_skips_ids_with_no_respondent_row(self, uow, task_runner):
        assembly_id = uuid.uuid4()
        uow.respondents.add(Respondent(assembly_id=assembly_id, external_id="1"))

        selected = sortition.get_selected_respondents(uow, self._record(assembly_id, [["1", "gone"]]))

        assert [r.external_id for r in selected] == ["1"]

    def test_run_without_a_panel_gives_nothing(self, uow, task_runner):
        assembly_id = uuid.uuid4()
        uow.respondents.add(Respondent(assembly_id=assembly_id, external_id="1"))

        assert sortition.get_selected_respondents(uow, self._record(assembly_id, None)) == []
        assert sortition.get_selected_respondents(uow, self._record(assembly_id, [])) == []

    def test_google_sheets_run_gives_nothing(self, uow, task_runner):
        """A Google Sheets run's IDs name spreadsheet rows, even when a respondent happens to share one."""
        assembly_id = uuid.uuid4()
        uow.respondents.add(Respondent(assembly_id=assembly_id, external_id="1"))
        record = self._record(assembly_id, [["1"]])
        record.task_type = SelectionTaskType.SELECT_GSHEET

        assert sortition.get_selected_respondents(uow, record) == []


class TestGetManageOldTabsStatus:
    def get_run_result(self, task_is_list: bool, success: bool | None) -> sortition.RunResult:
        if success is None:
            status = SelectionRunStatus.RUNNING
        elif success is True:
            status = SelectionRunStatus.COMPLETED
        else:
            status = SelectionRunStatus.FAILED
        return sortition.RunResult(
            run_record=SelectionRunRecord(
                assembly_id=uuid.uuid4(),
                task_id=uuid.uuid4(),
                task_type=SelectionTaskType.LIST_OLD_TABS if task_is_list else SelectionTaskType.DELETE_OLD_TABS,
                status=status,
                log_messages=[],
            ),
            run_report=RunReport(),
            log_messages=[],
            success=success,
        )

    def test_get_manage_old_tabs_status_for_error(self):
        run_result = self.get_run_result(task_is_list=True, success=False)
        status = sortition.get_manage_old_tabs_status(run_result)
        assert status.is_error

    def test_get_manage_old_tabs_status_for_list_running(self):
        run_result = self.get_run_result(task_is_list=True, success=None)
        status = sortition.get_manage_old_tabs_status(run_result)
        assert status.is_running
        assert status.state == ManageOldTabsState.LIST_RUNNING

    def test_get_manage_old_tabs_status_for_list_completed(self):
        run_result = self.get_run_result(task_is_list=True, success=True)
        status = sortition.get_manage_old_tabs_status(run_result)
        assert status.is_completed
        assert status.is_list_completed

    def test_get_manage_old_tabs_status_for_delete_running(self):
        run_result = self.get_run_result(task_is_list=False, success=None)
        status = sortition.get_manage_old_tabs_status(run_result)
        assert status.is_running
        assert status.state == ManageOldTabsState.DELETE_RUNNING

    def test_get_manage_old_tabs_status_for_delete_completed(self):
        run_result = self.get_run_result(task_is_list=False, success=True)
        status = sortition.get_manage_old_tabs_status(run_result)
        assert status.is_completed
        assert not status.is_list_completed


class TestGetLatestRunForAssembly:
    """Test getting latest run for assembly."""

    def test_get_latest_run_for_assembly_exists(self, uow, task_runner):
        """Test getting latest run when runs exist."""

        assembly_id = uuid.uuid4()

        # Create multiple records for the same assembly
        old_record = SelectionRunRecord(
            assembly_id=assembly_id,
            task_id=uuid.uuid4(),
            task_type=SelectionTaskType.LOAD_GSHEET,
            status=SelectionRunStatus.COMPLETED,
            log_messages=["Old task"],
        )
        # Manually set created_at to ensure ordering
        old_record.created_at = old_record.created_at.replace(year=2020)
        uow.selection_run_records.add(old_record)

        new_record = SelectionRunRecord(
            assembly_id=assembly_id,
            task_id=uuid.uuid4(),
            task_type=SelectionTaskType.LOAD_GSHEET,
            status=SelectionRunStatus.RUNNING,
            log_messages=["New task"],
        )
        uow.selection_run_records.add(new_record)

        result = sortition.get_latest_run_for_assembly(uow, assembly_id)

        assert result is not None
        assert result.task_id == new_record.task_id
        assert result.status == SelectionRunStatus.RUNNING

    def test_get_latest_run_for_assembly_not_found(self, uow, task_runner):
        """Test getting latest run when no runs exist."""

        non_existent_assembly_id = uuid.uuid4()
        result = sortition.get_latest_run_for_assembly(uow, non_existent_assembly_id)

        assert result is None


class TestCheckAndUpdateTaskHealth:
    """Test checking and updating task health status."""

    def test_ignores_completed_tasks(self, uow, task_runner):
        """Test that completed tasks are not checked or modified."""

        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.COMPLETED,
            celery_task_id="celery-123",
            log_messages=["Task completed"],
        )
        uow.selection_run_records.add(record)

        # Should not check Celery or modify the record
        sortition.check_and_update_task_health(uow, task_id, task_runner=task_runner)

        # Record should be unchanged
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.COMPLETED
        assert len(updated_record.log_messages) == 1

    def test_ignores_failed_tasks(self, uow, task_runner):
        """Test that failed tasks are not checked or modified."""

        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.FAILED,
            celery_task_id="celery-123",
            log_messages=["Task failed"],
            error_message="Original error",
        )
        uow.selection_run_records.add(record)

        # Should not check Celery or modify the record
        sortition.check_and_update_task_health(uow, task_id, task_runner=task_runner)

        # Record should be unchanged
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.FAILED
        assert updated_record.error_message == "Original error"

    def test_marks_running_task_as_failed_when_celery_says_failure(self, uow, task_runner):
        """Test that RUNNING task is marked FAILED when Celery reports FAILURE state."""

        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            celery_task_id="celery-123",
            log_messages=["Task started"],
        )
        uow.selection_run_records.add(record)

        task_runner.fail("celery-123", error="Exception: Task crashed")

        sortition.check_and_update_task_health(uow, task_id, task_runner=task_runner)

        # Record should be marked as FAILED
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.FAILED
        assert "stopped unexpectedly" in updated_record.error_message
        assert "contact the administrators" in updated_record.error_message
        assert updated_record.completed_at is not None
        assert any("ERROR" in msg for msg in updated_record.log_messages)

    def test_marks_running_task_as_failed_when_celery_says_revoked(self, uow, task_runner):
        """Test that RUNNING task is marked FAILED when Celery reports REVOKED state."""

        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            celery_task_id="celery-456",
            log_messages=["Task started"],
        )
        uow.selection_run_records.add(record)

        task_runner.fail("celery-456", state="REVOKED")

        sortition.check_and_update_task_health(uow, task_id, task_runner=task_runner)

        # Record should be marked as FAILED
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.FAILED
        assert "stopped unexpectedly" in updated_record.error_message

    def test_marks_running_task_as_failed_when_celery_forgot_it(self, uow, task_runner):
        """Test that RUNNING task is marked FAILED when Celery has no record (state=PENDING)."""

        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            celery_task_id="celery-789",
            log_messages=["Task started"],
        )
        uow.selection_run_records.add(record)

        # The runner reports PENDING for an id it has not been told about, which
        # is what Celery says once it has forgotten a task
        sortition.check_and_update_task_health(uow, task_id, task_runner=task_runner)

        # Record should be marked as FAILED
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.FAILED
        assert "stopped unexpectedly" in updated_record.error_message

    def test_leaves_running_task_alone_when_celery_says_started(self, uow, task_runner):
        """Test that RUNNING task is left alone when Celery reports STARTED state."""

        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            celery_task_id="celery-active",
            log_messages=["Task started"],
        )
        uow.selection_run_records.add(record)

        # The backend reports STARTED (task is running fine)
        task_runner.set_state("celery-active", "STARTED")

        sortition.check_and_update_task_health(uow, task_id, task_runner=task_runner)

        # Record should be unchanged
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.RUNNING
        assert len(updated_record.log_messages) == 1

    def test_leaves_running_task_alone_when_celery_says_success(self, uow, task_runner):
        """Test that RUNNING task is left alone when Celery reports SUCCESS state."""

        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            celery_task_id="celery-done",
            log_messages=["Task started"],
        )
        uow.selection_run_records.add(record)

        # The backend reports SUCCESS
        task_runner.set_state("celery-done", "SUCCESS")

        sortition.check_and_update_task_health(uow, task_id, task_runner=task_runner)

        # Record should be unchanged - let normal polling handle SUCCESS
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.RUNNING
        assert len(updated_record.log_messages) == 1

    def test_marks_pending_task_as_failed_when_celery_says_failure(self, uow, task_runner):
        """Test that PENDING task is marked FAILED when Celery reports FAILURE state."""

        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.PENDING,
            celery_task_id="celery-pending-failed",
            log_messages=["Task submitted"],
        )
        uow.selection_run_records.add(record)

        task_runner.fail("celery-pending-failed", error="Exception: Failed to start")

        sortition.check_and_update_task_health(uow, task_id, task_runner=task_runner)

        # Record should be marked as FAILED
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.FAILED
        assert "failed to start" in updated_record.error_message.lower()

    def test_marks_task_as_failed_when_timeout_exceeded(self, uow, task_runner):
        """Test that task is marked FAILED when it exceeds the timeout."""

        task_id = uuid.uuid4()
        # Create record with old created_at (25 hours ago)
        old_time = datetime.now(UTC) - timedelta(hours=25)
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            celery_task_id="celery-timeout",
            log_messages=["Task started"],
        )
        record.created_at = old_time
        uow.selection_run_records.add(record)

        # Check with 24 hour timeout - should fail
        sortition.check_and_update_task_health(uow, task_id, timeout_hours=24, task_runner=task_runner)

        # Record should be marked as FAILED due to timeout
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.FAILED
        assert "timeout" in updated_record.error_message.lower()

    def test_marks_pending_task_as_failed_after_the_pending_timeout(self, uow, task_runner):
        """A record still PENDING past the pending timeout was never picked up, so it is FAILED."""
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_FROM_DB,
            status=SelectionRunStatus.PENDING,
            celery_task_id="celery-never-started",
            log_messages=["Task submitted"],
        )
        record.created_at = datetime.now(UTC) - timedelta(minutes=61)
        uow.selection_run_records.add(record)

        task_runner.set_state("celery-never-started", "PENDING")
        sortition.check_and_update_task_health(uow, task_id, pending_timeout_minutes=60, task_runner=task_runner)

        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.FAILED
        assert "did not start" in updated_record.error_message

    def test_pending_task_within_the_pending_timeout_is_left_alone(self, uow, task_runner):
        """A record that has only just been queued is still waiting for a worker."""
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_FROM_DB,
            status=SelectionRunStatus.PENDING,
            celery_task_id="celery-queued",
            log_messages=["Task submitted"],
        )
        record.created_at = datetime.now(UTC) - timedelta(minutes=59)
        uow.selection_run_records.add(record)

        task_runner.set_state("celery-queued", "PENDING")
        sortition.check_and_update_task_health(uow, task_id, pending_timeout_minutes=60, task_runner=task_runner)

        assert uow.selection_run_records.get_by_task_id(task_id).status == SelectionRunStatus.PENDING

    def test_running_task_is_not_subject_to_the_pending_timeout(self, uow, task_runner):
        """The pending timeout is about never starting; a RUNNING record of the same age is fine."""
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_FROM_DB,
            status=SelectionRunStatus.RUNNING,
            celery_task_id="celery-running",
            log_messages=["Task started"],
        )
        record.created_at = datetime.now(UTC) - timedelta(minutes=61)
        uow.selection_run_records.add(record)

        task_runner.set_state("celery-running", "STARTED")
        sortition.check_and_update_task_health(uow, task_id, pending_timeout_minutes=60, task_runner=task_runner)

        assert uow.selection_run_records.get_by_task_id(task_id).status == SelectionRunStatus.RUNNING

    def test_does_not_fail_task_within_timeout(self, uow, task_runner):
        """Test that task is not marked failed when within timeout period."""

        task_id = uuid.uuid4()
        # Create record with recent created_at (1 hour ago)
        recent_time = datetime.now(UTC) - timedelta(hours=1)
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            celery_task_id="celery-recent",
            log_messages=["Task started"],
        )
        record.created_at = recent_time
        uow.selection_run_records.add(record)

        # The backend reports STARTED (running normally)
        task_runner.set_state("celery-recent", "STARTED")

        # Check with 24 hour timeout - should not fail
        sortition.check_and_update_task_health(uow, task_id, timeout_hours=24, task_runner=task_runner)

        # Record should still be RUNNING
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.RUNNING

    def test_does_nothing_when_task_not_found(self, uow, task_runner):
        """Test that function handles gracefully when task doesn't exist."""

        non_existent_id = uuid.uuid4()

        # Should not raise an exception
        sortition.check_and_update_task_health(uow, non_existent_id, task_runner=task_runner)

    def test_handles_missing_celery_task_id_gracefully(self, uow):
        """Test that function handles gracefully when celery_task_id is None or empty."""
        task_runner = _StatusRecordingTaskRunner()

        task_id = uuid.uuid4()
        # Create record without celery_task_id (None)
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            celery_task_id=None,  # Missing Celery task ID
            log_messages=["Task started"],
        )
        uow.selection_run_records.add(record)

        # Should not raise an exception, nor ask the task runner
        sortition.check_and_update_task_health(uow, task_id, task_runner=task_runner)
        assert task_runner.status_queries == []

        # Record should still be RUNNING (can't check health without celery_task_id)
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.RUNNING

    def test_handles_empty_celery_task_id_gracefully(self, uow):
        """Test that function handles gracefully when celery_task_id is empty string."""
        task_runner = _StatusRecordingTaskRunner()

        task_id = uuid.uuid4()
        # Create record with empty celery_task_id
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            celery_task_id="",  # Empty Celery task ID
            log_messages=["Task started"],
        )
        uow.selection_run_records.add(record)

        # Should not raise an exception, nor ask the task runner
        sortition.check_and_update_task_health(uow, task_id, task_runner=task_runner)
        assert task_runner.status_queries == []

        # Record should still be RUNNING (can't check health without celery_task_id)
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.RUNNING

    def test_leaves_task_alone_when_the_backend_cannot_be_reached(self, uow):
        """If asking the backend raises, the health of the task is unknown, so it is not failed."""
        task_runner = _UnreachableStatusTaskRunner()
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            celery_task_id="celery-unreachable",
            log_messages=["Task started"],
        )
        uow.selection_run_records.add(record)

        sortition.check_and_update_task_health(uow, task_id, task_runner=task_runner)

        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.RUNNING
        assert len(updated_record.log_messages) == 1


class TestCancelTask:
    """Test cancelling running tasks."""

    def test_cancel_pending_task_success(self, uow, task_runner):
        """Test successfully cancelling a PENDING task."""

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Create a PENDING task
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.PENDING,
            celery_task_id="celery-123",
            log_messages=["Task submitted"],
        )
        uow.selection_run_records.add(record)

        # Cancel the task
        sortition.cancel_task(uow, admin_user.id, assembly.id, task_id, task_runner=task_runner)
        assert task_runner.revoked == ["celery-123"]

        # Verify task is CANCELLED
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.CANCELLED
        assert updated_record.completed_at is not None
        assert "admin" in updated_record.error_message  # display_name returns email prefix
        assert "cancelled" in updated_record.error_message.lower()
        assert "cancelled" in updated_record.log_messages[-1].lower()

    def test_cancel_running_task_success(self, uow, task_runner):
        """Test successfully cancelling a RUNNING task."""

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Create a RUNNING task
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            celery_task_id="celery-456",
            log_messages=["Task started", "Processing..."],
        )
        uow.selection_run_records.add(record)

        # Cancel the task
        sortition.cancel_task(uow, admin_user.id, assembly.id, task_id, task_runner=task_runner)
        assert task_runner.revoked == ["celery-456"]

        # Verify task is CANCELLED
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.CANCELLED
        assert updated_record.completed_at is not None

    def test_cancel_already_completed_task_fails(self, uow, task_runner):
        """Test that cancelling a COMPLETED task raises an error."""

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Create a COMPLETED task
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.COMPLETED,
            celery_task_id="celery-789",
            log_messages=["Task completed"],
            completed_at=datetime.now(UTC),
        )
        uow.selection_run_records.add(record)

        # Attempt to cancel should fail
        with pytest.raises(InvalidSelection, match="Cannot cancel task"):
            sortition.cancel_task(uow, admin_user.id, assembly.id, task_id, task_runner=task_runner)

    def test_cancel_already_failed_task_fails(self, uow, task_runner):
        """Test that cancelling a FAILED task raises an error."""

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Create a FAILED task
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.FAILED,
            celery_task_id="celery-999",
            log_messages=["Task failed"],
            error_message="Some error",
            completed_at=datetime.now(UTC),
        )
        uow.selection_run_records.add(record)

        # Attempt to cancel should fail
        with pytest.raises(InvalidSelection, match="Cannot cancel task"):
            sortition.cancel_task(uow, admin_user.id, assembly.id, task_id, task_runner=task_runner)

    def test_cancel_already_cancelled_task_fails(self, uow, task_runner):
        """Test that cancelling a CANCELLED task raises an error."""

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Create a CANCELLED task
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.CANCELLED,
            celery_task_id="celery-111",
            log_messages=["Task cancelled"],
            error_message="Task cancelled by user",
            completed_at=datetime.now(UTC),
        )
        uow.selection_run_records.add(record)

        # Attempt to cancel should fail
        with pytest.raises(InvalidSelection, match="Cannot cancel task"):
            sortition.cancel_task(uow, admin_user.id, assembly.id, task_id, task_runner=task_runner)

    def test_cancel_nonexistent_task_fails(self, uow, task_runner):
        """Test that cancelling a non-existent task raises an error."""

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Attempt to cancel non-existent task
        with pytest.raises(InvalidSelection, match="Task not found"):
            sortition.cancel_task(uow, admin_user.id, assembly.id, uuid.uuid4(), task_runner=task_runner)

    def test_cancel_task_celery_revoke_fails_still_marks_cancelled(self, uow):
        """Test that task is marked CANCELLED even if Celery revoke fails."""
        task_runner = _FailingRevokeTaskRunner()

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Create a RUNNING task
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            celery_task_id="celery-error",
            log_messages=["Task started"],
        )
        uow.selection_run_records.add(record)

        # Cancel the task with the revoke failing
        sortition.cancel_task(uow, admin_user.id, assembly.id, task_id, task_runner=task_runner)

        # Task should still be CANCELLED despite Celery error
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.CANCELLED
        assert updated_record.completed_at is not None

    def test_has_finished_includes_cancelled(self):
        """Test that has_finished property includes CANCELLED status."""
        task_id = uuid.uuid4()
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.CANCELLED,
            celery_task_id="celery-123",
        )

        assert record.has_finished is True
        assert record.is_cancelled is True


class TestStartGsheetSelectTaskTimeLimits:
    """Test that start_gsheet_select_task passes its time limits through to the task's options."""

    def _make_uow_with_select_setup(self, uow) -> tuple[FakeUnitOfWork, User, Assembly]:
        admin = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin)

        assembly = Assembly(title="Test Assembly", number_to_select=10)
        uow.assemblies.add(assembly)

        gsheet = AssemblyGSheet(assembly_id=assembly.id, url=VALID_GSHEET_URL)
        uow.assembly_gsheets.add(gsheet)

        sel_settings = SelectionSettings(
            assembly_id=assembly.id,
            check_same_address_cols=["address1", "postcode"],
            columns_to_keep=["first_name", "last_name", "age"],
        )
        assembly.selection_settings = sel_settings
        return uow, admin, assembly

    def test_default_call_sends_no_time_limits(self, uow, task_runner):
        uow, admin, assembly = self._make_uow_with_select_setup(uow)

        task_id = sortition.start_gsheet_select_task(uow, admin.id, assembly.id, task_runner=task_runner)

        assert [t.name for t in task_runner.submitted] == ["run_select"]
        submitted = task_runner.submitted[0]
        assert set(submitted.kwargs.keys()) == {
            "task_id",
            "data_source",
            "number_people_wanted",
            "settings",
            "test_selection",
            "gen_rem_tab",
            "for_replacements",
        }
        assert submitted.kwargs["for_replacements"] is False
        # No time limits should have been passed
        assert submitted.options == {"task_id": str(task_id)}

    def test_sends_time_limits_as_task_options(self, uow, task_runner):
        uow, admin, assembly = self._make_uow_with_select_setup(uow)

        task_id = sortition.start_gsheet_select_task(
            uow,
            admin.id,
            assembly.id,
            task_runner=task_runner,
            time_limit=5,
            soft_time_limit=4,
        )

        assert [t.name for t in task_runner.submitted] == ["run_select"]
        submitted = task_runner.submitted[0]
        assert submitted.options == {"task_id": str(task_id), "time_limit": 5, "soft_time_limit": 4}
        assert "time_limit" not in submitted.kwargs
        assert "soft_time_limit" not in submitted.kwargs


class TestSortitionErrorHandling:
    """Test that sortition-algorithms library errors are properly converted to service layer exceptions."""

    def test_start_gsheet_load_task_invalid_settings_raises_invalid_selection(self, uow, task_runner):
        """Test that ConfigurationError from to_settings() is converted to InvalidSelection."""

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Create gsheet configuration
        gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
        )
        uow.assembly_gsheets.add(gsheet)

        # Create selection settings with invalid config:
        # check_same_address=True but no check_same_address_cols will cause ConfigurationError
        sel_settings = SelectionSettings(
            assembly_id=assembly.id,
            check_same_address=True,
            check_same_address_cols=[],  # Empty - will cause ConfigurationError
            columns_to_keep=["first_name", "last_name"],
        )
        assembly.selection_settings = sel_settings

        # Should raise InvalidSelection, not ConfigurationError
        with pytest.raises(InvalidSelection, match="check_same_address is TRUE but there are no columns"):
            sortition.start_gsheet_load_task(uow, admin_user.id, assembly.id, task_runner=task_runner)

    def test_start_gsheet_select_task_invalid_settings_raises_invalid_selection(self, uow, task_runner):
        """Test that ConfigurationError from to_settings() is converted to InvalidSelection in select task."""

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly with valid number_to_select
        assembly = Assembly(title="Test Assembly", number_to_select=10)
        uow.assemblies.add(assembly)

        # Create gsheet configuration
        gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
        )
        uow.assembly_gsheets.add(gsheet)

        # Create selection settings with invalid config
        sel_settings = SelectionSettings(
            assembly_id=assembly.id,
            check_same_address=True,
            check_same_address_cols=[],  # Empty - will cause ConfigurationError
            columns_to_keep=["first_name", "last_name"],
        )
        assembly.selection_settings = sel_settings

        # Should raise InvalidSelection, not ConfigurationError
        with pytest.raises(InvalidSelection, match="check_same_address is TRUE but there are no columns"):
            sortition.start_gsheet_select_task(uow, admin_user.id, assembly.id, task_runner=task_runner)

    def test_start_gsheet_replace_load_task_invalid_settings_raises_invalid_selection(self, uow, task_runner):
        """Test that ConfigurationError from to_settings() is converted to InvalidSelection in replace load."""

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Create gsheet configuration
        gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
        )
        uow.assembly_gsheets.add(gsheet)

        # Create selection settings with invalid config
        sel_settings = SelectionSettings(
            assembly_id=assembly.id,
            check_same_address=True,
            check_same_address_cols=[],  # Empty - will cause ConfigurationError
            columns_to_keep=["first_name", "last_name"],
        )
        assembly.selection_settings = sel_settings

        # Should raise InvalidSelection, not ConfigurationError
        with pytest.raises(InvalidSelection, match="check_same_address is TRUE but there are no columns"):
            sortition.start_gsheet_replace_load_task(uow, admin_user.id, assembly.id, task_runner=task_runner)

    def test_start_gsheet_replace_task_invalid_settings_raises_invalid_selection(self, uow, task_runner):
        """Test that ConfigurationError from to_settings() is converted to InvalidSelection in replace task."""

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Create gsheet configuration
        gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
        )
        uow.assembly_gsheets.add(gsheet)

        # Create selection settings with invalid config
        sel_settings = SelectionSettings(
            assembly_id=assembly.id,
            check_same_address=True,
            check_same_address_cols=[],  # Empty - will cause ConfigurationError
            columns_to_keep=["first_name", "last_name"],
        )
        assembly.selection_settings = sel_settings

        # Should raise InvalidSelection, not ConfigurationError
        with pytest.raises(InvalidSelection, match="check_same_address is TRUE but there are no columns"):
            sortition.start_gsheet_replace_task(
                uow, admin_user.id, assembly.id, number_to_select=5, task_runner=task_runner
            )


class TestStartDbSelectTask:
    """Test starting database-based selection tasks."""

    def test_start_db_select_task_success(self, uow, task_runner):
        """Test successful task start by admin user."""

        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        assembly = Assembly(title="Test Assembly", number_to_select=2)
        assembly.csv = AssemblyCSV(assembly_id=assembly.id)
        assembly.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
        uow.assemblies.add(assembly)

        task_id = sortition.start_db_select_task(uow, admin_user.id, assembly.id, task_runner=task_runner)

        assert isinstance(task_id, uuid.UUID)

        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.assembly_id == assembly.id
        assert record.task_id == task_id
        assert record.status == SelectionRunStatus.PENDING
        assert record.task_type == SelectionTaskType.SELECT_FROM_DB
        assert "database selection" in record.log_messages[0]

        assert record.celery_task_id == str(task_id)

        assert [t.name for t in task_runner.submitted] == ["run_select_from_db"]
        call_kwargs = task_runner.submitted[0].kwargs
        assert call_kwargs["task_id"] == task_id
        assert call_kwargs["assembly_id"] == assembly.id
        assert call_kwargs["number_people_wanted"] == 2

        assert uow.committed

    def test_start_db_select_task_zero_number_to_select_raises(self, uow, task_runner):
        """Test that InvalidSelection is raised when number_to_select is zero."""

        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        assembly = Assembly(title="Test Assembly", number_to_select=0)
        uow.assemblies.add(assembly)

        with pytest.raises(InvalidSelection):
            sortition.start_db_select_task(uow, admin_user.id, assembly.id, task_runner=task_runner)

    def test_start_db_test_select_task_uses_correct_task_type(self, uow, task_runner):
        """Test that test selection uses TEST_SELECT_FROM_DB task type."""

        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        assembly = Assembly(title="Test Assembly", number_to_select=2)
        assembly.csv = AssemblyCSV(assembly_id=assembly.id)
        assembly.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
        uow.assemblies.add(assembly)

        task_id = sortition.start_db_select_task(
            uow, admin_user.id, assembly.id, test_selection=True, task_runner=task_runner
        )

        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.task_type == SelectionTaskType.TEST_SELECT_FROM_DB
        assert "TEST" in record.log_messages[0]

        call_kwargs = task_runner.submitted[0].kwargs
        assert call_kwargs["test_selection"] is True

    def test_start_db_select_task_snapshots_targets(self, uow, task_runner):
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        assembly = Assembly(title="Test Assembly", number_to_select=2)
        assembly.csv = AssemblyCSV(assembly_id=assembly.id)
        assembly.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
        uow.assemblies.add(assembly)
        gender = TargetCategory(assembly_id=assembly.id, name="Gender", comment="men/women", sort_order=1)
        gender.add_value(TargetValue(value="Man", min=1, max=1, percentage_target=50.0))
        gender.add_value(TargetValue(value="Woman", min=1, max=1, percentage_target=50.0))
        uow.target_categories.add(gender)

        task_id = sortition.start_db_select_task(uow, admin_user.id, assembly.id, task_runner=task_runner)

        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.targets_used == [
            {
                "name": "Gender",
                "sort_order": 1,
                "comment": "men/women",
                "source_url": "",
                "values": [
                    {
                        "value": "Man",
                        "min": 1,
                        "max": 1,
                        "min_flex": 0,
                        "max_flex": -1,
                        "percentage_target": 50.0,
                        "comment": "",
                        "minmax_manual": False,
                    },
                    {
                        "value": "Woman",
                        "min": 1,
                        "max": 1,
                        "min_flex": 0,
                        "max_flex": -1,
                        "percentage_target": 50.0,
                        "comment": "",
                        "minmax_manual": False,
                    },
                ],
            },
        ]

    def test_start_db_select_task_ignores_stored_id_column(self, uow, task_runner):
        """A leftover gsheet id_column reaches neither the worker nor the record.

        The database data source always keys people by DB_ID_COLUMN, and the
        stored settings snapshot records what the run used, so both have to
        carry the adapter's column name.
        """
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        assembly = Assembly(title="Test Assembly", number_to_select=2)
        assembly.csv = AssemblyCSV(assembly_id=assembly.id)
        assembly.selection_settings = SelectionSettings(
            assembly_id=assembly.id,
            id_column="nationbuilder_id",
            check_same_address=False,
        )
        uow.assemblies.add(assembly)

        task_id = sortition.start_db_select_task(uow, admin_user.id, assembly.id, task_runner=task_runner)

        assert task_runner.submitted[0].kwargs["settings"].id_column == DB_ID_COLUMN

        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.settings_used["id_column"] == DB_ID_COLUMN

    def test_start_db_select_task_assembly_not_found_raises(self, uow, task_runner):
        """Test that AssemblyNotFoundError is raised for non-existent assembly."""

        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        non_existent_id = uuid.uuid4()

        with pytest.raises(AssemblyNotFoundError, match=f"Assembly {non_existent_id} not found"):
            sortition.start_db_select_task(uow, admin_user.id, non_existent_id, task_runner=task_runner)


class TestStartDbReplaceTask:
    """start_db_replace_task: the record it writes and what it refuses."""

    def _setup(self, uow):
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)
        assembly = Assembly(title="Test Assembly", number_to_select=10)
        assembly.csv = AssemblyCSV(assembly_id=assembly.id)
        assembly.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
        uow.assemblies.add(assembly)
        snapshot = [
            {
                "name": "Gender",
                "sort_order": 0,
                "comment": "",
                "source_url": "",
                "values": [
                    {"value": "Male", "min": 2, "max": 3, "overall_min": 5, "overall_max": 6, "held": 3},
                ],
            }
        ]
        info = {"number_to_select_overall": 10, "held_total": 6, "calculated_number": 4, "number_to_select_used": 4}
        return admin_user, assembly, snapshot, info

    def test_creates_record_and_dispatches_task_with_snapshot(self, uow, task_runner):
        admin_user, assembly, snapshot, info = self._setup(uow)

        task_id = sortition.start_db_replace_task(
            uow, admin_user.id, assembly.id, 4, snapshot, info, task_runner=task_runner
        )

        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.task_type == SelectionTaskType.SELECT_REPLACEMENT_FROM_DB
        assert record.status == SelectionRunStatus.PENDING
        assert record.targets_used == snapshot
        assert record.settings_used["replacement"] == info
        assert record.settings_used["id_column"] == DB_ID_COLUMN
        assert record.celery_task_id == str(task_id)
        assert record.user_id == admin_user.id

        assert [t.name for t in task_runner.submitted] == ["run_select_from_db"]
        kwargs = task_runner.submitted[0].kwargs
        assert kwargs["task_id"] == task_id
        assert kwargs["number_people_wanted"] == 4
        assert kwargs["targets_snapshot"] == snapshot
        assert kwargs["test_selection"] is False
        assert uow.committed

    def test_refuses_fewer_than_one_replacement(self, uow, task_runner):
        admin_user, assembly, snapshot, info = self._setup(uow)
        with pytest.raises(InvalidSelection):
            sortition.start_db_replace_task(uow, admin_user.id, assembly.id, 0, snapshot, info, task_runner=task_runner)

    def test_refuses_while_a_selection_is_running(self, uow, task_runner):
        admin_user, assembly, snapshot, info = self._setup(uow)
        uow.selection_run_records.add(
            SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=uuid.uuid4(),
                task_type=SelectionTaskType.SELECT_FROM_DB,
                status=SelectionRunStatus.RUNNING,
            )
        )
        with pytest.raises(InvalidSelection):
            sortition.start_db_replace_task(uow, admin_user.id, assembly.id, 4, snapshot, info, task_runner=task_runner)

    def test_requires_assembly_management(self, uow, task_runner):
        _, assembly, snapshot, info = self._setup(uow)
        viewer = User(email="viewer@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(viewer)
        with pytest.raises(InsufficientPermissions):
            sortition.start_db_replace_task(uow, viewer.id, assembly.id, 4, snapshot, info, task_runner=task_runner)

    def test_assembly_not_found(self, uow, task_runner):
        admin_user, _, snapshot, info = self._setup(uow)
        with pytest.raises(AssemblyNotFoundError):
            sortition.start_db_replace_task(
                uow, admin_user.id, uuid.uuid4(), 4, snapshot, info, task_runner=task_runner
            )


class TestActiveInitialSelectionIncludesDbReplacement:
    def test_running_db_replacement_counts_as_active(self, uow, task_runner):
        """A replacement run writes the same rows as an initial run, so the cards wait for it."""
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)
        task_id = uuid.uuid4()
        uow.selection_run_records.add(
            SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                task_type=SelectionTaskType.SELECT_REPLACEMENT_FROM_DB,
                status=SelectionRunStatus.RUNNING,
            )
        )
        assert sortition.get_active_initial_selection_run_id(uow, assembly.id) == task_id

    def test_reset_record_is_never_active(self, uow, task_runner):
        """A reset is written already complete, so it never swaps the cards for a running-run button."""
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)
        uow.selection_run_records.add(
            SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=uuid.uuid4(),
                task_type=SelectionTaskType.RESET_TO_POOL,
                status=SelectionRunStatus.COMPLETED,
            )
        )
        assert sortition.get_active_initial_selection_run_id(uow, assembly.id) is None


class TestProcessFinalResult:
    @pytest.mark.parametrize(
        "task_type",
        [
            SelectionTaskType.SELECT_FROM_DB,
            SelectionTaskType.TEST_SELECT_FROM_DB,
            SelectionTaskType.SELECT_REPLACEMENT_FROM_DB,
        ],
    )
    def test_database_selection_tasks_give_a_selection_result(self, task_type):
        record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            status=SelectionRunStatus.COMPLETED,
            task_type=task_type,
            log_messages=["Done"],
        )
        run_report = RunReport()
        selected = [frozenset({"F3"})]

        result = sortition._process_final_result(
            TaskStatus(state="SUCCESS", value=(True, selected, run_report)), record
        )

        assert isinstance(result, sortition.SelectionRunResult)
        assert result.success is True
        assert result.selected_ids == selected
        assert result.run_report is run_report
        assert result.log_messages == ["Done"]


class TestStartGsheetReplaceLoadTask:
    """Starting the check of a spreadsheet's replacement tabs."""

    def _admin_and_assembly(self, uow) -> tuple[User, Assembly]:
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)
        assembly.selection_settings = SelectionSettings(
            assembly_id=assembly.id,
            check_same_address_cols=["address1", "postcode"],
            columns_to_keep=["first_name", "last_name", "age"],
        )
        return admin_user, assembly

    def test_it_records_the_run_and_hands_the_replacement_tabs_to_the_task(self, uow, task_runner):
        admin_user, assembly = self._admin_and_assembly(uow)
        gsheet = AssemblyGSheet(assembly_id=assembly.id, url=VALID_GSHEET_URL)
        uow.assembly_gsheets.add(gsheet)

        task_id = sortition.start_gsheet_replace_load_task(uow, admin_user.id, assembly.id, task_runner=task_runner)

        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.task_type == SelectionTaskType.LOAD_REPLACEMENT_GSHEET
        assert record.status == SelectionRunStatus.PENDING
        assert record.celery_task_id == str(task_id)
        assert record.user_id == admin_user.id
        assert uow.committed

        assert [t.name for t in task_runner.submitted] == ["load_gsheet"]
        data_source = task_runner.submitted[0].kwargs["data_source"]
        assert task_runner.submitted[0].kwargs["task_id"] == task_id
        assert isinstance(data_source, GSheetDataSource)
        assert data_source.feature_tab_name == gsheet.replace_targets_tab
        assert data_source.people_tab_name == gsheet.replace_registrants_tab

    def test_a_project_with_no_spreadsheet_is_refused(self, uow, task_runner):
        admin_user, assembly = self._admin_and_assembly(uow)

        with pytest.raises(GoogleSheetConfigNotFoundError, match="No Google Sheets configuration found"):
            sortition.start_gsheet_replace_load_task(uow, admin_user.id, assembly.id, task_runner=task_runner)

        assert list(uow.selection_run_records.get_by_assembly_id(assembly.id)) == []


DISPATCH_FAILED_MESSAGE = "The task could not be started. Please try again."
REPLACE_SNAPSHOT = [
    {
        "name": "Gender",
        "sort_order": 0,
        "comment": "",
        "source_url": "",
        "values": [{"value": "Male", "min": 2, "max": 3, "overall_min": 5, "overall_max": 6, "held": 3}],
    }
]
REPLACE_INFO = {"number_to_select_overall": 10, "held_total": 6, "calculated_number": 4, "number_to_select_used": 4}

# Every start_* service, called with an admin and an assembly from _dispatch_setup.
ALL_STARTS = [
    pytest.param(
        lambda uow, admin, assembly, runner: sortition.start_gsheet_load_task(
            uow, admin.id, assembly.id, task_runner=runner
        ),
        id="gsheet_load",
    ),
    pytest.param(
        lambda uow, admin, assembly, runner: sortition.start_gsheet_select_task(
            uow, admin.id, assembly.id, task_runner=runner
        ),
        id="gsheet_select",
    ),
    pytest.param(
        lambda uow, admin, assembly, runner: sortition.start_gsheet_replace_load_task(
            uow, admin.id, assembly.id, task_runner=runner
        ),
        id="gsheet_replace_load",
    ),
    pytest.param(
        lambda uow, admin, assembly, runner: sortition.start_gsheet_replace_task(
            uow, admin.id, assembly.id, 3, task_runner=runner
        ),
        id="gsheet_replace",
    ),
    pytest.param(
        lambda uow, admin, assembly, runner: sortition.start_gsheet_manage_tabs_task(
            uow, admin.id, assembly.id, False, task_runner=runner
        ),
        id="gsheet_manage_tabs",
    ),
    pytest.param(
        lambda uow, admin, assembly, runner: sortition.start_db_select_task(
            uow, admin.id, assembly.id, task_runner=runner
        ),
        id="db_select",
    ),
    pytest.param(
        lambda uow, admin, assembly, runner: sortition.start_db_replace_task(
            uow, admin.id, assembly.id, 4, REPLACE_SNAPSHOT, REPLACE_INFO, task_runner=runner
        ),
        id="db_replace",
    ),
]


def _dispatch_setup(uow: FakeUnitOfWork) -> tuple[User, Assembly, AssemblyGSheet]:
    """An admin and an assembly configured for both Google Sheets and database selection."""
    admin = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(admin)
    assembly = Assembly(title="Test Assembly", number_to_select=10)
    assembly.csv = AssemblyCSV(assembly_id=assembly.id)
    assembly.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
    uow.assemblies.add(assembly)
    gsheet = AssemblyGSheet(assembly_id=assembly.id, url=VALID_GSHEET_URL)
    uow.assembly_gsheets.add(gsheet)
    return admin, assembly, gsheet


class _Unpicklable:
    """Holds a lambda, so it cannot be pickled to reach a worker."""

    def __init__(self) -> None:
        self.callback = lambda: None


class TestStartFailsFastWhenTheTaskCannotBeSent:
    @pytest.mark.parametrize("start", ALL_STARTS)
    def test_broker_failure_marks_the_record_failed_and_raises(self, uow, task_runner, start):
        """The record is committed first; when sending fails it is FAILED, so the assembly is not held."""
        admin, assembly, _ = _dispatch_setup(uow)
        broker_error = ConnectionError("broker down")
        task_runner.fail_dispatch = broker_error

        with pytest.raises(TaskDispatchError) as exc_info:
            start(uow, admin, assembly, task_runner)

        assert exc_info.value.__cause__ is broker_error
        assert exc_info.value.user_msg() == DISPATCH_FAILED_MESSAGE
        (record,) = uow.selection_run_records.get_by_assembly_id(assembly.id)
        assert record.status == SelectionRunStatus.FAILED
        assert record.error_message.startswith(DISPATCH_FAILED_MESSAGE)
        assert record.completed_at is not None
        assert uow.committed
        assert task_runner.submitted == []

    def test_an_argument_that_cannot_be_pickled_raises_before_any_record_is_written(
        self, uow, task_runner, monkeypatch
    ):
        """The runner checks the arguments when the task is prepared, so a serialisation bug leaves no record."""
        admin, assembly, gsheet = _dispatch_setup(uow)
        monkeypatch.setattr(gsheet, "to_data_source", lambda **_kwargs: _Unpicklable())

        with pytest.raises((AttributeError, TypeError, pickle.PicklingError)):
            sortition.start_gsheet_load_task(uow, admin.id, assembly.id, task_runner=task_runner)

        assert list(uow.selection_run_records.get_by_assembly_id(assembly.id)) == []
        assert task_runner.submitted == []
