# ABOUTME: Component tests for the gsheets blueprint over a FakeUnitOfWork
# ABOUTME: Drives the real gsheet routes for pre-dispatch validation, legacy redirects, and no-task render

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from opendlp.adapters import database
from opendlp.service_layer.assembly_service import add_assembly_gsheet, create_assembly
from tests.fakes import FakeUnitOfWork


@pytest.fixture(autouse=True)
def _mapped_domain_objects():
    """Selection page rendering calls SQLAlchemy flag_modified, which needs mapped classes."""
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


class TestReplacementLegacyRoutes:
    """Test the legacy replacement redirect routes."""

    def test_view_assembly_replacement_redirects_with_modal_open(self, logged_in_admin, assembly_with_gsheet):
        """Test that /replacement redirects to selection page with replacement_modal=open."""
        assembly, _gsheet = assembly_with_gsheet
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/replacement",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "replacement_modal=open" in response.location

    def test_view_assembly_replacement_with_run_redirects(self, logged_in_admin, assembly_with_gsheet):
        """Test that /replacement/<run_id> redirects with current_replacement param."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/replacement/{run_id}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"current_replacement={run_id}" in response.location

    def test_view_assembly_replacement_with_run_preserves_min_max(self, logged_in_admin, assembly_with_gsheet):
        """Test that /replacement/<run_id> preserves min_select and max_select params."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/replacement/{run_id}?min_select=5&max_select=20",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "min_select=5" in response.location
        assert "max_select=20" in response.location


class TestStartReplacementRunValidation:
    """Test number_to_select validation in start_replacement_run before task dispatch."""

    def test_start_replacement_run_missing_number_to_select(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint flashes error when number_to_select is missing."""
        assembly, _gsheet = assembly_with_gsheet

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/replacement/run",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "replacement" in response.location

    def test_start_replacement_run_zero_number_to_select(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint rejects zero number_to_select."""
        assembly, _gsheet = assembly_with_gsheet

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/replacement/run",
            data={"number_to_select": "0"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "replacement" in response.location

    def test_start_replacement_run_invalid_number_to_select(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint rejects non-integer number_to_select."""
        assembly, _gsheet = assembly_with_gsheet

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/replacement/run",
            data={"number_to_select": "abc"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "replacement" in response.location

    def test_start_replacement_run_negative_number_to_select(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint rejects negative number_to_select."""
        assembly, _gsheet = assembly_with_gsheet

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/replacement/run",
            data={"number_to_select": "-3"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "replacement" in response.location


class TestSelectionPageInvalidParams:
    """Test that invalid task params are ignored and the selection page loads normally."""

    def test_selection_page_with_invalid_manage_tabs_param_loads_normally(self, logged_in_admin, assembly_with_gsheet):
        """Test that invalid manage_tabs param is ignored and page loads normally."""
        assembly, _gsheet = assembly_with_gsheet

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection?current_manage_tabs=not-a-uuid")
        assert response.status_code == 200
        assert b"manage-tabs-progress-modal" not in response.data

    def test_selection_page_with_invalid_replacement_param_loads_normally(self, logged_in_admin, assembly_with_gsheet):
        """Test that invalid replacement param is ignored and page loads normally."""
        assembly, _gsheet = assembly_with_gsheet

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection?current_replacement=not-a-uuid")
        assert response.status_code == 200
        assert b"replacement-modal" not in response.data


class TestSelectionPageViewRunningButton:
    """When no selection task is active, the Initial Selection card footer shows the run buttons."""

    def test_gsheet_shows_run_buttons_when_no_active_task(self, logged_in_admin, assembly_with_gsheet):
        """Test that the run buttons render when there is no active task."""
        assembly, _gsheet = assembly_with_gsheet

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"Check Spreadsheet" in response.data
        assert b"Run Test Selection" in response.data
        assert b"Run Selection" in response.data
        assert b"View Running Selection" not in response.data
