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

    def test_gsheet_form_shows_default_values_in_new_mode(self, logged_in_admin, existing_assembly):
        """Test that form defaults are shown when creating new gsheet config."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")
        assert response.status_code == 200
        # Form should have default values from the WTForms form
        assert b"Respondents" in response.data  # Default for select_registrants_tab
        assert b"Categories" in response.data  # Default for select_targets_tab
        assert b"Selected" in response.data  # Default for already_selected_tab


class TestBackofficeGSheetFormSubmission:
    """Test gsheet form submission (create and edit)."""

    def test_create_gsheet_config_success(self, logged_in_admin, existing_assembly):
        """Test successfully creating a new gsheet configuration."""
        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/save",
            data={
                "csrf_token": csrf_token,
                "url": "https://docs.google.com/spreadsheets/d/1abc123/edit",
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "id",
                "check_same_address": "y",
                "generate_remaining_tab": "y",
                "check_same_address_cols_string": "address1,city,postcode",  # Required when check_same_address is enabled
                "columns_to_keep_string": "name,email",
            },
            follow_redirects=False,
        )
        # Should redirect to view mode on success
        assert response.status_code == 302
        assert "source=gsheet" in response.location

        # Follow redirect and verify success message
        response = logged_in_admin.get(response.location)
        assert response.status_code == 200
        # Should show success message and be in VIEW mode (config now exists)
        assert b"created successfully" in response.data or b"View Spreadsheet" in response.data

    def test_create_gsheet_config_validation_error_missing_url(self, logged_in_admin, existing_assembly):
        """Test validation error when creating gsheet config without URL."""
        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/save",
            data={
                "csrf_token": csrf_token,
                "url": "",  # Empty URL - should fail validation
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "id",
            },
            follow_redirects=False,
        )
        # Should return 200 (re-render form with errors), not redirect
        assert response.status_code == 200
        # Form should still be displayed (not redirected to success)
        assert b'name="url"' in response.data

    def test_create_gsheet_config_validation_error_invalid_url(self, logged_in_admin, existing_assembly):
        """Test validation error when creating gsheet config with invalid URL."""
        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/save",
            data={
                "csrf_token": csrf_token,
                "url": "https://example.com/not-a-google-sheet",  # Not a Google Sheets URL
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "id",
            },
            follow_redirects=False,
        )
        # Should return 200 (re-render form with errors)
        assert response.status_code == 200

    def test_update_gsheet_config_success(self, logged_in_admin, assembly_with_gsheet):
        """Test successfully updating an existing gsheet configuration."""
        assembly, gsheet = assembly_with_gsheet
        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/data?source=gsheet&mode=edit")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/gsheet/save",
            data={
                "csrf_token": csrf_token,
                "url": "https://docs.google.com/spreadsheets/d/updated123/edit",
                "team": "uk",
                "select_registrants_tab": "Updated Respondents",
                "select_targets_tab": "Updated Categories",
                "replace_registrants_tab": "Updated Remaining",
                "replace_targets_tab": "Updated Replacement",
                "already_selected_tab": "Updated Selected",
                "id_column": "nationbuilder_id",
                "check_same_address": "y",
                "generate_remaining_tab": "y",
                "check_same_address_cols_string": "address1,city",
                "columns_to_keep_string": "first_name,last_name,email",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        # Should show success message
        assert b"updated successfully" in response.data

    def test_update_gsheet_config_validation_error(self, logged_in_admin, assembly_with_gsheet):
        """Test validation error when updating gsheet config with invalid data."""
        assembly, gsheet = assembly_with_gsheet
        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/data?source=gsheet&mode=edit")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/gsheet/save",
            data={
                "csrf_token": csrf_token,
                "url": "",  # Empty URL - should fail validation
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "id",
            },
            follow_redirects=False,
        )
        # Should return 200 (re-render form with errors)
        assert response.status_code == 200
        # Form should still be displayed
        assert b'name="url"' in response.data

    def test_create_gsheet_shows_warning_for_empty_columns_to_keep(self, logged_in_admin, existing_assembly):
        """Test that warning is shown when columns_to_keep is empty."""
        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/save",
            data={
                "csrf_token": csrf_token,
                "url": "https://docs.google.com/spreadsheets/d/1warningtest/edit",
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "id",
                # Not enabling check_same_address to avoid validation error
                "generate_remaining_tab": "y",
                "columns_to_keep_string": "",  # Empty - should show warning
            },
            follow_redirects=False,
        )
        # Should redirect to view mode on success
        assert response.status_code == 302

        # Follow redirect and check for warning
        response = logged_in_admin.get(response.location)
        assert response.status_code == 200
        # Should show warning about empty columns_to_keep
        assert b"Warning" in response.data or b"columns to keep" in response.data.lower()
