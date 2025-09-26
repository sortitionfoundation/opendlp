"""ABOUTME: End-to-end tests for sortition-related Flask routes
ABOUTME: Tests Google Sheets loading task management routes through complete HTTP request/response cycles"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from opendlp.domain.assembly import AssemblyGSheet, SelectionRunRecord
from opendlp.domain.users import UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole
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
        assert b"Load Spreadsheet" in response.data

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
                status="running",
                task_type="load_gsheet",
                log_messages=["Task started", "Loading data"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}")

        assert response.status_code == 200
        assert b"Task Status" in response.data
        assert b"Running" in response.data
        assert b"Task started" in response.data
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
                task_type="load_gsheet",
                status="running",
            )
            uow.selection_run_records.add(record)
            uow.commit()

        # Try to access task from different assembly
        different_assembly_id = uuid.uuid4()
        response = logged_in_admin.get(f"/assemblies/{different_assembly_id}/gsheet_select/{task_id}")

        # Should redirect due to validation error
        assert response.status_code == 404

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
            assert records[0].status == "pending"
            assert "Task submitted for Google Sheets loading" in records[0].log_messages

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
