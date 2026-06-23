"""ABOUTME: End-to-end tests for sortition-related Flask routes
ABOUTME: Keeps PG happy-path smokes, DB-semantics pagination, and the Celery dispatch/revoke tail"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.users import UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


class TestSortitionRoutes:
    """PG happy-path smoke tests for sortition routes."""

    def test_select_assembly_gsheet_get_success(self, logged_in_admin, assembly_with_gsheet):
        """Test GET request to selection page succeeds for admin."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select")

        assert response.status_code == 200
        assert b"Google Spreadsheet Configuration" in response.data
        assert b"Check Spreadsheet" in response.data

    def test_progress_endpoint_returns_fragment_for_running_task(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test progress endpoint returns HTML fragment with HTMX attributes for running task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a running task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.LOAD_GSHEET,
                log_messages=["Task started", "Processing data"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/progress")

        assert response.status_code == 200
        # Should contain the progress section
        assert b"Current status: running" in response.data
        assert b"Task started" in response.data
        assert b"Processing data" in response.data
        # Should contain HTMX polling attributes
        assert b"hx-get" in response.data
        assert b"hx-trigger" in response.data
        assert b"hx-swap" in response.data
        assert b"every 1s" in response.data

    @patch("opendlp.service_layer.sortition.tasks.load_gsheet.delay")
    def test_gsheet_load_success(self, mock_celery, logged_in_admin, assembly_with_gsheet, postgres_session_factory):
        """Test POST request to start loading task succeeds."""
        assembly, _ = assembly_with_gsheet
        mock_result = Mock()
        mock_result.id = "celery-task-id"
        mock_celery.return_value = mock_result

        response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_load")

        # Should redirect to status page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_select" in response.headers["Location"]

        # Verify task was created in database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            records = list(uow.selection_run_records.get_by_assembly_id(assembly.id))
            assert len(records) == 1
            assert records[0].status == SelectionRunStatus.PENDING
            assert records[0].task_type == SelectionTaskType.LOAD_GSHEET
            assert "Task submitted for Google Sheets loading" in records[0].log_messages

    @patch("opendlp.service_layer.sortition.tasks.run_select.apply_async")
    def test_gsheet_select_success(self, mock_celery, logged_in_admin, assembly_with_gsheet, postgres_session_factory):
        """Test POST request to start loading task succeeds."""
        assembly, _ = assembly_with_gsheet
        mock_result = Mock()
        mock_result.id = "celery-task-id"
        mock_celery.return_value = mock_result

        response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_select", data={"test_selection": "0"})

        # Should redirect to status page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_select" in response.headers["Location"]

        # Verify task was created in database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            records = list(uow.selection_run_records.get_by_assembly_id(assembly.id))
            assert len(records) == 1
            assert records[0].status == SelectionRunStatus.PENDING
            assert records[0].task_type == SelectionTaskType.SELECT_GSHEET
            assert "Task submitted for Google Sheets selection" in records[0].log_messages

    @patch("opendlp.service_layer.sortition.tasks.run_select.apply_async")
    def test_gsheet_test_select_success(
        self, mock_celery, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test POST request to start loading task succeeds."""
        assembly, _ = assembly_with_gsheet
        mock_result = Mock()
        mock_result.id = "celery-task-id"
        mock_celery.return_value = mock_result

        response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_select", data={"test_selection": "1"})

        # Should redirect to status page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_select" in response.headers["Location"]

        # Verify task was created in database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            records = list(uow.selection_run_records.get_by_assembly_id(assembly.id))
            assert len(records) == 1
            assert records[0].status == SelectionRunStatus.PENDING
            assert records[0].task_type == SelectionTaskType.TEST_SELECT_GSHEET
            assert "Task submitted for Google Sheets TEST selection" in records[0].log_messages


class TestReplacementRoutes:
    """End-to-end tests for replacement selection routes."""

    def test_replace_assembly_gsheet_get_success(self, logged_in_admin, assembly_with_gsheet):
        """Test GET request to replacement page succeeds for admin."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_replace")

        assert response.status_code == 200
        assert b"Replacements for" in response.data
        assert b"Check Spreadsheet" in response.data

    @patch("opendlp.service_layer.sortition.tasks.load_gsheet.delay")
    def test_gsheet_replace_load_success(
        self, mock_celery, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test POST request to start replacement loading task succeeds."""
        assembly, _ = assembly_with_gsheet
        mock_result = Mock()
        mock_result.id = "celery-task-id"
        mock_celery.return_value = mock_result

        response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_replace_load")

        # Should redirect to status page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_replace" in response.headers["Location"]

        # Verify task was created in database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            records = list(uow.selection_run_records.get_by_assembly_id(assembly.id))
            assert len(records) == 1
            assert records[0].status == SelectionRunStatus.PENDING
            assert records[0].task_type == SelectionTaskType.LOAD_REPLACEMENT_GSHEET
            assert "Task submitted for Google Sheets replacement data loading" in records[0].log_messages

    @patch("opendlp.service_layer.sortition.tasks.run_select.delay")
    def test_start_gsheet_replace_success(
        self, mock_celery, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test POST request to start replacement selection task succeeds."""
        assembly, _ = assembly_with_gsheet
        mock_result = Mock()
        mock_result.id = "celery-task-id"
        mock_celery.return_value = mock_result

        response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_replace", data={"number_to_select": "10"})

        # Should redirect to status page with num_to_select query param
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_replace" in response.headers["Location"]
        assert "num_to_select=10" in response.headers["Location"]

        # Verify task was created in database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            records = list(uow.selection_run_records.get_by_assembly_id(assembly.id))
            assert len(records) == 1
            assert records[0].status == SelectionRunStatus.PENDING
            assert records[0].task_type == SelectionTaskType.SELECT_REPLACEMENT_GSHEET
            assert "Task submitted for Google Sheets replacement selection of 10 people" in records[0].log_messages


class TestSortitionRoutesWithAssemblyRole:
    """Test sortition routes with assembly-specific roles."""

    @pytest.fixture
    def assembly_managed_by_user(self, regular_user, assembly_with_gsheet, postgres_session_factory):
        """Create user with assembly manager role."""
        assembly, _ = assembly_with_gsheet
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            # Give user assembly manager role
            role = UserAssemblyRole(
                user_id=regular_user.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER
            )
            uow.user_assembly_roles.add(role)
            # regular_user.assembly_roles.append(role)

            uow.commit()
        return assembly.id

    @patch("opendlp.service_layer.sortition.tasks.load_gsheet.delay")
    def test_assembly_manager_can_start_task(self, mock_celery, logged_in_user, assembly_managed_by_user):
        """Test user with assembly manager role can start task."""
        mock_result = Mock()
        mock_result.id = "celery-task-id"
        mock_celery.return_value = mock_result

        assembly_id = assembly_managed_by_user

        response = logged_in_user.post(f"/assemblies/{assembly_id}/gsheet_load")

        # Should succeed and redirect to status page
        assert response.status_code == 302
        assert f"/assemblies/{assembly_id}/gsheet_select" in response.headers["Location"]


class TestManageTabsRoutes:
    """End-to-end tests for tab management routes."""

    def test_manage_tabs_get_success(self, logged_in_admin, assembly_with_gsheet):
        """Test GET request to manage tabs page succeeds for admin."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_manage_tabs")

        assert response.status_code == 200
        assert b"Manage Generated Tabs" in response.data or b"manage" in response.data.lower()
        assert b"List Old Tabs" in response.data

    @patch("opendlp.service_layer.sortition.tasks.manage_old_tabs.delay")
    def test_list_tabs_success(self, mock_celery, logged_in_admin, assembly_with_gsheet, postgres_session_factory):
        """Test POST request to start listing task succeeds."""
        assembly, _ = assembly_with_gsheet
        mock_result = Mock()
        mock_result.id = "celery-task-id"
        mock_celery.return_value = mock_result

        response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_list_tabs")

        # Should redirect to status page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_manage_tabs" in response.headers["Location"]

        # Verify task was created in database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            records = list(uow.selection_run_records.get_by_assembly_id(assembly.id))
            assert len(records) == 1
            assert records[0].status == SelectionRunStatus.PENDING
            assert records[0].task_type == SelectionTaskType.LIST_OLD_TABS
            assert "Task submitted for listing old output tabs" in records[0].log_messages

    @patch("opendlp.service_layer.sortition.tasks.manage_old_tabs.delay")
    def test_delete_tabs_success(self, mock_celery, logged_in_admin, assembly_with_gsheet, postgres_session_factory):
        """Test POST request to start deletion task succeeds."""
        assembly, _ = assembly_with_gsheet
        mock_result = Mock()
        mock_result.id = "celery-task-id"
        mock_celery.return_value = mock_result

        response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_delete_tabs")

        # Should redirect to status page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_manage_tabs" in response.headers["Location"]

        # Verify task was created in database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            records = list(uow.selection_run_records.get_by_assembly_id(assembly.id))
            assert len(records) == 1
            assert records[0].status == SelectionRunStatus.PENDING
            assert records[0].task_type == SelectionTaskType.DELETE_OLD_TABS
            assert "Task submitted for deleting old output tabs" in records[0].log_messages


class TestSelectionRunHistory:
    """End-to-end tests for selection run history viewing and navigation."""

    def test_view_assembly_data_shows_run_history(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test that assembly data page shows selection run history table."""
        assembly, _ = assembly_with_gsheet

        # Create some run records
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            # Completed run
            record1 = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=uuid.uuid4(),
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_GSHEET,
                log_messages=["Selection completed"],
                created_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                comment="Initial selection",
            )
            # Failed run
            record2 = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=uuid.uuid4(),
                status=SelectionRunStatus.FAILED,
                task_type=SelectionTaskType.LOAD_GSHEET,
                log_messages=["Load failed"],
                created_at=datetime.now(UTC) - timedelta(hours=1),
                error_message="Connection error",
            )
            uow.selection_run_records.add(record1)
            uow.selection_run_records.add(record2)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/data")

        assert response.status_code == 200
        # Check for history section
        assert b"Selection Run History" in response.data
        assert b"Showing 1 to 2 of 2 runs" in response.data
        # Check status tags
        assert b"Completed" in response.data
        assert b"Failed" in response.data
        # Check task types (using task_type_verbose formatting)
        assert b"Select google spreadsheet" in response.data
        assert b"Load google spreadsheet" in response.data
        # Check comment appears
        assert b"Initial selection" in response.data

    @pytest.mark.db_semantics
    def test_view_assembly_data_pagination_works(self, logged_in_admin, assembly_with_gsheet, postgres_session_factory):
        """Test that pagination works with >50 run records."""
        assembly, _ = assembly_with_gsheet

        # Create 55 run records
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            for i in range(55):
                record = SelectionRunRecord(
                    assembly_id=assembly.id,
                    task_id=uuid.uuid4(),
                    status=SelectionRunStatus.COMPLETED,
                    task_type=SelectionTaskType.SELECT_GSHEET,
                    log_messages=[f"Run {i}"],
                    created_at=datetime.now(UTC) - timedelta(minutes=i),
                )
                uow.selection_run_records.add(record)
            uow.commit()

        # Test page 1
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/data")
        assert response.status_code == 200
        assert b"Showing 1 to 50 of 55 runs" in response.data
        assert b"govuk-pagination" in response.data
        assert b"Next" in response.data

        # Test page 2
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/data?page=2")
        assert response.status_code == 200
        assert b"Showing 51 to 55 of 55 runs" in response.data
        assert b"Previous" in response.data


class TestCancelTaskRoutes:
    """End-to-end tests for task cancellation routes."""

    def test_cancel_gsheet_select_success(self, logged_in_admin, assembly_with_gsheet, postgres_session_factory):
        """Test POST to cancel endpoint successfully cancels a running task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a RUNNING task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.SELECT_GSHEET,
                celery_task_id="test-celery-id",
                log_messages=["Task started"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # POST to cancel endpoint
        with patch("opendlp.service_layer.sortition.app.app.control.revoke"):
            response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/cancel")

        # Should redirect back to task page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_select/{task_id}" in response.headers["Location"]

        # Verify task status is CANCELLED
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record.status == SelectionRunStatus.CANCELLED
            assert record.completed_at is not None

    def test_cancel_gsheet_select_already_completed(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test POST to cancel endpoint with completed task shows error.

        Stays e2e: the finished-task selection status page reads cached selection
        data from Redis, so it cannot run on the fake-backed component app.
        """
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a COMPLETED task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_GSHEET,
                celery_task_id="test-celery-id",
                log_messages=["Task completed"],
                completed_at=datetime.now(UTC),
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # POST to cancel endpoint
        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet_select/{task_id}/cancel", follow_redirects=True
        )

        # Should show error message
        assert response.status_code == 200
        assert b"Cannot cancel" in response.data or b"already finished" in response.data

    def test_cancel_gsheet_replace_success(self, logged_in_admin, assembly_with_gsheet, postgres_session_factory):
        """Test POST to cancel replacement task succeeds."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a RUNNING replacement task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
                celery_task_id="test-celery-replace-id",
                log_messages=["Replacement task started"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # POST to cancel endpoint
        with patch("opendlp.service_layer.sortition.app.app.control.revoke"):
            response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_replace/{task_id}/cancel")

        # Should redirect back to task page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_replace/{task_id}" in response.headers["Location"]

        # Verify task status is CANCELLED
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record.status == SelectionRunStatus.CANCELLED

    def test_cancel_gsheet_manage_tabs_success(self, logged_in_admin, assembly_with_gsheet, postgres_session_factory):
        """Test POST to cancel manage tabs task succeeds."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a RUNNING manage tabs task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.LIST_OLD_TABS,
                celery_task_id="test-celery-tabs-id",
                log_messages=["Listing tabs"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # POST to cancel endpoint
        with patch("opendlp.service_layer.sortition.app.app.control.revoke"):
            response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_manage_tabs/{task_id}/cancel")

        # Should redirect back to task page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_manage_tabs/{task_id}" in response.headers["Location"]

        # Verify task status is CANCELLED
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record.status == SelectionRunStatus.CANCELLED

    def test_cancel_displays_in_ui(self, logged_in_admin, assembly_with_gsheet, postgres_session_factory):
        """Test GET request shows cancelled task status in UI.

        Stays e2e: the finished-task selection status page reads cached selection
        data from Redis, so it cannot run on the fake-backed component app.
        """
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a CANCELLED task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.CANCELLED,
                task_type=SelectionTaskType.SELECT_GSHEET,
                celery_task_id="test-celery-cancelled-id",
                log_messages=["Task cancelled"],
                error_message="Task cancelled by admin@example.com",
                completed_at=datetime.now(UTC),
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # GET the task page
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}")

        # Should show cancelled status
        assert response.status_code == 200
        assert b"Task Cancelled" in response.data or b"cancelled" in response.data.lower()
