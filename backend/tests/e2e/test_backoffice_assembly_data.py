"""ABOUTME: End-to-end tests for backoffice assembly data page
ABOUTME: Tests the assembly data page with gsheet source selection"""

from tests.e2e.helpers import get_csrf_token


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


class TestBackofficeGSheetConfigForm:
    """Test the gsheet configuration form on backoffice data page."""

    def test_gsheet_form_shows_new_mode_when_no_config_exists(self, logged_in_admin, existing_assembly):
        """Test that new gsheet form is shown when no config exists."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")
        assert response.status_code == 200
        # Should be in "new" mode - form should be editable
        assert b'name="url"' in response.data
        assert b"Save" in response.data or b"submit" in response.data.lower()

    def test_gsheet_form_contains_required_fields(self, logged_in_admin, existing_assembly):
        """Test that gsheet form contains all required fields."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")
        assert response.status_code == 200

        # URL field
        assert b'name="url"' in response.data

        # Tab name fields
        assert b"select_registrants_tab" in response.data
        assert b"select_targets_tab" in response.data

        # Options
        assert b"check_same_address" in response.data

    def test_gsheet_form_shows_view_mode_when_config_exists(self, logged_in_admin, assembly_with_gsheet):
        """Test that readonly view mode is shown when gsheet config exists (no mode param)."""
        assembly, gsheet = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=gsheet")
        assert response.status_code == 200
        # Should be in "view" mode - form fields should be readonly/disabled
        # The Edit button should be present to switch to edit mode
        assert b"Edit" in response.data or b"edit" in response.data.lower()
        # URL should be displayed (possibly as link or readonly field)
        assert b"docs.google.com/spreadsheets" in response.data

    def test_gsheet_form_shows_edit_mode_with_mode_param(self, logged_in_admin, assembly_with_gsheet):
        """Test that editable form is shown when mode=edit param is present."""
        assembly, gsheet = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=gsheet&mode=edit")
        assert response.status_code == 200
        # Should be in "edit" mode - form should be editable with save button
        assert b'name="url"' in response.data
        assert b"Save" in response.data or b"submit" in response.data.lower()
        # Should show cancel button to go back to view mode
        assert b"Cancel" in response.data or b"cancel" in response.data.lower()

    def test_gsheet_save_endpoint_exists(self, logged_in_admin, existing_assembly):
        """Test that the gsheet save endpoint responds."""
        # This will fail validation but should not 404
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/save",
            data={
                "csrf_token": get_csrf_token(
                    logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet"
                ),
            },
            follow_redirects=False,
        )
        # Should either process the form or show validation errors, not 404
        assert response.status_code in [200, 302]
