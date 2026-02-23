"""ABOUTME: Unit tests for sortition service layer operations
ABOUTME: Tests Google Sheets loading task management and selection run monitoring with fake repositories"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from sortition_algorithms import GSheetDataSource, RunReport

from opendlp.domain.assembly import Assembly, AssemblyGSheet, SelectionRunRecord
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, ManageOldTabsState, SelectionRunStatus, SelectionTaskType
from opendlp.service_layer import sortition
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    GoogleSheetConfigNotFoundError,
    InsufficientPermissions,
    InvalidSelection,
)
from tests.data import VALID_GSHEET_URL
from tests.fakes import FakeUnitOfWork


class TestStartGsheetLoadTask:
    """Test starting Google Sheets loading tasks."""

    def test_start_gsheet_load_task_success_admin(self):
        """Test successful task start by admin user."""
        uow = FakeUnitOfWork()

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
            check_same_address_cols=["address1", "postcode"],  # Required when check_same_address=True
            columns_to_keep=["first_name", "last_name", "age"],  # Required by Settings
        )
        uow.assembly_gsheets.add(gsheet)

        with patch("opendlp.service_layer.sortition.tasks.load_gsheet.delay") as mock_celery:
            mock_result = Mock()
            mock_result.id = "celery-task-id"
            mock_celery.return_value = mock_result

            task_id = sortition.start_gsheet_load_task(uow, admin_user.id, assembly.id)

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

        # Verify Celery task was called
        mock_celery.assert_called_once()
        call_args = mock_celery.call_args
        assert call_args[1]["task_id"] == task_id
        assert isinstance(call_args[1]["data_source"], GSheetDataSource)
        assert call_args[1]["data_source"].feature_tab_name == gsheet.select_targets_tab
        assert call_args[1]["data_source"].people_tab_name == gsheet.select_registrants_tab

        assert uow.committed

    def test_start_gsheet_load_task_assembly_not_found(self):
        """Test error when assembly doesn't exist."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        non_existent_id = uuid.uuid4()

        with pytest.raises(AssemblyNotFoundError, match=f"Assembly {non_existent_id} not found"):
            sortition.start_gsheet_load_task(uow, admin_user.id, non_existent_id)

    def test_start_gsheet_load_task_no_gsheet_config(self):
        """Test error when assembly has no Google Sheets configuration."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)
        # No gsheet configuration added

        with pytest.raises(
            GoogleSheetConfigNotFoundError, match=f"No Google Sheets configuration found for assembly {assembly.id}"
        ):
            sortition.start_gsheet_load_task(uow, admin_user.id, assembly.id)

    def test_start_gsheet_load_task_insufficient_permissions(self):
        """Test error when user doesn't have management permissions."""
        uow = FakeUnitOfWork()
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
            check_same_address_cols=["address1", "postcode"],
            columns_to_keep=["first_name", "last_name", "age"],
        )
        uow.assembly_gsheets.add(gsheet)

        with pytest.raises(InsufficientPermissions):
            sortition.start_gsheet_load_task(uow, regular_user.id, assembly.id)


class TestGetSelectionRunStatus:
    """Test getting selection run status."""

    def test_get_selection_run_status_exists(self):
        """Test getting status for existing task."""
        uow = FakeUnitOfWork()

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

        result = sortition.get_selection_run_status(uow, task_id)
        run_record = result.run_record

        assert run_record is not None
        assert run_record.task_id == task_id
        assert run_record.assembly_id == assembly_id
        assert run_record.status == SelectionRunStatus.RUNNING
        assert len(run_record.log_messages) == 2

    def test_get_selection_run_status_not_found(self):
        """Test getting status for non-existent task."""
        uow = FakeUnitOfWork()

        non_existent_id = uuid.uuid4()
        result = sortition.get_selection_run_status(uow, non_existent_id)

        assert result.run_record is None


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

    def test_get_latest_run_for_assembly_exists(self):
        """Test getting latest run when runs exist."""
        uow = FakeUnitOfWork()

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

    def test_get_latest_run_for_assembly_not_found(self):
        """Test getting latest run when no runs exist."""
        uow = FakeUnitOfWork()

        non_existent_assembly_id = uuid.uuid4()
        result = sortition.get_latest_run_for_assembly(uow, non_existent_assembly_id)

        assert result is None


