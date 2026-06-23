# ABOUTME: Component tests for the sortition gsheet Flask routes over a FakeUnitOfWork
# ABOUTME: Drives auth/permission/validation/render/redirect branches that return before any Celery dispatch

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from opendlp.adapters import database
from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.users import UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.assembly_service import add_assembly_gsheet, create_assembly
from tests.fakes import FakeUnitOfWork


@pytest.fixture(autouse=True)
def _mapped_domain_objects():
    """Seeding/cancelling run records touches SQLAlchemy state, which needs mapped classes."""
    database.start_mappers()


@pytest.fixture
def assembly_with_gsheet(fake_store, admin_user):
    """Create an assembly with an existing gsheet configuration in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Assembly with GSheet",
            created_by_user_id=admin_user.id,
            question="What should we configure?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            number_to_select=22,
        )
        detached_assembly = assembly.create_detached_copy()

    with FakeUnitOfWork(store=fake_store) as uow:
        gsheet = add_assembly_gsheet(
            uow=uow,
            assembly_id=assembly.id,
            user_id=admin_user.id,
            url="https://docs.google.com/spreadsheets/d/1234567890abcdef/edit",
            team="uk",
            select_registrants_tab="TestRespondents",
            select_targets_tab="TestCategories",
            id_column="test_id_column",
            check_same_address=True,
            generate_remaining_tab=False,
        )
        detached_gsheet = gsheet.create_detached_copy()
    return detached_assembly, detached_gsheet


def _seed_run_record(fake_store, assembly_id, task_id, status, task_type, **kwargs):
    """Seed a SelectionRunRecord into the shared store via the real repo."""
    with FakeUnitOfWork(store=fake_store) as uow:
        record = SelectionRunRecord(
            assembly_id=assembly_id,
            task_id=task_id,
            status=status,
            task_type=task_type,
            **kwargs,
        )
        uow.selection_run_records.add(record)
        uow.commit()


class TestSortitionRoutes:
    """Auth/permission/validation/render branches for the gsheet selection routes."""

    def test_select_assembly_gsheet_get_requires_auth(self, client, assembly_with_gsheet):
        """GET request redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.get(f"/assemblies/{assembly.id}/gsheet_select")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_select_assembly_gsheet_with_run_shows_status(self, fake_store, logged_in_admin, assembly_with_gsheet):
        """GET request with run_id shows task status."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.LOAD_GSHEET,
            log_messages=["Task started", "Loading data"],
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}")

        assert response.status_code == 200
        assert b"Current status: running" in response.data
        assert b"Loading data" in response.data

    def test_select_assembly_gsheet_with_run_validates_assembly(self, fake_store, logged_in_admin, existing_assembly):
        """GET request with run_id for wrong assembly returns 404."""
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            existing_assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.LOAD_GSHEET,
        )

        different_assembly_id = uuid.uuid4()
        response = logged_in_admin.get(f"/assemblies/{different_assembly_id}/gsheet_select/{task_id}")

        assert response.status_code == 404

    def test_select_assembly_gsheet_with_none_to_select(self, fake_store, admin_user, logged_in_admin):
        """POST request for assembly with zero to select redirects."""
        with FakeUnitOfWork(store=fake_store) as uow:
            assembly = create_assembly(
                uow=uow,
                title="None Assembly",
                created_by_user_id=admin_user.id,
                question="What should we configure?",
                first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
                number_to_select=None,
            )
            assembly_id = assembly.id

        with FakeUnitOfWork(store=fake_store) as uow:
            add_assembly_gsheet(
                uow=uow,
                assembly_id=assembly_id,
                user_id=admin_user.id,
                url="https://docs.google.com/spreadsheets/d/1234567890abcdef/edit",
                team="uk",
            )

        response = logged_in_admin.post(f"/assemblies/{assembly_id}/gsheet_select")

        assert response.status_code == 302

    def test_gsheet_load_requires_auth(self, client, assembly_with_gsheet):
        """POST request redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.post(f"/assemblies/{assembly.id}/gsheet_load")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_gsheet_load_requires_management_permission(self, logged_in_user, assembly_with_gsheet):
        """POST request fails for user without management permission."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_user.post(f"/assemblies/{assembly.id}/gsheet_load")

        assert response.status_code == 403

    def test_gsheet_load_handles_missing_gsheet(self, fake_store, logged_in_admin, admin_user):
        """POST request handles assembly with no gsheet configuration."""
        with FakeUnitOfWork(store=fake_store) as uow:
            assembly = create_assembly(
                uow=uow,
                title="Assembly No GSheet",
                created_by_user_id=admin_user.id,
                question="What should we configure?",
                first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            )
            assembly_id = assembly.id

        response = logged_in_admin.post(f"/assemblies/{assembly_id}/gsheet_load")

        assert response.status_code == 302
        assert f"/assemblies/{assembly_id}/gsheet_select" in response.headers["Location"]

    def test_gsheet_load_handles_nonexistent_assembly(self, logged_in_admin):
        """POST request handles nonexistent assembly."""
        non_existent_id = uuid.uuid4()
        response = logged_in_admin.post(f"/assemblies/{non_existent_id}/gsheet_load")

        assert response.status_code == 404

    def test_progress_endpoint_returns_fragment_for_running_task(
        self, fake_store, logged_in_admin, assembly_with_gsheet
    ):
        """Progress endpoint returns HTML fragment with HTMX attributes for running task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.LOAD_GSHEET,
            log_messages=["Task started", "Processing data"],
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/progress")

        assert response.status_code == 200
        assert b"Current status: running" in response.data
        assert b"Task started" in response.data
        assert b"Processing data" in response.data
        assert b"hx-get" in response.data
        assert b"hx-trigger" in response.data
        assert b"hx-swap" in response.data
        assert b"every 1s" in response.data

    def test_progress_endpoint_returns_fragment_for_pending_task(
        self, fake_store, logged_in_admin, assembly_with_gsheet
    ):
        """Progress endpoint returns HTML fragment with HTMX attributes for pending task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.PENDING,
            SelectionTaskType.SELECT_GSHEET,
            log_messages=["Task queued"],
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/progress")

        assert response.status_code == 200
        assert b"Current status: pending" in response.data
        assert b"hx-get" in response.data
        assert b"hx-trigger" in response.data
        assert b"every 1s" in response.data

    def test_progress_endpoint_returns_fragment_without_polling_for_completed_task(
        self, fake_store, logged_in_admin, assembly_with_gsheet
    ):
        """Progress endpoint returns fragment WITHOUT HTMX polling for completed task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.COMPLETED,
            SelectionTaskType.LOAD_GSHEET,
            log_messages=["Task completed successfully"],
            completed_at=datetime.now(UTC),
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/progress")

        assert response.status_code == 200
        assert b"Completed" in response.data
        assert b"Task completed successfully" in response.data
        assert b"hx-trigger" not in response.data
        assert b"every 1s" not in response.data

    def test_progress_endpoint_returns_fragment_without_polling_for_failed_task(
        self, fake_store, logged_in_admin, assembly_with_gsheet
    ):
        """Progress endpoint returns fragment WITHOUT HTMX polling for failed task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.FAILED,
            SelectionTaskType.SELECT_GSHEET,
            log_messages=["Task started", "Error occurred"],
            error_message="Something went wrong",
            completed_at=datetime.now(UTC),
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/progress")

        assert response.status_code == 200
        assert b"Error Details" in response.data
        assert b"Something went wrong" in response.data
        assert b"hx-trigger" not in response.data
        assert b"every 1s" not in response.data

    def test_progress_endpoint_requires_auth(self, fake_store, client, assembly_with_gsheet):
        """Progress endpoint redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.LOAD_GSHEET,
        )

        response = client.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/progress")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_progress_endpoint_validates_run_belongs_to_assembly(
        self, fake_store, logged_in_admin, assembly_with_gsheet
    ):
        """Progress endpoint validates that run_id belongs to the correct assembly."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.LOAD_GSHEET,
        )

        different_assembly_id = uuid.uuid4()
        response = logged_in_admin.get(f"/assemblies/{different_assembly_id}/gsheet_select/{task_id}/progress")

        assert response.status_code == 404

    def test_progress_endpoint_handles_nonexistent_run(self, logged_in_admin, assembly_with_gsheet):
        """Progress endpoint handles request for nonexistent run_id."""
        assembly, _ = assembly_with_gsheet
        non_existent_task_id = uuid.uuid4()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_select/{non_existent_task_id}/progress")

        assert response.status_code == 404

    def test_progress_endpoint_requires_management_permission(self, fake_store, logged_in_user, assembly_with_gsheet):
        """Progress endpoint requires assembly management permission."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.LOAD_GSHEET,
        )

        response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/progress")

        assert response.status_code == 403


