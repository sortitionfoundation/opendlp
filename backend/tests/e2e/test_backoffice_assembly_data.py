"""ABOUTME: End-to-end tests for backoffice assembly data page
ABOUTME: Tests the assembly data page with gsheet source selection"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from opendlp.service_layer.exceptions import InsufficientPermissions, NotFoundError
from opendlp.service_layer.sortition import InvalidSelection
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


class TestBackofficeAssemblyDetails:
    """Test backoffice assembly details page."""

    def test_view_assembly_details_page_loads(self, logged_in_admin, existing_assembly):
        """Test that assembly details page loads successfully."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}")
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data

    def test_view_assembly_redirects_when_not_logged_in(self, client, existing_assembly):
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}")
        assert response.status_code == 302
        assert "login" in response.location

    def test_view_nonexistent_assembly_redirects(self, logged_in_admin):
        """Test that accessing non-existent assembly redirects with error."""
        response = logged_in_admin.get("/backoffice/assembly/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 302  # Should redirect to dashboard with error


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


class TestBackofficeAssemblyMembers:
    """Test backoffice assembly members page."""

    def test_members_page_loads(self, logged_in_admin, existing_assembly):
        """Test that the members page loads successfully."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/members")
        assert response.status_code == 200
        assert b"Members" in response.data or b"Team" in response.data

    def test_members_page_redirects_when_not_logged_in(self, client, existing_assembly):
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/members")
        assert response.status_code == 302
        assert "login" in response.location

    def test_members_search_returns_json(self, logged_in_admin, existing_assembly):
        """Test that members search endpoint returns JSON."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=test")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)


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
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=gsheet")
        assert response.status_code == 200
        # Should be in "view" mode - form fields should be readonly/disabled
        # The Edit button should be present to switch to edit mode
        assert b"Edit" in response.data or b"edit" in response.data.lower()
        # URL should be displayed (possibly as link or readonly field)
        assert b"docs.google.com/spreadsheets" in response.data

    def test_gsheet_form_shows_edit_mode_with_mode_param(self, logged_in_admin, assembly_with_gsheet):
        """Test that editable form is shown when mode=edit param is present."""
        assembly, _ = assembly_with_gsheet
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
        assembly, _ = assembly_with_gsheet
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
        assembly, _ = assembly_with_gsheet
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


