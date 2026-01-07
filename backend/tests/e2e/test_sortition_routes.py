"""ABOUTME: End-to-end tests for sortition-related Flask routes
ABOUTME: Tests Google Sheets loading task management routes through complete HTTP request/response cycles"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from opendlp.domain.assembly import AssemblyGSheet, SelectionRunRecord
from opendlp.domain.users import UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.data import VALID_GSHEET_URL


class TestSortitionRoutes:
    """Integration tests for sortition routes."""

    # Use the standard e2e fixtures: logged_in_admin, admin_user, postgres_session_factory, etc

    def test_select_assembly_gsheet_get_success(self, logged_in_admin, assembly_with_gsheet):
        """Test GET request to selection page succeeds for admin."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select")

        assert response.status_code == 200
        assert b"Google Spreadsheet Configuration" in response.data
        assert b"Check Spreadsheet" in response.data

    def test_select_assembly_gsheet_get_requires_auth(self, client, assembly_with_gsheet):
        """Test GET request redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.get(f"/assemblies/{assembly.id}/gsheet_select")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_select_assembly_gsheet_with_run_shows_status(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test GET request with run_id shows task status."""
        assembly, _ = assembly_with_gsheet
        # Create a selection run record
        task_id = uuid.uuid4()
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.LOAD_GSHEET,
                log_messages=["Task started", "Loading data"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}")

        assert response.status_code == 200
        assert b"Current status: running" in response.data
        assert b"Loading data" in response.data

    def test_select_assembly_gsheet_with_run_validates_assembly(
        self, admin_user, logged_in_admin, postgres_session_factory
    ):
        """Test GET request with run_id for wrong assembly redirects."""
        # Create assembly and task for different assembly
        wrong_assembly_id = uuid.uuid4()
        task_id = uuid.uuid4()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(
                uow=uow,
                title="Wrong Assembly",
                created_by_user_id=admin_user.id,
                question="What should we configure?",
                first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            )
            wrong_assembly_id = assembly.id
            uow.flush()

            gsheet = AssemblyGSheet(
                assembly_id=assembly.id,
                url=VALID_GSHEET_URL,
                check_same_address_cols=["address1", "postcode"],
                columns_to_keep=["first_name", "last_name", "age"],
            )
            uow.assembly_gsheets.add(gsheet)

            record = SelectionRunRecord(
                assembly_id=wrong_assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.LOAD_GSHEET,
                status=SelectionRunStatus.RUNNING,
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Try to access task from different assembly
        different_assembly_id = uuid.uuid4()
        response = logged_in_admin.get(f"/assemblies/{different_assembly_id}/gsheet_select/{task_id}")

        # Should redirect due to validation error
        assert response.status_code == 404

    def test_select_assembly_gsheet_with_none_to_select(self, admin_user, logged_in_admin, postgres_session_factory):
        """Test POST request with run_id for assembly with zero to select."""
        # Create assembly and task for different assembly
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(
                uow=uow,
                title="None Assembly",
                created_by_user_id=admin_user.id,
                question="What should we configure?",
                first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
                number_to_select=None,
            )
            assembly_id = assembly.id
            uow.flush()

            gsheet = AssemblyGSheet(
                assembly_id=assembly.id,
                url=VALID_GSHEET_URL,
                check_same_address_cols=["address1", "postcode"],
                columns_to_keep=["first_name", "last_name", "age"],
            )
            uow.assembly_gsheets.add(gsheet)
            uow.commit()

        # Try to access task from different assembly
        response = logged_in_admin.post(f"/assemblies/{assembly_id}/gsheet_select")

        # Should redirect due to validation error
        assert response.status_code == 302

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

    @patch("opendlp.service_layer.sortition.tasks.run_select.delay")
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

    @patch("opendlp.service_layer.sortition.tasks.run_select.delay")
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

    def test_gsheet_load_requires_auth(self, client, assembly_with_gsheet):
        """Test POST request redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.post(f"/assemblies/{assembly.id}/gsheet_load")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_gsheet_load_requires_management_permission(self, logged_in_user, assembly_with_gsheet):
        """Test POST request fails for user without management permission."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_user.post(f"/assemblies/{assembly.id}/gsheet_load")

        # Should get 403 Forbidden
        assert response.status_code == 403

    def test_gsheet_load_handles_missing_gsheet(self, logged_in_admin, admin_user, postgres_session_factory):
        """Test POST request handles assembly with no gsheet configuration."""
        # Create assembly without gsheet
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(
                uow=uow,
                title="Assembly No GSheet",
                created_by_user_id=admin_user.id,
                question="What should we configure?",
                first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            )
            uow.commit()
            assembly_id = assembly.id

        response = logged_in_admin.post(f"/assemblies/{assembly_id}/gsheet_load")

        # Should redirect back to select page with error
        assert response.status_code == 302
        assert f"/assemblies/{assembly_id}/gsheet_select" in response.headers["Location"]

    def test_gsheet_load_handles_nonexistent_assembly(self, logged_in_admin):
        """Test POST request handles nonexistent assembly."""
        non_existent_id = uuid.uuid4()
        response = logged_in_admin.post(f"/assemblies/{non_existent_id}/gsheet_load")

        # Should redirect back to select page with error
        assert response.status_code == 404

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
        assert b"every 2s" in response.data

    def test_progress_endpoint_returns_fragment_for_pending_task(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test progress endpoint returns HTML fragment with HTMX attributes for pending task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a pending task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.PENDING,
                task_type=SelectionTaskType.SELECT_GSHEET,
                log_messages=["Task queued"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/progress")

        assert response.status_code == 200
        assert b"Current status: pending" in response.data
        # Should contain HTMX polling attributes
        assert b"hx-get" in response.data
        assert b"hx-trigger" in response.data
        assert b"every 2s" in response.data

    def test_progress_endpoint_returns_fragment_without_polling_for_completed_task(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test progress endpoint returns fragment WITHOUT HTMX polling for completed task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a completed task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.LOAD_GSHEET,
                log_messages=["Task completed successfully"],
                completed_at=datetime.now(UTC),
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/progress")

        assert response.status_code == 200
        assert b"Completed" in response.data
        assert b"Task completed successfully" in response.data
        # Should NOT contain HTMX polling attributes (task is done)
        assert b"hx-trigger" not in response.data
        assert b"every 2s" not in response.data

    def test_progress_endpoint_returns_fragment_without_polling_for_failed_task(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test progress endpoint returns fragment WITHOUT HTMX polling for failed task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a failed task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.FAILED,
                task_type=SelectionTaskType.SELECT_GSHEET,
                log_messages=["Task started", "Error occurred"],
                error_message="Something went wrong",
                completed_at=datetime.now(UTC),
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/progress")

        assert response.status_code == 200
        assert b"Error Details" in response.data
        assert b"Something went wrong" in response.data
        # Should NOT contain HTMX polling attributes (task is done)
        assert b"hx-trigger" not in response.data
        assert b"every 2s" not in response.data

    def test_progress_endpoint_requires_auth(self, client, assembly_with_gsheet, postgres_session_factory):
        """Test progress endpoint redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.LOAD_GSHEET,
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = client.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/progress")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_progress_endpoint_validates_run_belongs_to_assembly(
        self, logged_in_admin, admin_user, assembly_with_gsheet, postgres_session_factory
    ):
        """Test progress endpoint validates that run_id belongs to the correct assembly."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a task for the first assembly
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.LOAD_GSHEET,
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Try to access from a different assembly
        different_assembly_id = uuid.uuid4()
        response = logged_in_admin.get(f"/assemblies/{different_assembly_id}/gsheet_select/{task_id}/progress")

        # Should return 404
        assert response.status_code == 404

    def test_progress_endpoint_handles_nonexistent_run(self, logged_in_admin, assembly_with_gsheet):
        """Test progress endpoint handles request for nonexistent run_id."""
        assembly, _ = assembly_with_gsheet
        non_existent_task_id = uuid.uuid4()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{non_existent_task_id}/progress")

        # Should return 404 when run record not found
        assert response.status_code == 404

    def test_progress_endpoint_requires_management_permission(
        self, logged_in_user, assembly_with_gsheet, postgres_session_factory
    ):
        """Test progress endpoint requires assembly management permission."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.LOAD_GSHEET,
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/progress")

        # Should get 403 Forbidden
        assert response.status_code == 403


class TestReplacementRoutes:
    """End-to-end tests for replacement selection routes."""

    def test_replace_assembly_gsheet_get_success(self, logged_in_admin, assembly_with_gsheet):
        """Test GET request to replacement page succeeds for admin."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_replace")

        assert response.status_code == 200
        assert b"Replacements for" in response.data
        assert b"Check Spreadsheet" in response.data

    def test_replace_assembly_gsheet_get_requires_auth(self, client, assembly_with_gsheet):
        """Test GET request to replacement page redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.get(f"/assemblies/{assembly.id}/gsheet_replace")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_replace_assembly_gsheet_with_run_shows_status(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test GET request with run_id shows task status."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a replacement load run record
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
                log_messages=["Task started", "Loading replacement data"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_replace/{task_id}")

        assert response.status_code == 200
        assert b"Current status: running" in response.data
        assert b"Task started" in response.data
        assert b"Loading replacement data" in response.data

    def test_replace_assembly_gsheet_with_run_validates_assembly(
        self, admin_user, logged_in_admin, postgres_session_factory
    ):
        """Test GET request with run_id for wrong assembly redirects."""
        # Create assembly and task for different assembly
        wrong_assembly_id = uuid.uuid4()
        task_id = uuid.uuid4()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(
                uow=uow,
                title="Wrong Assembly",
                created_by_user_id=admin_user.id,
                question="What should we configure?",
                first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            )
            wrong_assembly_id = assembly.id
            uow.flush()

            gsheet = AssemblyGSheet(
                assembly_id=assembly.id,
                url=VALID_GSHEET_URL,
                check_same_address_cols=["address1", "postcode"],
                columns_to_keep=["first_name", "last_name", "age"],
            )
            uow.assembly_gsheets.add(gsheet)

            record = SelectionRunRecord(
                assembly_id=wrong_assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
                status=SelectionRunStatus.RUNNING,
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Try to access task from different assembly
        different_assembly_id = uuid.uuid4()
        response = logged_in_admin.get(f"/assemblies/{different_assembly_id}/gsheet_replace/{task_id}")

        # Should redirect due to validation error
        assert response.status_code == 404

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

    def test_gsheet_replace_load_requires_auth(self, client, assembly_with_gsheet):
        """Test POST request to replacement load redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.post(f"/assemblies/{assembly.id}/gsheet_replace_load")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_gsheet_replace_load_requires_management_permission(self, logged_in_user, assembly_with_gsheet):
        """Test POST request to replacement load fails for user without management permission."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_user.post(f"/assemblies/{assembly.id}/gsheet_replace_load")

        # Should get 403 Forbidden
        assert response.status_code == 403

    def test_gsheet_replace_load_handles_missing_gsheet(self, logged_in_admin, admin_user, postgres_session_factory):
        """Test POST request to replacement load handles assembly with no gsheet configuration."""
        # Create assembly without gsheet
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(
                uow=uow,
                title="Assembly No GSheet",
                created_by_user_id=admin_user.id,
                question="What should we configure?",
                first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            )
            uow.commit()
            assembly_id = assembly.id

        response = logged_in_admin.post(f"/assemblies/{assembly_id}/gsheet_replace_load")

        # Should redirect back to replace page with error
        assert response.status_code == 302
        assert f"/assemblies/{assembly_id}/gsheet_replace" in response.headers["Location"]

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

    def test_start_gsheet_replace_requires_number(self, logged_in_admin, assembly_with_gsheet):
        """Test POST request to start replacement requires number_to_select."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_replace", data={})

        # Should redirect back with error
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_replace" in response.headers["Location"]

    def test_start_gsheet_replace_validates_number(self, logged_in_admin, assembly_with_gsheet):
        """Test POST request to start replacement validates number_to_select is positive."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_replace", data={"number_to_select": "0"})

        # Should redirect back with error
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_replace" in response.headers["Location"]

    def test_start_gsheet_replace_requires_auth(self, client, assembly_with_gsheet):
        """Test POST request to start replacement redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.post(f"/assemblies/{assembly.id}/gsheet_replace", data={"number_to_select": "10"})

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_start_gsheet_replace_requires_management_permission(self, logged_in_user, assembly_with_gsheet):
        """Test POST request to start replacement fails for user without management permission."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_user.post(f"/assemblies/{assembly.id}/gsheet_replace", data={"number_to_select": "10"})

        # Should get 403 Forbidden
        assert response.status_code == 403

    def test_gsheet_replace_progress_returns_fragment_for_running_task(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test replacement progress endpoint returns HTML fragment with HTMX attributes for running task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a running replacement task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
                log_messages=["Task started", "Processing replacement data"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_replace/{task_id}/progress")

        assert response.status_code == 200
        # Should contain the progress section
        assert b"Current status: running" in response.data
        assert b"Task started" in response.data
        assert b"Processing replacement data" in response.data
        # Should contain HTMX polling attributes
        assert b"hx-get" in response.data
        assert b"hx-trigger" in response.data
        assert b"hx-swap" in response.data
        assert b"every 2s" in response.data

    def test_gsheet_replace_progress_returns_fragment_without_polling_for_completed_task(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test replacement progress endpoint returns fragment WITHOUT HTMX polling for completed task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a completed replacement task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
                log_messages=["Task completed successfully"],
                completed_at=datetime.now(UTC),
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_replace/{task_id}/progress")

        assert response.status_code == 200
        assert b"Completed" in response.data
        assert b"Task completed successfully" in response.data
        # Should NOT contain HTMX polling attributes (task is done)
        assert b"hx-trigger" not in response.data
        assert b"every 2s" not in response.data

    def test_gsheet_replace_progress_requires_auth(self, client, assembly_with_gsheet, postgres_session_factory):
        """Test replacement progress endpoint redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = client.get(f"/assemblies/{assembly.id}/gsheet_replace/{task_id}/progress")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_gsheet_replace_progress_validates_run_belongs_to_assembly(
        self, logged_in_admin, admin_user, assembly_with_gsheet, postgres_session_factory
    ):
        """Test replacement progress endpoint validates that run_id belongs to the correct assembly."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a task for the first assembly
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Try to access from a different assembly
        different_assembly_id = uuid.uuid4()
        response = logged_in_admin.get(f"/assemblies/{different_assembly_id}/gsheet_replace/{task_id}/progress")

        # Should return 404
        assert response.status_code == 404

    def test_gsheet_replace_progress_handles_nonexistent_run(self, logged_in_admin, assembly_with_gsheet):
        """Test replacement progress endpoint handles request for nonexistent run_id."""
        assembly, _ = assembly_with_gsheet
        non_existent_task_id = uuid.uuid4()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_replace/{non_existent_task_id}/progress")

        # Should return 404 when run record not found
        assert response.status_code == 404

    def test_gsheet_replace_progress_requires_management_permission(
        self, logged_in_user, assembly_with_gsheet, postgres_session_factory
    ):
        """Test replacement progress endpoint requires assembly management permission."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet_replace/{task_id}/progress")

        # Should get 403 Forbidden
        assert response.status_code == 403


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

    def test_manage_tabs_get_requires_auth(self, client, assembly_with_gsheet):
        """Test GET request to manage tabs page redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.get(f"/assemblies/{assembly.id}/gsheet_manage_tabs")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_manage_tabs_get_requires_management_permission(self, logged_in_user, assembly_with_gsheet):
        """Test GET request to manage tabs page fails for user without management permission."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet_manage_tabs")

        # Should get 403 Forbidden
        assert response.status_code == 403

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

    def test_list_tabs_requires_auth(self, client, assembly_with_gsheet):
        """Test POST request to list tabs redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.post(f"/assemblies/{assembly.id}/gsheet_list_tabs")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_list_tabs_requires_management_permission(self, logged_in_user, assembly_with_gsheet):
        """Test POST request to list tabs fails for user without management permission."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_user.post(f"/assemblies/{assembly.id}/gsheet_list_tabs")

        # Should get 403 Forbidden
        assert response.status_code == 403

    def test_delete_tabs_requires_auth(self, client, assembly_with_gsheet):
        """Test POST request to delete tabs redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.post(f"/assemblies/{assembly.id}/gsheet_delete_tabs")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_delete_tabs_requires_management_permission(self, logged_in_user, assembly_with_gsheet):
        """Test POST request to delete tabs fails for user without management permission."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_user.post(f"/assemblies/{assembly.id}/gsheet_delete_tabs")

        # Should get 403 Forbidden
        assert response.status_code == 403

    def test_manage_tabs_with_run_shows_status(self, logged_in_admin, assembly_with_gsheet, postgres_session_factory):
        """Test GET request with run_id shows task status."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a tab management run record
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.DELETE_OLD_TABS,
                log_messages=["Task started", "Found 3 old output tab(s) that can be deleted"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_manage_tabs/{task_id}")

        assert response.status_code == 200
        assert b"Task Status" in response.data or b"status" in response.data.lower()
        assert b"Completed" in response.data
        assert b"Found 3 old output tab(s)" in response.data

    def test_progress_endpoint_returns_fragment_for_running_task(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test progress endpoint returns HTML fragment with HTMX attributes for running tab management task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a running tab management task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.DELETE_OLD_TABS,
                log_messages=["Task started", "Listing old tabs"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_manage_tabs/{task_id}/progress")

        assert response.status_code == 200
        assert b"Task Status" in response.data or b"status" in response.data.lower()
        assert b"Task in Progress" in response.data
        assert b"Listing old tabs" in response.data
        # Should contain HTMX polling attributes
        assert b"hx-get" in response.data
        assert b"hx-trigger" in response.data
        assert b"every 2s" in response.data

    def test_progress_endpoint_requires_auth(self, client, assembly_with_gsheet, postgres_session_factory):
        """Test progress endpoint redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.DELETE_OLD_TABS,
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = client.get(f"/assemblies/{assembly.id}/gsheet_manage_tabs/{task_id}/progress")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_progress_endpoint_requires_management_permission(
        self, logged_in_user, assembly_with_gsheet, postgres_session_factory
    ):
        """Test progress endpoint requires assembly management permission."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.DELETE_OLD_TABS,
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet_manage_tabs/{task_id}/progress")

        # Should get 403 Forbidden
        assert response.status_code == 403


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

    def test_view_assembly_data_empty_history(self, logged_in_admin, assembly_with_gsheet):
        """Test that empty state message appears when no runs exist."""
        assembly, _ = assembly_with_gsheet

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/data")

        assert response.status_code == 200
        assert b"Selection Run History" in response.data
        assert b"No selection runs have been performed yet" in response.data

    def test_view_gsheet_run_redirect_routes_select_tasks(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test redirect endpoint routes SELECT task types correctly."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create LOAD_GSHEET run
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.LOAD_GSHEET,
                log_messages=["Loaded"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_runs/{task_id}/view", follow_redirects=False)

        # Should redirect to select endpoint
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_select/{task_id}" in response.headers["Location"]

    def test_view_gsheet_run_redirect_routes_replace_tasks(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test redirect endpoint routes REPLACE task types correctly."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create LOAD_REPLACEMENT_GSHEET run
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
                log_messages=["Selected replacements"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_runs/{task_id}/view", follow_redirects=False)

        # Should redirect to replace endpoint
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_replace/{task_id}" in response.headers["Location"]

    def test_view_gsheet_run_redirect_routes_tabs_tasks(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test redirect endpoint routes tab management task types correctly."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create LIST_OLD_TABS run
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.DELETE_OLD_TABS,
                log_messages=["Deleted tabs"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_runs/{task_id}/view", follow_redirects=False)

        # Should redirect to manage_tabs endpoint
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_manage_tabs/{task_id}" in response.headers["Location"]

    def test_view_gsheet_run_redirect_validates_assembly_ownership(
        self, admin_user, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test redirect endpoint validates run belongs to assembly."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create run for this assembly
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_GSHEET,
                log_messages=["Done"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Try to access via wrong assembly ID
        wrong_assembly_id = uuid.uuid4()
        response = logged_in_admin.get(
            f"/assemblies/{wrong_assembly_id}/gsheet_runs/{task_id}/view", follow_redirects=True
        )

        # Should show error and redirect
        assert response.status_code in [302, 404]
        if response.status_code == 302:
            assert b"Invalid task ID for this assembly" in response.data or b"not found" in response.data

    def test_view_gsheet_run_redirect_requires_auth(self, client, assembly_with_gsheet, postgres_session_factory):
        """Test redirect endpoint requires authentication."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create run
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_GSHEET,
                log_messages=["Done"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = client.get(f"/assemblies/{assembly.id}/gsheet_runs/{task_id}/view")

        # Should redirect to login
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_view_gsheet_run_redirect_requires_permissions(
        self, logged_in_user, assembly_with_gsheet, postgres_session_factory
    ):
        """Test redirect endpoint requires assembly management permissions."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create run
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_GSHEET,
                log_messages=["Done"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet_runs/{task_id}/view")

        # Should get 403 Forbidden
        assert response.status_code == 403

    def test_view_gsheet_run_redirect_handles_nonexistent_run(self, logged_in_admin, assembly_with_gsheet):
        """Test redirect endpoint handles nonexistent run ID gracefully."""
        assembly, _ = assembly_with_gsheet
        fake_task_id = uuid.uuid4()

        response = logged_in_admin.get(
            f"/assemblies/{assembly.id}/gsheet_runs/{fake_task_id}/view", follow_redirects=True
        )

        # Should show error message
        assert response.status_code == 200
        assert b"Task run not found" in response.data or b"not found" in response.data


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

    def test_cancel_gsheet_select_requires_auth(self, client, assembly_with_gsheet, postgres_session_factory):
        """Test POST to cancel endpoint requires authentication."""
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
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # POST without auth should redirect to login
        response = client.post(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/cancel")
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_cancel_gsheet_select_already_completed(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test POST to cancel endpoint with completed task shows error."""
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
        """Test GET request shows cancelled task status in UI."""
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

    def test_cancelled_task_shows_in_history_table(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test cancelled task appears in Selection Run History table."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()

        # Create a CANCELLED task
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.CANCELLED,
                task_type=SelectionTaskType.SELECT_GSHEET,
                celery_task_id="test-celery-history-id",
                log_messages=["Task cancelled"],
                error_message="Task cancelled by admin@example.com",
                created_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # GET the data page with run history table
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/data")

        # Should show cancelled status in history table
        assert response.status_code == 200
        assert b"Cancelled" in response.data