class TestReplacementRoutes:
    """Auth/permission/validation/render branches for the replacement selection routes."""

    def test_replace_assembly_gsheet_get_requires_auth(self, client, assembly_with_gsheet):
        """GET request to replacement page redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.get(f"/assemblies/{assembly.id}/gsheet_replace")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_replace_assembly_gsheet_with_run_shows_status(self, fake_store, logged_in_admin, assembly_with_gsheet):
        """GET request with run_id shows task status."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
            log_messages=["Task started", "Loading replacement data"],
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_replace/{task_id}")

        assert response.status_code == 200
        assert b"Current status: running" in response.data
        assert b"Task started" in response.data
        assert b"Loading replacement data" in response.data

    def test_replace_assembly_gsheet_with_run_validates_assembly(self, fake_store, logged_in_admin, existing_assembly):
        """GET request with run_id for wrong assembly returns 404."""
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            existing_assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
        )

        different_assembly_id = uuid.uuid4()
        response = logged_in_admin.get(f"/assemblies/{different_assembly_id}/gsheet_replace/{task_id}")

        assert response.status_code == 404

    def test_gsheet_replace_load_requires_auth(self, client, assembly_with_gsheet):
        """POST request to replacement load redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.post(f"/assemblies/{assembly.id}/gsheet_replace_load")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_gsheet_replace_load_requires_management_permission(self, logged_in_user, assembly_with_gsheet):
        """POST request to replacement load fails for user without management permission."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_user.post(f"/assemblies/{assembly.id}/gsheet_replace_load")

        assert response.status_code == 403

    def test_gsheet_replace_load_handles_missing_gsheet(self, fake_store, logged_in_admin, admin_user):
        """POST request to replacement load handles assembly with no gsheet configuration."""
        with FakeUnitOfWork(store=fake_store) as uow:
            assembly = create_assembly(
                uow=uow,
                title="Assembly No GSheet",
                created_by_user_id=admin_user.id,
                question="What should we configure?",
                first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            )
            assembly_id = assembly.id

        response = logged_in_admin.post(f"/assemblies/{assembly_id}/gsheet_replace_load")

        assert response.status_code == 302
        assert f"/assemblies/{assembly_id}/gsheet_replace" in response.headers["Location"]

    def test_start_gsheet_replace_requires_number(self, logged_in_admin, assembly_with_gsheet):
        """POST request to start replacement requires number_to_select."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_replace", data={})

        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_replace" in response.headers["Location"]

    def test_start_gsheet_replace_validates_number(self, logged_in_admin, assembly_with_gsheet):
        """POST request to start replacement validates number_to_select is positive."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet_replace", data={"number_to_select": "0"})

        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_replace" in response.headers["Location"]

    def test_start_gsheet_replace_requires_auth(self, client, assembly_with_gsheet):
        """POST request to start replacement redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.post(f"/assemblies/{assembly.id}/gsheet_replace", data={"number_to_select": "10"})

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_start_gsheet_replace_requires_management_permission(self, logged_in_user, assembly_with_gsheet):
        """POST request to start replacement fails for user without management permission."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_user.post(f"/assemblies/{assembly.id}/gsheet_replace", data={"number_to_select": "10"})

        assert response.status_code == 403

    def test_gsheet_replace_progress_returns_fragment_for_running_task(
        self, fake_store, logged_in_admin, assembly_with_gsheet
    ):
        """Replacement progress endpoint returns HTML fragment with HTMX attributes for running task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
            log_messages=["Task started", "Processing replacement data"],
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_replace/{task_id}/progress")

        assert response.status_code == 200
        assert b"Current status: running" in response.data
        assert b"Task started" in response.data
        assert b"Processing replacement data" in response.data
        assert b"hx-get" in response.data
        assert b"hx-trigger" in response.data
        assert b"hx-swap" in response.data
        assert b"every 1s" in response.data

    def test_gsheet_replace_progress_returns_fragment_without_polling_for_completed_task(
        self, fake_store, logged_in_admin, assembly_with_gsheet
    ):
        """Replacement progress endpoint returns fragment WITHOUT HTMX polling for completed task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.COMPLETED,
            SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
            log_messages=["Task completed successfully"],
            completed_at=datetime.now(UTC),
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_replace/{task_id}/progress")

        assert response.status_code == 200
        assert b"Completed" in response.data
        assert b"Task completed successfully" in response.data
        assert b"hx-trigger" not in response.data
        assert b"every 1s" not in response.data

    def test_gsheet_replace_progress_requires_auth(self, fake_store, client, assembly_with_gsheet):
        """Replacement progress endpoint redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
        )

        response = client.get(f"/assemblies/{assembly.id}/gsheet_replace/{task_id}/progress")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_gsheet_replace_progress_validates_run_belongs_to_assembly(
        self, fake_store, logged_in_admin, assembly_with_gsheet
    ):
        """Replacement progress endpoint validates that run_id belongs to the correct assembly."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
        )

        different_assembly_id = uuid.uuid4()
        response = logged_in_admin.get(f"/assemblies/{different_assembly_id}/gsheet_replace/{task_id}/progress")

        assert response.status_code == 404

    def test_gsheet_replace_progress_handles_nonexistent_run(self, logged_in_admin, assembly_with_gsheet):
        """Replacement progress endpoint handles request for nonexistent run_id."""
        assembly, _ = assembly_with_gsheet
        non_existent_task_id = uuid.uuid4()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_replace/{non_existent_task_id}/progress")

        assert response.status_code == 404

    def test_gsheet_replace_progress_requires_management_permission(
        self, fake_store, logged_in_user, assembly_with_gsheet
    ):
        """Replacement progress endpoint requires assembly management permission."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
        )

        response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet_replace/{task_id}/progress")

        assert response.status_code == 403


class TestManageTabsRoutes:
    """Auth/permission/render branches for the tab management routes."""

    def test_manage_tabs_get_requires_auth(self, client, assembly_with_gsheet):
        """GET request to manage tabs page redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.get(f"/assemblies/{assembly.id}/gsheet_manage_tabs")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_manage_tabs_get_requires_management_permission(self, logged_in_user, assembly_with_gsheet):
        """GET request to manage tabs page fails for user without management permission."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet_manage_tabs")

        assert response.status_code == 403

    def test_list_tabs_requires_auth(self, client, assembly_with_gsheet):
        """POST request to list tabs redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.post(f"/assemblies/{assembly.id}/gsheet_list_tabs")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_list_tabs_requires_management_permission(self, logged_in_user, assembly_with_gsheet):
        """POST request to list tabs fails for user without management permission."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_user.post(f"/assemblies/{assembly.id}/gsheet_list_tabs")

        assert response.status_code == 403

    def test_delete_tabs_requires_auth(self, client, assembly_with_gsheet):
        """POST request to delete tabs redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.post(f"/assemblies/{assembly.id}/gsheet_delete_tabs")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_delete_tabs_requires_management_permission(self, logged_in_user, assembly_with_gsheet):
        """POST request to delete tabs fails for user without management permission."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_user.post(f"/assemblies/{assembly.id}/gsheet_delete_tabs")

        assert response.status_code == 403

    def test_manage_tabs_with_run_shows_status(self, fake_store, logged_in_admin, assembly_with_gsheet):
        """GET request with run_id shows task status."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.COMPLETED,
            SelectionTaskType.DELETE_OLD_TABS,
            log_messages=["Task started", "Found 3 old output tab(s) that can be deleted"],
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_manage_tabs/{task_id}")

        assert response.status_code == 200
        assert b"Task Status" in response.data or b"status" in response.data.lower()
        assert b"Completed" in response.data
        assert b"Found 3 old output tab(s)" in response.data

    def test_manage_tabs_progress_returns_fragment_for_running_task(
        self, fake_store, logged_in_admin, assembly_with_gsheet
    ):
        """Progress endpoint returns HTML fragment with HTMX attributes for running tab management task."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.DELETE_OLD_TABS,
            log_messages=["Task started", "Listing old tabs"],
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_manage_tabs/{task_id}/progress")

        assert response.status_code == 200
        assert b"Task Status" in response.data or b"status" in response.data.lower()
        assert b"Task in Progress" in response.data
        assert b"Listing old tabs" in response.data
        assert b"hx-get" in response.data
        assert b"hx-trigger" in response.data
        assert b"every 1s" in response.data

    def test_manage_tabs_progress_requires_auth(self, fake_store, client, assembly_with_gsheet):
        """Progress endpoint redirects when not authenticated."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.DELETE_OLD_TABS,
        )

        response = client.get(f"/assemblies/{assembly.id}/gsheet_manage_tabs/{task_id}/progress")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_manage_tabs_progress_requires_management_permission(
        self, fake_store, logged_in_user, assembly_with_gsheet
    ):
        """Progress endpoint requires assembly management permission."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.DELETE_OLD_TABS,
        )

        response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet_manage_tabs/{task_id}/progress")

        assert response.status_code == 403


class TestSelectionRunHistory:
    """Render/redirect branches for selection run history and run navigation."""

    def test_view_assembly_data_shows_run_history(self, fake_store, logged_in_admin, assembly_with_gsheet):
        """Assembly data page shows selection run history table."""
        assembly, _ = assembly_with_gsheet
        _seed_run_record(
            fake_store,
            assembly.id,
            uuid.uuid4(),
            SelectionRunStatus.COMPLETED,
            SelectionTaskType.SELECT_GSHEET,
            log_messages=["Selection completed"],
            created_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            comment="Initial selection",
        )
        _seed_run_record(
            fake_store,
            assembly.id,
            uuid.uuid4(),
            SelectionRunStatus.FAILED,
            SelectionTaskType.LOAD_GSHEET,
            log_messages=["Load failed"],
            created_at=datetime.now(UTC) - timedelta(hours=1),
            error_message="Connection error",
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/data")

        assert response.status_code == 200
        assert b"Selection Run History" in response.data
        assert b"Showing 1 to 2 of 2 runs" in response.data
        assert b"Completed" in response.data
        assert b"Failed" in response.data
        assert b"Select google spreadsheet" in response.data
        assert b"Load google spreadsheet" in response.data
        assert b"Initial selection" in response.data

    def test_view_assembly_data_empty_history(self, logged_in_admin, assembly_with_gsheet):
        """Empty state message appears when no runs exist."""
        assembly, _ = assembly_with_gsheet

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/data")

        assert response.status_code == 200
        assert b"Selection Run History" in response.data
        assert b"No selection runs have been performed yet" in response.data

    def test_view_gsheet_run_redirect_routes_select_tasks(self, fake_store, logged_in_admin, assembly_with_gsheet):
        """Redirect endpoint routes SELECT task types correctly."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.COMPLETED,
            SelectionTaskType.LOAD_GSHEET,
            log_messages=["Loaded"],
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_runs/{task_id}/view", follow_redirects=False)

        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_select/{task_id}" in response.headers["Location"]

    def test_view_gsheet_run_redirect_routes_replace_tasks(self, fake_store, logged_in_admin, assembly_with_gsheet):
        """Redirect endpoint routes REPLACE task types correctly."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.COMPLETED,
            SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
            log_messages=["Selected replacements"],
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_runs/{task_id}/view", follow_redirects=False)

        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_replace/{task_id}" in response.headers["Location"]

    def test_view_gsheet_run_redirect_routes_tabs_tasks(self, fake_store, logged_in_admin, assembly_with_gsheet):
        """Redirect endpoint routes tab management task types correctly."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.COMPLETED,
            SelectionTaskType.DELETE_OLD_TABS,
            log_messages=["Deleted tabs"],
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet_runs/{task_id}/view", follow_redirects=False)

        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/gsheet_manage_tabs/{task_id}" in response.headers["Location"]

    def test_view_gsheet_run_redirect_validates_assembly_ownership(
        self, fake_store, logged_in_admin, assembly_with_gsheet
    ):
        """Redirect endpoint validates run belongs to assembly."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.COMPLETED,
            SelectionTaskType.SELECT_GSHEET,
            log_messages=["Done"],
        )

        wrong_assembly_id = uuid.uuid4()
        response = logged_in_admin.get(
            f"/assemblies/{wrong_assembly_id}/gsheet_runs/{task_id}/view", follow_redirects=True
        )

        assert response.status_code in [302, 404]
        if response.status_code == 302:
            assert b"Invalid task ID for this assembly" in response.data or b"not found" in response.data

    def test_view_gsheet_run_redirect_requires_auth(self, fake_store, client, assembly_with_gsheet):
        """Redirect endpoint requires authentication."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.COMPLETED,
            SelectionTaskType.SELECT_GSHEET,
            log_messages=["Done"],
        )

        response = client.get(f"/assemblies/{assembly.id}/gsheet_runs/{task_id}/view")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_view_gsheet_run_redirect_requires_permissions(self, fake_store, logged_in_user, assembly_with_gsheet):
        """Redirect endpoint requires assembly management permissions."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.COMPLETED,
            SelectionTaskType.SELECT_GSHEET,
            log_messages=["Done"],
        )

        response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet_runs/{task_id}/view")

        assert response.status_code == 403

    def test_view_gsheet_run_redirect_handles_nonexistent_run(self, logged_in_admin, assembly_with_gsheet):
        """Redirect endpoint handles nonexistent run ID gracefully."""
        assembly, _ = assembly_with_gsheet
        fake_task_id = uuid.uuid4()

        response = logged_in_admin.get(
            f"/assemblies/{assembly.id}/gsheet_runs/{fake_task_id}/view", follow_redirects=True
        )

        assert response.status_code == 200
        assert b"Task run not found" in response.data or b"not found" in response.data


class TestCancelTaskRoutes:
    """Auth/guard/render branches for task cancellation routes (no Celery revoke)."""

    def test_cancel_gsheet_select_requires_auth(self, fake_store, client, assembly_with_gsheet):
        """POST to cancel endpoint requires authentication."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.RUNNING,
            SelectionTaskType.SELECT_GSHEET,
            celery_task_id="test-celery-id",
        )

        response = client.post(f"/assemblies/{assembly.id}/gsheet_select/{task_id}/cancel")
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_cancelled_task_shows_in_history_table(self, fake_store, logged_in_admin, assembly_with_gsheet):
        """Cancelled task appears in Selection Run History table."""
        assembly, _ = assembly_with_gsheet
        task_id = uuid.uuid4()
        _seed_run_record(
            fake_store,
            assembly.id,
            task_id,
            SelectionRunStatus.CANCELLED,
            SelectionTaskType.SELECT_GSHEET,
            celery_task_id="test-celery-history-id",
            log_messages=["Task cancelled"],
            error_message="Task cancelled by admin@example.com",
            created_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/data")

        assert response.status_code == 200
        assert b"Cancelled" in response.data


class TestSortitionRoutesWithAssemblyRole:
    """Assembly-role permission rendering over the fake store."""

    @pytest.fixture
    def assembly_managed_by_user(self, fake_store, regular_user, assembly_with_gsheet):
        """Give the regular user an assembly manager role on the gsheet assembly."""
        assembly, _ = assembly_with_gsheet
        with FakeUnitOfWork(store=fake_store) as uow:
            user = uow.users.get(regular_user.id)
            role = UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)
            user.assembly_roles.append(role)
            uow.commit()
        return assembly.id

    def test_assembly_manager_can_view_manage_tabs(self, logged_in_user, assembly_managed_by_user):
        """User with assembly manager role can view the manage-tabs page."""
        assembly_id = assembly_managed_by_user
        response = logged_in_user.get(f"/assemblies/{assembly_id}/gsheet_manage_tabs")

        assert response.status_code == 200
        assert b"List Old Tabs" in response.data