class TestBackofficeGSheetDelete:
    """Test gsheet configuration deletion."""

    def test_delete_gsheet_config_success(self, logged_in_admin, assembly_with_gsheet):
        """Test successfully deleting a gsheet configuration."""
        assembly, _ = assembly_with_gsheet
        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/data?source=gsheet")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/gsheet/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        # Should redirect to data page on success (without source param - selector unlocked)
        assert response.status_code == 302
        assert "/data" in response.location

        # Follow redirect and verify success message
        response = logged_in_admin.get(response.location)
        assert response.status_code == 200
        assert b"removed successfully" in response.data

        # Selector should now be unlocked (no config exists)
        assert b"urlSelect" in response.data

    def test_delete_gsheet_config_not_found(self, logged_in_admin, existing_assembly):
        """Test deleting a non-existent gsheet configuration."""
        # Get CSRF token from new gsheet form
        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        # Should redirect with error (without source param)
        assert response.status_code == 302
        assert "/data" in response.location

        # Follow redirect and verify error message
        response = logged_in_admin.get(response.location)
        assert response.status_code == 200
        assert b"not found" in response.data

    def test_delete_button_shown_in_view_mode(self, logged_in_admin, assembly_with_gsheet):
        """Test that delete button is shown in VIEW mode when config exists."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=gsheet")
        assert response.status_code == 200
        # Should show Delete button
        assert b"Delete" in response.data
        # Should have form action pointing to delete endpoint
        assert b"gsheet/delete" in response.data

    def test_delete_button_shown_in_edit_mode(self, logged_in_admin, assembly_with_gsheet):
        """Test that delete button is shown in EDIT mode when config exists."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=gsheet&mode=edit")
        assert response.status_code == 200
        # Should show Delete Configuration button
        assert b"Delete" in response.data
        # Should have form action pointing to delete endpoint
        assert b"gsheet/delete" in response.data

    def test_delete_button_not_shown_in_new_mode(self, logged_in_admin, existing_assembly):
        """Test that delete button is NOT shown in NEW mode when no config exists."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")
        assert response.status_code == 200
        # Should NOT show delete button (no config to delete)
        assert b"gsheet/delete" not in response.data


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


class TestBackofficeSelectionTab:
    """Test the selection tab routes for backoffice."""

    def test_selection_page_loads_without_gsheet_config(self, logged_in_admin, existing_assembly):
        """Test that selection page loads and shows configure message when no gsheet config."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/selection")
        assert response.status_code == 200
        # Should show message about configuring gsheet first
        assert b"configure" in response.data.lower() or b"Google Spreadsheet" in response.data

    def test_selection_page_loads_with_gsheet_config(self, logged_in_admin, assembly_with_gsheet):
        """Test that selection page loads when gsheet is configured."""
        assembly, _gsheet = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")
        assert response.status_code == 200
        # Should show selection interface with gsheet configured
        assert b"Selection" in response.data

    def test_selection_page_redirects_when_not_logged_in(self, client, existing_assembly):
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/selection")
        assert response.status_code == 302
        assert "login" in response.location

    def test_selection_load_endpoint_starts_task(self, logged_in_admin, assembly_with_gsheet):
        """Test that load endpoint starts a gsheet load task and redirects to run page."""

        assembly, _gsheet = assembly_with_gsheet
        mock_task_id = "12345678-1234-1234-1234-123456789012"

        with patch(
            "opendlp.entrypoints.blueprints.backoffice.start_gsheet_load_task",
            return_value=mock_task_id,
        ) as mock_start_load:
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/selection/load",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

            # Should redirect to selection page with run_id
            assert response.status_code == 302
            assert "selection" in response.location
            assert mock_task_id in response.location
            mock_start_load.assert_called_once()

    def test_selection_run_endpoint_starts_task(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint starts a gsheet select task and redirects to run page."""

        assembly, _gsheet = assembly_with_gsheet
        mock_task_id = "12345678-1234-1234-1234-123456789012"

        with patch(
            "opendlp.entrypoints.blueprints.backoffice.start_gsheet_select_task",
            return_value=mock_task_id,
        ) as mock_start_select:
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/selection/run",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

            # Should redirect to selection page with run_id
            assert response.status_code == 302
            assert "selection" in response.location
            assert mock_task_id in response.location
            mock_start_select.assert_called_once()

    def test_selection_run_test_mode_endpoint(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint with test=1 passes test_selection=True."""

        assembly, _gsheet = assembly_with_gsheet
        mock_task_id = "12345678-1234-1234-1234-123456789012"

        with patch(
            "opendlp.entrypoints.blueprints.backoffice.start_gsheet_select_task",
            return_value=mock_task_id,
        ) as mock_start_select:
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/selection/run?test=1",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

            assert response.status_code == 302
            # Verify test_selection=True was passed
            call_args = mock_start_select.call_args
            assert call_args[1].get("test_selection") is True or call_args[0][3] is True

    def test_selection_progress_endpoint_returns_html(self, logged_in_admin, assembly_with_gsheet):
        """Test that progress endpoint returns HTML fragment with HTMX attributes."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_run_record = MagicMock()
        mock_run_record.status.value = "running"
        mock_run_record.error_message = None
        mock_run_record.completed_at = None
        mock_run_record.assembly_id = assembly.id
        mock_run_record.has_finished = False
        mock_run_record.is_running = True
        mock_run_record.is_pending = False
        mock_run_record.is_completed = False
        mock_run_record.is_failed = False
        mock_run_record.is_cancelled = False
        mock_run_record.task_type_verbose = "Load Google Spreadsheet"
        mock_run_record.log_messages = ["Loading data...", "Processing..."]

        mock_result = MagicMock()
        mock_result.run_record = mock_run_record
        mock_result.log_messages = ["Loading data...", "Processing..."]
        mock_result.run_report = None

        with (
            patch("opendlp.entrypoints.blueprints.backoffice.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice.get_selection_run_status",
                return_value=mock_result,
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/{run_id}/progress")

            assert response.status_code == 200
            assert b"hx-get" in response.data
            assert b"hx-trigger" in response.data
            assert b"Loading data..." in response.data
            assert b"Processing..." in response.data

    def test_selection_cancel_endpoint_cancels_task(self, logged_in_admin, assembly_with_gsheet):
        """Test that cancel endpoint cancels the task and redirects."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        with patch("opendlp.entrypoints.blueprints.backoffice.cancel_task") as mock_cancel:
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/selection/{run_id}/cancel",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

            # Should redirect to selection page with run_id
            assert response.status_code == 302
            assert "selection" in response.location
            mock_cancel.assert_called_once()

    def test_selection_load_handles_not_found_error(self, logged_in_admin, assembly_with_gsheet):
        """Test that load endpoint handles NotFoundError gracefully."""

        assembly, _gsheet = assembly_with_gsheet

        with patch(
            "opendlp.entrypoints.blueprints.backoffice.start_gsheet_load_task",
            side_effect=NotFoundError("Gsheet config not found"),
        ):
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/selection/load",
                data={"csrf_token": csrf_token},
                follow_redirects=True,
            )

            # Should redirect back to selection page with error flash
            assert response.status_code == 200
            assert b"configure" in response.data.lower() or b"Google Spreadsheet" in response.data

    def test_selection_with_run_page_redirects_to_query_param(self, logged_in_admin, assembly_with_gsheet):
        """Test that legacy /selection/<run_id> URL redirects to query param version."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        # The legacy URL should redirect to the query parameter version
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/{run_id}")
        assert response.status_code == 302
        assert f"current_selection={run_id}" in response.location

    def test_selection_with_current_selection_param_loads(self, logged_in_admin, assembly_with_gsheet):
        """Test that selection page with current_selection query param loads successfully."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        # Create mock result object
        mock_run_record = MagicMock()
        mock_run_record.status.value = "running"
        mock_run_record.error_message = None
        mock_run_record.completed_at = None
        mock_run_record.assembly_id = assembly.id
        mock_run_record.has_finished = False

        mock_result = MagicMock()
        mock_result.run_record = mock_run_record
        mock_result.log_messages = ["Loading data..."]
        mock_result.run_report = None

        with (
            patch("opendlp.entrypoints.blueprints.backoffice.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice.get_selection_run_status",
                return_value=mock_result,
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection?current_selection={run_id}")
            assert response.status_code == 200
            assert b"Selection" in response.data

    def test_selection_with_run_not_found(self, logged_in_admin, assembly_with_gsheet):
        """Test selection with run page handles NotFoundError."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.backoffice.check_and_update_task_health",
            side_effect=NotFoundError("Task not found"),
        ):
            response = logged_in_admin.get(
                f"/backoffice/assembly/{assembly.id}/selection/{run_id}",
                follow_redirects=True,
            )
            # Should redirect to dashboard with error
            assert response.status_code == 200

    def test_view_run_details_endpoint_exists(self, logged_in_admin, assembly_with_gsheet):
        """Test that view_run_details endpoint responds (tests routing)."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        # Even without mocking, the endpoint should respond with redirect
        # (either success redirect or error redirect)
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/selection/history/{run_id}",
            follow_redirects=False,
        )

        # Should redirect (either to selection page or with error)
        assert response.status_code == 302

    def test_selection_page_shows_history_section(self, logged_in_admin, assembly_with_gsheet):
        """Test that selection page contains Selection History section."""
        assembly, _gsheet = assembly_with_gsheet

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")
        assert response.status_code == 200
        # Should show the Selection History card (even if empty)
        assert b"Selection History" in response.data

    def test_selection_progress_not_found(self, logged_in_admin, assembly_with_gsheet):
        """Test progress endpoint returns 404 when task not found."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.run_record = None

        with (
            patch("opendlp.entrypoints.blueprints.backoffice.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice.get_selection_run_status",
                return_value=mock_result,
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/{run_id}/progress")
            assert response.status_code == 404
            assert response.data == b""

    def test_selection_progress_permission_denied(self, logged_in_admin, existing_assembly):
        """Test progress endpoint returns 403 when user lacks permission."""

        run_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.backoffice.get_assembly_with_permissions",
            side_effect=InsufficientPermissions("No access"),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/selection/{run_id}/progress")
            assert response.status_code == 403
            assert response.data == b""

    def test_selection_progress_no_hx_get_when_completed(self, logged_in_admin, assembly_with_gsheet):
        """Test that progress HTML omits hx-get when task is completed (stops polling)."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_run_record = MagicMock()
        mock_run_record.status.value = "completed"
        mock_run_record.error_message = None
        mock_run_record.completed_at = datetime.now(UTC)
        mock_run_record.created_at = datetime.now(UTC)
        mock_run_record.assembly_id = assembly.id
        mock_run_record.has_finished = True
        mock_run_record.is_running = False
        mock_run_record.is_pending = False
        mock_run_record.is_completed = True
        mock_run_record.is_failed = False
        mock_run_record.is_cancelled = False
        mock_run_record.task_type_verbose = "Select Google Spreadsheet"

        mock_result = MagicMock()
        mock_result.run_record = mock_run_record
        mock_result.log_messages = ["Done"]
        mock_result.run_report = None

        with (
            patch("opendlp.entrypoints.blueprints.backoffice.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice.get_selection_run_status",
                return_value=mock_result,
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/{run_id}/progress")

            assert response.status_code == 200
            assert b"hx-get" not in response.data
            assert response.headers.get("HX-Refresh") == "true"

    def test_selection_progress_hx_refresh_on_failed(self, logged_in_admin, assembly_with_gsheet):
        """Test that HX-Refresh header is set for failed tasks too."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_run_record = MagicMock()
        mock_run_record.status.value = "failed"
        mock_run_record.error_message = "Something went wrong"
        mock_run_record.completed_at = datetime.now(UTC)
        mock_run_record.created_at = datetime.now(UTC)
        mock_run_record.assembly_id = assembly.id
        mock_run_record.has_finished = True
        mock_run_record.is_running = False
        mock_run_record.is_pending = False
        mock_run_record.is_completed = False
        mock_run_record.is_failed = True
        mock_run_record.is_cancelled = False
        mock_run_record.task_type_verbose = "Select Google Spreadsheet"

        mock_result = MagicMock()
        mock_result.run_record = mock_run_record
        mock_result.log_messages = []
        mock_result.run_report = None

        with (
            patch("opendlp.entrypoints.blueprints.backoffice.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice.get_selection_run_status",
                return_value=mock_result,
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/{run_id}/progress")

            assert response.status_code == 200
            assert b"hx-get" not in response.data
            assert response.headers.get("HX-Refresh") == "true"

    def test_selection_progress_assembly_ownership_validation(self, logged_in_admin, assembly_with_gsheet):
        """Test that progress returns 404 when run belongs to a different assembly."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_run_record = MagicMock()
        mock_run_record.status.value = "running"
        mock_run_record.assembly_id = uuid.uuid4()  # Different assembly
        mock_run_record.has_finished = False

        mock_result = MagicMock()
        mock_result.run_record = mock_run_record
        mock_result.log_messages = []
        mock_result.run_report = None

        with (
            patch("opendlp.entrypoints.blueprints.backoffice.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice.get_selection_run_status",
                return_value=mock_result,
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/{run_id}/progress")
            assert response.status_code == 404

    def test_selection_with_current_selection_renders_modal(self, logged_in_admin, assembly_with_gsheet):
        """Test that selection page with current_selection param shows the progress modal."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_run_record = MagicMock()
        mock_run_record.status.value = "running"
        mock_run_record.error_message = None
        mock_run_record.completed_at = None
        mock_run_record.assembly_id = assembly.id
        mock_run_record.has_finished = False
        mock_run_record.is_running = True
        mock_run_record.is_pending = False
        mock_run_record.is_completed = False
        mock_run_record.is_failed = False
        mock_run_record.is_cancelled = False
        mock_run_record.task_type_verbose = "Load Google Spreadsheet"

        mock_result = MagicMock()
        mock_result.run_record = mock_run_record
        mock_result.log_messages = ["Checking data..."]
        mock_result.run_report = None

        with (
            patch("opendlp.entrypoints.blueprints.backoffice.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice.get_selection_run_status",
                return_value=mock_result,
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection?current_selection={run_id}")

            assert response.status_code == 200
            assert b"selection-progress-modal" in response.data
            assert b"hx-get" in response.data
            assert b"Checking data..." in response.data

    def test_cancel_invalid_selection_error(self, logged_in_admin, assembly_with_gsheet):
        """Test cancel endpoint handles InvalidSelection error."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.backoffice.cancel_task",
            side_effect=InvalidSelection("Cannot cancel completed task"),
        ):
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/selection/{run_id}/cancel",
                data={"csrf_token": csrf_token},
                follow_redirects=True,
            )

            # Should redirect with error message
            assert response.status_code == 200