class TestCheckAndUpdateTaskHealth:
    """Test checking and updating task health status."""

    def test_ignores_completed_tasks(self):
        """Test that completed tasks are not checked or modified."""
        uow = FakeUnitOfWork()

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
        sortition.check_and_update_task_health(uow, task_id)

        # Record should be unchanged
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.COMPLETED
        assert len(updated_record.log_messages) == 1

    def test_ignores_failed_tasks(self):
        """Test that failed tasks are not checked or modified."""
        uow = FakeUnitOfWork()

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
        sortition.check_and_update_task_health(uow, task_id)

        # Record should be unchanged
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.FAILED
        assert updated_record.error_message == "Original error"

    def test_marks_running_task_as_failed_when_celery_says_failure(self):
        """Test that RUNNING task is marked FAILED when Celery reports FAILURE state."""
        uow = FakeUnitOfWork()

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

        # Mock Celery to return FAILURE state
        with patch("opendlp.service_layer.sortition.app.app.AsyncResult") as mock_async_result:
            mock_result = Mock()
            mock_result.state = "FAILURE"
            mock_result.info = Exception("Task crashed")
            mock_async_result.return_value = mock_result

            sortition.check_and_update_task_health(uow, task_id)

        # Record should be marked as FAILED
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.FAILED
        assert "stopped unexpectedly" in updated_record.error_message
        assert "contact the administrators" in updated_record.error_message
        assert updated_record.completed_at is not None
        assert any("ERROR" in msg for msg in updated_record.log_messages)

    def test_marks_running_task_as_failed_when_celery_says_revoked(self):
        """Test that RUNNING task is marked FAILED when Celery reports REVOKED state."""
        uow = FakeUnitOfWork()

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

        # Mock Celery to return REVOKED state
        with patch("opendlp.service_layer.sortition.app.app.AsyncResult") as mock_async_result:
            mock_result = Mock()
            mock_result.state = "REVOKED"
            mock_result.info = None
            mock_async_result.return_value = mock_result

            sortition.check_and_update_task_health(uow, task_id)

        # Record should be marked as FAILED
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.FAILED
        assert "stopped unexpectedly" in updated_record.error_message

    def test_marks_running_task_as_failed_when_celery_forgot_it(self):
        """Test that RUNNING task is marked FAILED when Celery has no record (state=PENDING)."""
        uow = FakeUnitOfWork()

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

        # Mock Celery to return PENDING (which means Celery forgot about it)
        with patch("opendlp.service_layer.sortition.app.app.AsyncResult") as mock_async_result:
            mock_result = Mock()
            mock_result.state = "PENDING"
            mock_result.info = None
            mock_async_result.return_value = mock_result

            sortition.check_and_update_task_health(uow, task_id)

        # Record should be marked as FAILED
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.FAILED
        assert "stopped unexpectedly" in updated_record.error_message

    def test_leaves_running_task_alone_when_celery_says_started(self):
        """Test that RUNNING task is left alone when Celery reports STARTED state."""
        uow = FakeUnitOfWork()

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

        # Mock Celery to return STARTED state (task is running fine)
        with patch("opendlp.service_layer.sortition.app.app.AsyncResult") as mock_async_result:
            mock_result = Mock()
            mock_result.state = "STARTED"
            mock_result.info = {}
            mock_async_result.return_value = mock_result

            sortition.check_and_update_task_health(uow, task_id)

        # Record should be unchanged
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.RUNNING
        assert len(updated_record.log_messages) == 1

    def test_leaves_running_task_alone_when_celery_says_success(self):
        """Test that RUNNING task is left alone when Celery reports SUCCESS state."""
        uow = FakeUnitOfWork()

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

        # Mock Celery to return SUCCESS state
        with patch("opendlp.service_layer.sortition.app.app.AsyncResult") as mock_async_result:
            mock_result = Mock()
            mock_result.state = "SUCCESS"
            mock_result.info = {}
            mock_async_result.return_value = mock_result

            sortition.check_and_update_task_health(uow, task_id)

        # Record should be unchanged - let normal polling handle SUCCESS
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.RUNNING
        assert len(updated_record.log_messages) == 1

    def test_marks_pending_task_as_failed_when_celery_says_failure(self):
        """Test that PENDING task is marked FAILED when Celery reports FAILURE state."""
        uow = FakeUnitOfWork()

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

        # Mock Celery to return FAILURE state
        with patch("opendlp.service_layer.sortition.app.app.AsyncResult") as mock_async_result:
            mock_result = Mock()
            mock_result.state = "FAILURE"
            mock_result.info = Exception("Failed to start")
            mock_async_result.return_value = mock_result

            sortition.check_and_update_task_health(uow, task_id)

        # Record should be marked as FAILED
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.FAILED
        assert "failed to start" in updated_record.error_message.lower()

    def test_marks_task_as_failed_when_timeout_exceeded(self):
        """Test that task is marked FAILED when it exceeds the timeout."""
        uow = FakeUnitOfWork()

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
        sortition.check_and_update_task_health(uow, task_id, timeout_hours=24)

        # Record should be marked as FAILED due to timeout
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.FAILED
        assert "timeout" in updated_record.error_message.lower()

    def test_does_not_fail_task_within_timeout(self):
        """Test that task is not marked failed when within timeout period."""
        uow = FakeUnitOfWork()

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

        # Mock Celery to return STARTED (running normally)
        with patch("opendlp.service_layer.sortition.app.app.AsyncResult") as mock_async_result:
            mock_result = Mock()
            mock_result.state = "STARTED"
            mock_result.info = {}
            mock_async_result.return_value = mock_result

            # Check with 24 hour timeout - should not fail
            sortition.check_and_update_task_health(uow, task_id, timeout_hours=24)

        # Record should still be RUNNING
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.RUNNING

    def test_does_nothing_when_task_not_found(self):
        """Test that function handles gracefully when task doesn't exist."""
        uow = FakeUnitOfWork()

        non_existent_id = uuid.uuid4()

        # Should not raise an exception
        sortition.check_and_update_task_health(uow, non_existent_id)

    def test_handles_missing_celery_task_id_gracefully(self):
        """Test that function handles gracefully when celery_task_id is None or empty."""
        uow = FakeUnitOfWork()

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

        # Should not raise an exception (no AsyncResult call)
        sortition.check_and_update_task_health(uow, task_id)

        # Record should still be RUNNING (can't check health without celery_task_id)
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.RUNNING

    def test_handles_empty_celery_task_id_gracefully(self):
        """Test that function handles gracefully when celery_task_id is empty string."""
        uow = FakeUnitOfWork()

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

        # Should not raise an exception (no AsyncResult call)
        sortition.check_and_update_task_health(uow, task_id)

        # Record should still be RUNNING (can't check health without celery_task_id)
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.RUNNING


