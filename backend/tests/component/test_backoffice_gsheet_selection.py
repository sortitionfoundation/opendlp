# ABOUTME: Component tests for backoffice gsheet config + selection-tab routes over a FakeUnitOfWork
# ABOUTME: Drives the real gsheet/selection Flask routes + services against a seeded fake store, no PostgreSQL

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from flask.testing import FlaskClient

from opendlp.adapters import database
from opendlp.domain.assembly import Assembly, AssemblyGSheet
from opendlp.service_layer.assembly_service import add_assembly_gsheet, create_assembly
from tests.fakes import FakeUnitOfWork


@pytest.fixture(autouse=True)
def _mapped_domain_objects():
    """GSheet/settings writes call SQLAlchemy flag_modified, which needs mapped classes."""
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


class TestBackofficeGSheetConfigForm:
    """Test the gsheet configuration form on backoffice data page."""

    def test_gsheet_form_shows_new_mode_when_no_config_exists(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that new gsheet form is shown when no config exists."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")
        assert response.status_code == 200
        assert b'name="url"' in response.data
        assert b"Save" in response.data or b"submit" in response.data.lower()

    def test_gsheet_form_contains_required_fields(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that gsheet form contains all required fields."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")
        assert response.status_code == 200

        assert b'name="url"' in response.data
        assert b"select_registrants_tab" in response.data
        assert b"select_targets_tab" in response.data
        assert b"check_same_address" in response.data

    def test_gsheet_form_shows_view_mode_when_config_exists(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test that readonly view mode is shown when gsheet config exists (no mode param)."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=gsheet")
        assert response.status_code == 200
        assert b"Edit" in response.data or b"edit" in response.data.lower()
        assert b"docs.google.com/spreadsheets" in response.data

    def test_gsheet_form_shows_edit_mode_with_mode_param(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test that editable form is shown when mode=edit param is present."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=gsheet&mode=edit")
        assert response.status_code == 200
        assert b'name="url"' in response.data
        assert b"Save" in response.data or b"submit" in response.data.lower()
        assert b"Cancel" in response.data or b"cancel" in response.data.lower()

    def test_gsheet_form_shows_default_values_in_new_mode(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that form defaults are shown when creating new gsheet config."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")
        assert response.status_code == 200
        assert b"Respondents" in response.data
        assert b"Categories" in response.data
        assert b"Selected" in response.data

    def test_gsheet_form_contains_all_fields(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that gsheet form contains all key configuration fields."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")
        assert response.status_code == 200

        assert b'name="url"' in response.data
        assert b"select_registrants_tab" in response.data
        assert b"select_targets_tab" in response.data
        assert b"already_selected_tab" in response.data
        assert b"id_column" in response.data
        assert b"check_same_address_cols_string" in response.data or b"address" in response.data.lower()
        assert b"columns_to_keep_string" in response.data or b"columns" in response.data.lower()
        assert b"check_same_address" in response.data
        assert b"generate_remaining_tab" in response.data


