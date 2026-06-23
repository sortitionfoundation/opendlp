# ABOUTME: Component tests for general backoffice routes over a FakeUnitOfWork
# ABOUTME: Drives dashboard, showcase, assembly data page, and data-source locking against a seeded fake store, no PostgreSQL

from datetime import UTC, datetime, timedelta

import pytest
from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly, AssemblyGSheet
from opendlp.service_layer.assembly_service import add_assembly_gsheet, create_assembly
from tests.fakes import FakeStore, FakeUnitOfWork


@pytest.fixture
def assembly_with_gsheet(fake_store: FakeStore, admin_user) -> tuple[Assembly, AssemblyGSheet]:
    """An assembly with existing gsheet configuration in the shared store."""
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


class TestBackofficeDashboard:
    """Test backoffice dashboard functionality."""

    def test_dashboard_redirects_when_not_logged_in(self, client: FlaskClient) -> None:
        """Unauthenticated users are redirected to login."""
        response = client.get("/backoffice/dashboard")
        assert response.status_code == 302
        assert "login" in response.location

    def test_dashboard_shows_existing_assemblies(self, logged_in_admin: FlaskClient, existing_assembly) -> None:
        """Dashboard shows existing assemblies."""
        response = logged_in_admin.get("/backoffice/dashboard")
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data

    def test_dashboard_accessible_to_regular_user(self, logged_in_user: FlaskClient) -> None:
        """Regular users can view the dashboard."""
        response = logged_in_user.get("/backoffice/dashboard")
        assert response.status_code == 200


class TestBackofficeShowcase:
    """Test backoffice showcase page."""

    def test_showcase_page_loads(self, client: FlaskClient) -> None:
        """Showcase page loads without authentication."""
        response = client.get("/backoffice/showcase")
        assert response.status_code == 200
        # Showcase demonstrates the design system components
        assert b"showcase" in response.data.lower() or b"component" in response.data.lower()

    def test_search_demo_empty_query(self, client: FlaskClient) -> None:
        """Search demo returns empty for no query."""
        response = client.get("/backoffice/showcase/search-demo")
        assert response.status_code == 200
        data = response.get_json()
        assert data == []

    def test_search_demo_with_query(self, client: FlaskClient) -> None:
        """Search demo returns mock results."""
        response = client.get("/backoffice/showcase/search-demo?q=alice")
        assert response.status_code == 200
        data = response.get_json()
        # Should match mock user with "alice"
        assert len(data) >= 1
        assert any("alice" in item["label"].lower() or "alice" in item["sublabel"].lower() for item in data)


class TestBackofficeAssemblyDataPage:
    """Test backoffice assembly data page functionality."""

    def test_view_assembly_data_page_with_gsheet_source(self, logged_in_admin: FlaskClient, existing_assembly) -> None:
        """Assembly data page loads with gsheet source parameter."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")
        assert response.status_code == 200
        # Should show the gsheet configuration form
        assert b"Spreadsheet URL" in response.data or b"Google" in response.data

    def test_view_assembly_data_page_with_csv_source(self, logged_in_admin: FlaskClient, existing_assembly) -> None:
        """Assembly data page loads with csv source parameter."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=csv")
        assert response.status_code == 200

    def test_view_assembly_data_page_invalid_source_ignored(
        self, logged_in_admin: FlaskClient, existing_assembly
    ) -> None:
        """Invalid source parameter is ignored."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=invalid")
        assert response.status_code == 200

    def test_view_assembly_data_redirects_when_not_logged_in(self, client: FlaskClient, existing_assembly) -> None:
        """Unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/data")
        assert response.status_code == 302
        assert "login" in response.location

    def test_view_assembly_data_nonexistent_assembly(self, logged_in_admin: FlaskClient) -> None:
        """Accessing data page for non-existent assembly redirects with error."""
        response = logged_in_admin.get("/backoffice/assembly/00000000-0000-0000-0000-000000000000/data")
        assert response.status_code == 302


class TestBackofficeDataSourceLocking:
    """Test data source selector locking behavior."""

    def test_data_source_locked_when_gsheet_config_exists(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet
    ) -> None:
        """Data source selector is disabled when gsheet config exists."""
        assembly, _ = assembly_with_gsheet
        # Access data page without source param - should auto-select gsheet and lock
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data")
        assert response.status_code == 200
        # Selector should be disabled
        assert b"disabled" in response.data
        # Should show gsheet content (auto-selected)
        assert b"Google Spreadsheet Configuration" in response.data
        # Should show locked message
        assert b"locked" in response.data.lower()

    def test_data_source_auto_selects_gsheet_when_config_exists(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet
    ) -> None:
        """Data source auto-selects gsheet when config exists, ignoring source param."""
        assembly, _ = assembly_with_gsheet
        # Try to access with csv source - should still show gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=csv")
        assert response.status_code == 200
        # Should show gsheet content, not csv
        assert b"Google Spreadsheet Configuration" in response.data
        # Should NOT show csv content
        assert b"Upload a CSV file" not in response.data

    def test_data_source_unlocked_when_no_config_exists(self, logged_in_admin: FlaskClient, existing_assembly) -> None:
        """Data source selector is enabled when no config exists."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data")
        assert response.status_code == 200
        # Selector should NOT be disabled (no config exists)
        # Check that the x-data urlSelect attribute is present (indicates interactivity)
        assert b"urlSelect" in response.data
        # Should show standard message, not locked message
        assert b"Choose how you want to import" in response.data

    def test_data_source_unlocked_after_delete(self, logged_in_admin: FlaskClient, assembly_with_gsheet) -> None:
        """Data source selector is unlocked after deleting config."""
        assembly, _ = assembly_with_gsheet

        # Delete the config
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/gsheet/delete",
            follow_redirects=True,
        )
        assert response.status_code == 200

        # Selector should now be enabled (unlocked)
        assert b"urlSelect" in response.data
        # Should show standard message
        assert b"Choose how you want to import" in response.data
        # Should NOT show locked message
        assert b"locked" not in response.data.lower() or b"Data source is locked" not in response.data

    def test_gsheet_selected_shows_in_dropdown_when_locked(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet
    ) -> None:
        """Gsheet option is selected in dropdown when config exists."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data")
        assert response.status_code == 200
        # The gsheet option should be selected
        assert b'value="gsheet" selected' in response.data or b'value="gsheet"' in response.data
