"""ABOUTME: End-to-end tests for general backoffice functionality
ABOUTME: Tests dashboard, showcase, data source selection, and data source locking"""

from tests.e2e.helpers import get_csrf_token


class TestBackofficeDashboard:
    """Test backoffice dashboard functionality."""

    def test_dashboard_loads_for_logged_in_user(self, logged_in_admin):
        """Test that dashboard page loads successfully."""
        response = logged_in_admin.get("/backoffice/dashboard")
        assert response.status_code == 200
        assert b"Dashboard" in response.data or b"Assembly" in response.data.lower()

    def test_dashboard_redirects_when_not_logged_in(self, client):
        """Test that unauthenticated users are redirected to login."""
        response = client.get("/backoffice/dashboard")
        assert response.status_code == 302
        assert "login" in response.location

    def test_dashboard_shows_existing_assemblies(self, logged_in_admin, existing_assembly):
        """Test dashboard shows existing assemblies."""
        response = logged_in_admin.get("/backoffice/dashboard")
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data

    def test_dashboard_accessible_to_regular_user(self, logged_in_user):
        """Test that regular users can view the dashboard."""
        response = logged_in_user.get("/backoffice/dashboard")
        assert response.status_code == 200


class TestBackofficeShowcase:
    """Test backoffice showcase page."""

    def test_showcase_page_loads(self, client):
        """Test that showcase page loads without authentication."""
        response = client.get("/backoffice/showcase")
        assert response.status_code == 200
        # Showcase demonstrates the design system components
        assert b"showcase" in response.data.lower() or b"component" in response.data.lower()

    def test_search_demo_empty_query(self, client):
        """Test search demo returns empty for no query."""
        response = client.get("/backoffice/showcase/search-demo")
        assert response.status_code == 200
        data = response.get_json()
        assert data == []

    def test_search_demo_with_query(self, client):
        """Test search demo returns mock results."""
        response = client.get("/backoffice/showcase/search-demo?q=alice")
        assert response.status_code == 200
        data = response.get_json()
        # Should match mock user with "alice"
        assert len(data) >= 1
        assert any("alice" in item["label"].lower() or "alice" in item["sublabel"].lower() for item in data)


class TestBackofficeAssemblyDataPage:
    """Test backoffice assembly data page functionality."""

    def test_view_assembly_data_page_loads(self, logged_in_admin, existing_assembly):
        """Test that the assembly data page loads successfully."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data")
        assert response.status_code == 200
        assert b"Data Source" in response.data or b"data" in response.data.lower()

    def test_view_assembly_data_page_with_gsheet_source(self, logged_in_admin, existing_assembly):
        """Test that the assembly data page loads with gsheet source parameter."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")
        assert response.status_code == 200
        # Should show the gsheet configuration form
        assert b"Spreadsheet URL" in response.data or b"Google" in response.data

    def test_view_assembly_data_page_with_csv_source(self, logged_in_admin, existing_assembly):
        """Test that the assembly data page loads with csv source parameter."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=csv")
        assert response.status_code == 200

    def test_view_assembly_data_page_invalid_source_ignored(self, logged_in_admin, existing_assembly):
        """Test that invalid source parameter is ignored."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=invalid")
        assert response.status_code == 200

    def test_view_assembly_data_redirects_when_not_logged_in(self, client, existing_assembly):
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/data")
        assert response.status_code == 302
        assert "login" in response.location

    def test_view_assembly_data_nonexistent_assembly(self, logged_in_admin):
        """Test accessing data page for non-existent assembly."""
        response = logged_in_admin.get("/backoffice/assembly/00000000-0000-0000-0000-000000000000/data")
        assert response.status_code == 302  # Should redirect with error


class TestBackofficeDataSourceLocking:
    """Test data source selector locking behavior."""

    def test_data_source_locked_when_gsheet_config_exists(self, logged_in_admin, assembly_with_gsheet):
        """Test that data source selector is disabled when gsheet config exists."""
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

    def test_data_source_auto_selects_gsheet_when_config_exists(self, logged_in_admin, assembly_with_gsheet):
        """Test that data source auto-selects gsheet when config exists, ignoring source param."""
        assembly, _ = assembly_with_gsheet
        # Try to access with csv source - should still show gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=csv")
        assert response.status_code == 200
        # Should show gsheet content, not csv
        assert b"Google Spreadsheet Configuration" in response.data
        # Should NOT show csv content
        assert b"Upload a CSV file" not in response.data

    def test_data_source_unlocked_when_no_config_exists(self, logged_in_admin, existing_assembly):
        """Test that data source selector is enabled when no config exists."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data")
        assert response.status_code == 200
        # Selector should NOT be disabled (no config exists)
        # Check that the x-data urlSelect attribute is present (indicates interactivity)
        assert b"urlSelect" in response.data
        # Should show standard message, not locked message
        assert b"Choose how you want to import" in response.data

    def test_data_source_unlocked_after_delete(self, logged_in_admin, assembly_with_gsheet):
        """Test that data source selector is unlocked after deleting config."""
        assembly, _ = assembly_with_gsheet
        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/data")

        # Delete the config
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/gsheet/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )
        assert response.status_code == 200

        # Selector should now be enabled (unlocked)
        assert b"urlSelect" in response.data
        # Should show standard message
        assert b"Choose how you want to import" in response.data
        # Should NOT show locked message
        assert b"locked" not in response.data.lower() or b"Data source is locked" not in response.data

    def test_gsheet_selected_shows_in_dropdown_when_locked(self, logged_in_admin, assembly_with_gsheet):
        """Test that gsheet option is selected in dropdown when config exists."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data")
        assert response.status_code == 200
        # The gsheet option should be selected
        assert b'value="gsheet" selected' in response.data or b'value="gsheet"' in response.data
