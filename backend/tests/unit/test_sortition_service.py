"""ABOUTME: Unit tests for sortition service layer operations
ABOUTME: Tests Google Sheets loading task management and selection run monitoring with fake repositories"""

import uuid
from unittest.mock import Mock, patch

import pytest
from sortition_algorithms import GSheetDataSource

from opendlp.domain.assembly import Assembly, AssemblyGSheet, SelectionRunRecord
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, SelectionRunStatus, SelectionTaskType
from opendlp.service_layer import sortition
from opendlp.service_layer.exceptions import InsufficientPermissions
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

        with pytest.raises(ValueError, match=f"Assembly {non_existent_id} not found"):
            sortition.start_gsheet_load_task(uow, admin_user.id, non_existent_id)

    def test_start_gsheet_load_task_no_gsheet_config(self):
        """Test error when assembly has no Google Sheets configuration."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)
        # No gsheet configuration added

        with pytest.raises(ValueError, match=f"No Google Sheets configuration found for assembly {assembly.id}"):
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

        run_record, _, _ = sortition.get_selection_run_status(uow, task_id)

        assert run_record is not None
        assert run_record.task_id == task_id
        assert run_record.assembly_id == assembly_id
        assert run_record.status == SelectionRunStatus.RUNNING
        assert len(run_record.log_messages) == 2

    def test_get_selection_run_status_not_found(self):
        """Test getting status for non-existent task."""
        uow = FakeUnitOfWork()

        non_existent_id = uuid.uuid4()
        result, _, _ = sortition.get_selection_run_status(uow, non_existent_id)

        assert result is None


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