class TestCancelTask:
    """Test cancelling running tasks."""

    def test_cancel_pending_task_success(self):
        """Test successfully cancelling a PENDING task."""
        uow = FakeUnitOfWork()

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
        with patch("opendlp.service_layer.sortition.app.app.control.revoke") as mock_revoke:
            sortition.cancel_task(uow, admin_user.id, assembly.id, task_id)
            mock_revoke.assert_called_once_with("celery-123", terminate=True)

        # Verify task is CANCELLED
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.CANCELLED
        assert updated_record.completed_at is not None
        assert "admin" in updated_record.error_message  # display_name returns email prefix
        assert "cancelled" in updated_record.error_message.lower()
        assert "cancelled" in updated_record.log_messages[-1].lower()

    def test_cancel_running_task_success(self):
        """Test successfully cancelling a RUNNING task."""
        uow = FakeUnitOfWork()

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
        with patch("opendlp.service_layer.sortition.app.app.control.revoke") as mock_revoke:
            sortition.cancel_task(uow, admin_user.id, assembly.id, task_id)
            mock_revoke.assert_called_once_with("celery-456", terminate=True)

        # Verify task is CANCELLED
        updated_record = uow.selection_run_records.get_by_task_id(task_id)
        assert updated_record.status == SelectionRunStatus.CANCELLED
        assert updated_record.completed_at is not None

    def test_cancel_already_completed_task_fails(self):
        """Test that cancelling a COMPLETED task raises an error."""
        uow = FakeUnitOfWork()

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
            sortition.cancel_task(uow, admin_user.id, assembly.id, task_id)

    def test_cancel_already_failed_task_fails(self):
        """Test that cancelling a FAILED task raises an error."""
        uow = FakeUnitOfWork()

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
            sortition.cancel_task(uow, admin_user.id, assembly.id, task_id)

    def test_cancel_already_cancelled_task_fails(self):
        """Test that cancelling a CANCELLED task raises an error."""
        uow = FakeUnitOfWork()

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
            sortition.cancel_task(uow, admin_user.id, assembly.id, task_id)

    def test_cancel_nonexistent_task_fails(self):
        """Test that cancelling a non-existent task raises an error."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Attempt to cancel non-existent task
        with pytest.raises(InvalidSelection, match="Task not found"):
            sortition.cancel_task(uow, admin_user.id, assembly.id, uuid.uuid4())

    def test_cancel_task_celery_revoke_fails_still_marks_cancelled(self):
        """Test that task is marked CANCELLED even if Celery revoke fails."""
        uow = FakeUnitOfWork()

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

        # Cancel the task with Celery revoke failing
        with patch("opendlp.service_layer.sortition.app.app.control.revoke") as mock_revoke:
            mock_revoke.side_effect = Exception("Celery connection error")
            sortition.cancel_task(uow, admin_user.id, assembly.id, task_id)

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


class TestSortitionErrorHandling:
    """Test that sortition-algorithms library errors are properly converted to service layer exceptions."""

    def test_start_gsheet_load_task_invalid_settings_raises_invalid_selection(self):
        """Test that ConfigurationError from to_settings() is converted to InvalidSelection."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Create gsheet configuration with invalid settings
        # check_same_address=True but no check_same_address_cols will cause ConfigurationError
        gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
            check_same_address=True,
            check_same_address_cols=[],  # Empty - will cause ConfigurationError
            columns_to_keep=["first_name", "last_name"],
        )
        uow.assembly_gsheets.add(gsheet)

        # Should raise InvalidSelection, not ConfigurationError
        with pytest.raises(InvalidSelection, match="check_same_address is TRUE but there are no columns"):
            sortition.start_gsheet_load_task(uow, admin_user.id, assembly.id)

    def test_start_gsheet_select_task_invalid_settings_raises_invalid_selection(self):
        """Test that ConfigurationError from to_settings() is converted to InvalidSelection in select task."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly with valid number_to_select
        assembly = Assembly(title="Test Assembly", number_to_select=10)
        uow.assemblies.add(assembly)

        # Create gsheet configuration with invalid settings
        gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
            check_same_address=True,
            check_same_address_cols=[],  # Empty - will cause ConfigurationError
            columns_to_keep=["first_name", "last_name"],
        )
        uow.assembly_gsheets.add(gsheet)

        # Should raise InvalidSelection, not ConfigurationError
        with pytest.raises(InvalidSelection, match="check_same_address is TRUE but there are no columns"):
            sortition.start_gsheet_select_task(uow, admin_user.id, assembly.id)

    def test_start_gsheet_replace_load_task_invalid_settings_raises_invalid_selection(self):
        """Test that ConfigurationError from to_settings() is converted to InvalidSelection in replace load."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Create gsheet configuration with invalid settings
        gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
            check_same_address=True,
            check_same_address_cols=[],  # Empty - will cause ConfigurationError
            columns_to_keep=["first_name", "last_name"],
        )
        uow.assembly_gsheets.add(gsheet)

        # Should raise InvalidSelection, not ConfigurationError
        with pytest.raises(InvalidSelection, match="check_same_address is TRUE but there are no columns"):
            sortition.start_gsheet_replace_load_task(uow, admin_user.id, assembly.id)

    def test_start_gsheet_replace_task_invalid_settings_raises_invalid_selection(self):
        """Test that ConfigurationError from to_settings() is converted to InvalidSelection in replace task."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Create assembly
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        # Create gsheet configuration with invalid settings
        gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
            check_same_address=True,
            check_same_address_cols=[],  # Empty - will cause ConfigurationError
            columns_to_keep=["first_name", "last_name"],
        )
        uow.assembly_gsheets.add(gsheet)

        # Should raise InvalidSelection, not ConfigurationError
        with pytest.raises(InvalidSelection, match="check_same_address is TRUE but there are no columns"):
            sortition.start_gsheet_replace_task(uow, admin_user.id, assembly.id, number_to_select=5)
