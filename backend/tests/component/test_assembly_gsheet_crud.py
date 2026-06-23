# ABOUTME: Component tests for AssemblyGSheet CRUD routes over a FakeUnitOfWork
# ABOUTME: Drives the real gsheet Flask routes + services against a seeded fake store, no PostgreSQL

from datetime import UTC, datetime, timedelta

import pytest
from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly, AssemblyGSheet
from opendlp.service_layer.assembly_service import add_assembly_gsheet, create_assembly
from tests.fakes import FakeStore, FakeUnitOfWork


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


class TestAssemblyGSheetCreateView:
    """Test AssemblyGSheet creation form rendering and validation."""

    def test_create_gsheet_get_form_no_existing(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test create gsheet form is displayed when no gsheet exists."""
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/gsheet")
        assert response.status_code == 200
        assert b"Configure Google Spreadsheet" in response.data
        assert b"Google Spreadsheet URL" in response.data
        assert b"Team Configuration" in response.data
        assert b"Save Configuration" in response.data

    def test_create_gsheet_form_contains_all_fields(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that gsheet form contains all required fields."""
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/gsheet")
        assert response.status_code == 200

        assert b"Google Spreadsheet URL" in response.data
        assert b'placeholder="https://docs.google.com/spreadsheets/d/' in response.data

        assert b"Team Configuration" in response.data
        assert b"UK Team" in response.data
        assert b"EU Team" in response.data
        assert b"Australia Team" in response.data

        assert b"Respondents Tab Name" in response.data
        assert b"Targets Tab Name" in response.data
        assert b"Already Selected Tab Name" in response.data

        assert b"ID Column" in response.data

        assert b"Address Columns" in response.data
        assert b"Columns to Keep" in response.data

        assert b"Check Same Address" in response.data
        assert b"Generate Remaining Tab" in response.data

    def test_create_gsheet_validation_invalid_url(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test form validation errors for invalid URL."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/gsheet",
            data={
                "url": "https://invalid-url.com/not-google-sheets",
                "team": "uk",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "id_column": "nationbuilder_id",
                "check_same_address_cols_string": "address1, postal_code",
                "columns_to_keep_string": "name, email",
            },
        )

        assert response.status_code == 200
        assert b"error" in response.data or b"Invalid" in response.data

    def test_create_gsheet_validation_required_fields(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test form validation errors for missing required fields."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/gsheet",
            data={"url": ""},
        )

        assert response.status_code == 200
        assert b"error" in response.data or b"required" in response.data

    def test_create_gsheet_with_custom_team_and_string_fields(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        """Test creating gsheet with 'other' team and custom string field values."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/custom123456789/edit",
                "team": "other",
                "select_registrants_tab": "CustomRespondents",
                "select_targets_tab": "CustomCategories",
                "id_column": "custom_id",
                "check_same_address_cols_string": "street_address, postal_code, city",
                "columns_to_keep_string": "first_name, last_name, email, phone, address",
                "check_same_address": True,
                "generate_remaining_tab": False,
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert f"/assemblies/{existing_assembly.id}/data" in response.location

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("configuration created successfully" in msg for msg in flash_messages)

        with FakeUnitOfWork(store=fake_store) as uow:
            saved_gsheet = uow.assembly_gsheets.get_by_assembly_id(existing_assembly.id)
            assert saved_gsheet is not None
            assert saved_gsheet.select_registrants_tab == "CustomRespondents"

    def test_create_gsheet_permission_denied_for_user(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test regular users cannot create gsheet configurations."""
        response = logged_in_user.get(f"/assemblies/{existing_assembly.id}/gsheet")
        assert response.status_code in [302, 403, 500]

    def test_create_gsheet_redirects_when_not_logged_in(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        """Test create gsheet redirects to login when not authenticated."""
        response = client.get(f"/assemblies/{existing_assembly.id}/gsheet")
        assert response.status_code == 302
        assert "login" in response.location


class TestAssemblyGSheetEditView:
    """Test AssemblyGSheet edit form rendering and validation."""

    def test_edit_gsheet_get_form_with_existing(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test edit gsheet form is displayed with existing data."""
        assembly, gsheet = assembly_with_gsheet
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet")
        assert response.status_code == 200
        assert b"Edit Google Spreadsheet Configuration" in response.data
        assert gsheet.url.encode() in response.data
        assert gsheet.select_registrants_tab.encode() in response.data
        assert gsheet.select_targets_tab.encode() in response.data
        assert b"Save Changes" in response.data
        assert b"Remove Configuration" in response.data

    def test_edit_gsheet_validation_errors(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test form validation errors on gsheet editing."""
        assembly, _gsheet = assembly_with_gsheet
        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={"url": ""},
        )

        assert response.status_code == 200
        assert b"error" in response.data or b"required" in response.data

    def test_edit_gsheet_permission_denied_for_user(
        self, logged_in_user: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test regular users cannot edit gsheet configurations."""
        assembly, _gsheet = assembly_with_gsheet
        response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet")
        assert response.status_code in [302, 403, 500]


class TestAssemblyGSheetDeleteView:
    """Test AssemblyGSheet deletion functionality."""

    def test_delete_nonexistent_gsheet(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test deleting non-existent gsheet shows error."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/gsheet/delete",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert f"/assemblies/{existing_assembly.id}" in response.location

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("not found" in msg for msg in flash_messages)

    def test_delete_gsheet_permission_denied_for_user(
        self, logged_in_user: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test regular users cannot delete gsheet configurations."""
        assembly, _gsheet = assembly_with_gsheet
        response = logged_in_user.post(f"/assemblies/{assembly.id}/gsheet/delete")
        assert response.status_code in [302, 403, 500]

    def test_delete_gsheet_redirects_when_not_logged_in(
        self, client: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test delete gsheet redirects to login when not authenticated."""
        assembly, _gsheet = assembly_with_gsheet
        response = client.post(f"/assemblies/{assembly.id}/gsheet/delete")
        assert response.status_code == 302
        assert "login" in response.location


class TestAssemblyGSheetWorkflowIntegration:
    """Test gsheet render workflows and state transitions over the fake store."""

    def test_gsheet_state_transitions(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test state transitions between no gsheet -> has gsheet -> no gsheet."""
        assembly = existing_assembly

        initial_response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet")
        assert initial_response.status_code == 200
        assert b"Configure Google Spreadsheet" in initial_response.data
        assert b"Save Configuration" in initial_response.data

        logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/state123456789/edit",
                "team": "uk",
                "select_registrants_tab": "StateRespondents",
                "select_targets_tab": "StateCategories",
                "id_column": "state_id",
            },
        )

        edit_response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet")
        assert edit_response.status_code == 200
        assert b"Edit Google Spreadsheet Configuration" in edit_response.data
        assert b"Save Changes" in edit_response.data
        assert b"Remove Configuration" in edit_response.data
        assert b"state123456789" in edit_response.data

        logged_in_admin.post(f"/assemblies/{assembly.id}/gsheet/delete")

        final_response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet")
        assert final_response.status_code == 200
        assert b"Configure Google Spreadsheet" in final_response.data
        assert b"Save Configuration" in final_response.data
        assert b"Edit Google Spreadsheet Configuration" not in final_response.data

    def test_navigation_breadcrumbs_work(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that navigation breadcrumbs are functional."""
        assembly = existing_assembly

        create_response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet")
        assert create_response.status_code == 200
        assert b"Dashboard" in create_response.data
        assert assembly.title.encode() in create_response.data

        logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/breadcrumb123456789/edit",
                "team": "uk",
                "select_registrants_tab": "BreadcrumbRespondents",
                "select_targets_tab": "BreadcrumbCategories",
                "id_column": "breadcrumb_id",
            },
        )

        edit_response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet")
        assert edit_response.status_code == 200
        assert b"Dashboard" in edit_response.data
        assert assembly.title.encode() in edit_response.data


class TestAssemblyGSheetPermissions:
    """Test gsheet permission handling."""

    def test_permissions_properly_enforced_for_regular_users(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that permission restrictions are properly enforced for regular users."""
        assembly = existing_assembly

        get_response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet")
        assert get_response.status_code in [302, 403, 500]

        post_response = logged_in_user.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={"url": "https://docs.google.com/spreadsheets/d/unauthorized123456789/edit"},
        )
        assert post_response.status_code in [302, 403, 500]

    def test_nonexistent_assembly_returns_error(self, logged_in_admin: FlaskClient) -> None:
        """Test accessing gsheet for non-existent assembly returns error."""
        response = logged_in_admin.get("/assemblies/00000000-0000-0000-0000-000000000000/gsheet")
        assert response.status_code == 302

    def test_url_validation_enforced(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that URL validation is properly enforced."""
        assembly = existing_assembly

        invalid_urls = [
            "not-a-url",
            "https://example.com/not-google-sheets",
            "https://drive.google.com/file/d/wrong-format",
            "",
        ]

        for invalid_url in invalid_urls:
            response = logged_in_admin.post(
                f"/assemblies/{assembly.id}/gsheet",
                data={
                    "url": invalid_url,
                    "team": "uk",
                    "select_registrants_tab": "Test",
                    "select_targets_tab": "Test",
                    "id_column": "test_id",
                },
            )
            assert response.status_code == 200
            assert b"error" in response.data or b"Invalid" in response.data or b"required" in response.data


class TestAssemblyGSheetValidation:
    """Test gsheet-specific hard and soft validation rules."""

    def test_create_gsheet_hard_validation_check_address_without_columns(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test hard validation: check_same_address=True requires address columns."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/validation123456789/edit",
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

    def test_create_gsheet_hard_validation_passes_when_team_not_other(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test hard validation: team="uk" auto-generates address columns so save succeeds."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/validation123456789/edit",
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
        )

        assert response.status_code == 302
        assert f"/assemblies/{existing_assembly.id}/data" in response.location

    def test_create_gsheet_hard_validation_passes_when_check_address_disabled(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test hard validation: check_same_address=False allows empty address columns."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/validation_pass123456789/edit",
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
        assert f"/assemblies/{existing_assembly.id}/data" in response.location

    def test_create_gsheet_soft_validation_empty_columns_to_keep_shows_warning(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test soft validation: empty columns_to_keep shows warning but allows save."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/warning123456789/edit",
                "team": "other",
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
        assert b"configuration created successfully" in response.data or b"success" in response.data.lower()
        assert (
            b"Warning" in response.data
            or b"No columns to keep" in response.data
            or b"participant data columns" in response.data
        )

    def test_create_gsheet_soft_validation_empty_columns_to_keep_with_team_does_not_show_warning(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test soft validation: team "uk" fills columns_to_keep so no warning is shown."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/warning123456789/edit",
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
        assert b"configuration created successfully" in response.data or b"success" in response.data.lower()
        assert (
            b"Warning" not in response.data
            and b"No columns to keep" not in response.data
            and b"participant data columns" not in response.data
        )

    def test_edit_gsheet_hard_validation_check_address_without_columns(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test hard validation on edit: check_same_address=True requires address columns."""
        assembly, _gsheet = assembly_with_gsheet

        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/edit_validation123456789/edit",
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

    def test_edit_gsheet_soft_validation_empty_columns_to_keep_shows_warning(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test soft validation on edit: empty columns_to_keep shows warning but allows save."""
        assembly, _gsheet = assembly_with_gsheet

        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/edit_warning123456789/edit",
                "team": "other",
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
        assert b"configuration updated successfully" in response.data or b"success" in response.data.lower()
        assert (
            b"Warning" in response.data
            or b"No columns to keep" in response.data
            or b"participant data columns" in response.data
        )