class TestBackofficeGSheetFormSubmission:
    """Test gsheet form submission rendering and validation branches."""

    def test_create_gsheet_config_validation_error_missing_url(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test validation error when creating gsheet config without URL."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/save",
            data={
                "url": "",
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
        assert response.status_code == 200
        assert b'name="url"' in response.data

    def test_create_gsheet_config_validation_error_invalid_url(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test validation error when creating gsheet config with invalid URL."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/save",
            data={
                "url": "https://example.com/not-a-google-sheet",
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
        assert response.status_code == 200

    def test_update_gsheet_config_validation_error(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test validation error when updating gsheet config with invalid data."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/gsheet/save",
            data={
                "url": "",
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
        assert response.status_code == 200
        assert b'name="url"' in response.data

    def test_create_gsheet_shows_warning_for_empty_columns_to_keep(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that warning is shown when columns_to_keep is empty."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/save",
            data={
                "url": "https://docs.google.com/spreadsheets/d/1warningtest/edit",
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "id",
                "generate_remaining_tab": "y",
                "columns_to_keep_string": "",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Warning" in response.data or b"columns to keep" in response.data.lower()

    def test_create_gsheet_no_warning_for_empty_columns_with_team(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that team-based defaults prevent columns_to_keep warning."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/save",
            data={
                "url": "https://docs.google.com/spreadsheets/d/1nowarningtest/edit",
                "team": "uk",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "test_id",
                "check_same_address": "y",
                "check_same_address_cols_string": "address1, postcode",
                "columns_to_keep_string": "",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"created successfully" in response.data or b"success" in response.data.lower()
        assert b"Warning" not in response.data and b"No columns to keep" not in response.data

    def test_gsheet_permission_denied_for_regular_user(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test regular users cannot access or submit gsheet configuration."""
        get_response = logged_in_user.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")
        assert get_response.status_code in [302, 403]

    def test_gsheet_redirects_when_not_logged_in(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        """Test gsheet page redirects to login when not authenticated."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")
        assert response.status_code == 302
        assert "login" in response.location


class TestBackofficeGSheetValidation:
    """Test gsheet-specific validation rules."""

    def test_hard_validation_check_address_without_columns(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test hard validation: check_same_address=True requires address columns."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/save",
            data={
                "url": "https://docs.google.com/spreadsheets/d/validation123/edit",
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "test_id",
                "check_same_address": "y",
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "first_name, last_name",
            },
        )
        assert response.status_code == 200
        assert b"address columns" in response.data.lower() or b"must specify" in response.data.lower()

    def test_hard_validation_passes_when_team_not_other(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test hard validation passes when team auto-generates address columns."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/save",
            data={
                "url": "https://docs.google.com/spreadsheets/d/validation_team_123/edit",
                "team": "uk",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "test_id",
                "check_same_address": "y",
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "first_name, last_name",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_hard_validation_passes_when_check_address_disabled(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test hard validation: check_same_address=False allows empty address columns."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/save",
            data={
                "url": "https://docs.google.com/spreadsheets/d/validation_pass_123/edit",
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "test_id",
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "first_name, last_name",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_hard_validation_on_edit(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test hard validation on edit: check_same_address=True requires address columns."""
        assembly, _gsheet = assembly_with_gsheet
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/gsheet/save",
            data={
                "url": "https://docs.google.com/spreadsheets/d/edit_validation_123/edit",
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "test_id",
                "check_same_address": "y",
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "first_name, last_name",
            },
        )
        assert response.status_code == 200
        assert b"address columns" in response.data.lower() or b"must specify" in response.data.lower()

    def test_url_validation_enforced(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that URL validation is properly enforced for various invalid URLs."""
        invalid_urls = [
            "not-a-url",
            "https://example.com/not-google-sheets",
            "https://drive.google.com/file/d/wrong-format",
            "",
        ]

        for invalid_url in invalid_urls:
            response = logged_in_admin.post(
                f"/backoffice/assembly/{existing_assembly.id}/gsheet/save",
                data={
                    "url": invalid_url,
                    "team": "uk",
                    "select_registrants_tab": "Test",
                    "select_targets_tab": "Test",
                    "replace_registrants_tab": "Remaining",
                    "replace_targets_tab": "Replacement",
                    "already_selected_tab": "Selected",
                    "id_column": "test_id",
                },
            )
            assert response.status_code == 200, f"Expected 200 for invalid URL: {invalid_url}"


class TestBackofficeGSheetDelete:
    """Test gsheet configuration delete button visibility and not-found handling."""

    def test_delete_gsheet_config_not_found(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test deleting a non-existent gsheet configuration."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/gsheet/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/data" in response.location

        response = logged_in_admin.get(response.location)
        assert response.status_code == 200
        assert b"not found" in response.data

    def test_delete_button_shown_in_view_mode(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test that delete button is shown in VIEW mode when config exists."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=gsheet")
        assert response.status_code == 200
        assert b"Delete" in response.data
        assert b"gsheet/delete" in response.data

    def test_delete_button_shown_in_edit_mode(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test that delete button is shown in EDIT mode when config exists."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=gsheet&mode=edit")
        assert response.status_code == 200
        assert b"Delete" in response.data
        assert b"gsheet/delete" in response.data

    def test_delete_button_not_shown_in_new_mode(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that delete button is NOT shown in NEW mode when no config exists."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=gsheet")
        assert response.status_code == 200
        assert b"gsheet/delete" not in response.data

    def test_delete_gsheet_permission_denied_for_regular_user(
        self, logged_in_user: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test regular users cannot delete gsheet configurations."""
        assembly, _gsheet = assembly_with_gsheet
        response = logged_in_user.post(f"/backoffice/assembly/{assembly.id}/gsheet/delete", data={})
        assert response.status_code in [302, 403]

    def test_delete_gsheet_redirects_when_not_logged_in(
        self, client: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test delete gsheet redirects to login when not authenticated."""
        assembly, _gsheet = assembly_with_gsheet
        response = client.post(f"/backoffice/assembly/{assembly.id}/gsheet/delete")
        assert response.status_code == 302
        assert "login" in response.location


class TestBackofficeSelectionTab:
    """Test selection-tab routes that render before any Celery dispatch."""

    def test_selection_page_loads_without_gsheet_config(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that selection page loads and shows configure message when no gsheet config."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/selection")
        assert response.status_code == 200
        assert b"configure" in response.data.lower() or b"Google Spreadsheet" in response.data

    def test_selection_page_loads_with_gsheet_config(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test that selection page loads when gsheet is configured."""
        assembly, _gsheet = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")
        assert response.status_code == 200
        assert b"Selection" in response.data

    def test_selection_page_redirects_when_not_logged_in(
        self, client: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/selection")
        assert response.status_code == 302
        assert "login" in response.location

    def test_selection_page_shows_history_section(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test that selection page contains Selection History section."""
        assembly, _gsheet = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")
        assert response.status_code == 200
        assert b"Selection History" in response.data

    def test_selection_with_run_page_redirects_to_query_param(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test that legacy /selection/<run_id> URL redirects to query param version."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/{run_id}")
        assert response.status_code == 302
        assert f"current_selection={run_id}" in response.location
