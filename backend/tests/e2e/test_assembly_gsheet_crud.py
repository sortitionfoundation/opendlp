"""ABOUTME: End-to-end AssemblyGSheet CRUD tests
ABOUTME: Tests complete AssemblyGSheet creation, viewing, editing, and deletion workflows through web interface"""

from opendlp.domain.assembly import DEFAULT_ADDRESS_COLS, DEFAULT_COLS_TO_KEEP, DEFAULT_ID_COLUMN
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token


class TestAssemblyGSheetCreateView:
    """Test AssemblyGSheet creation functionality."""

    def test_create_gsheet_get_form_no_existing(self, logged_in_admin, existing_assembly):
        """Test create gsheet form is displayed when no gsheet exists."""
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/gsheet")
        assert response.status_code == 200
        assert b"Configure Google Spreadsheet" in response.data
        assert b"Google Spreadsheet URL" in response.data
        assert b"Team Configuration" in response.data
        assert b"Save Configuration" in response.data

    def test_create_gsheet_form_contains_all_fields(self, logged_in_admin, existing_assembly):
        """Test that gsheet form contains all required fields."""
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/gsheet")
        assert response.status_code == 200

        # URL field
        assert b"Google Spreadsheet URL" in response.data
        assert b"docs.google.com" in response.data  # Placeholder

        # Team selection
        assert b"Team Configuration" in response.data
        assert b"UK Team" in response.data
        assert b"EU Team" in response.data
        assert b"Australia Team" in response.data

        # Tab names
        assert b"Respondents Tab Name" in response.data
        assert b"Targets Tab Name" in response.data

        # ID column
        assert b"ID Column" in response.data

        # String list fields
        assert b"Address Columns" in response.data
        assert b"Columns to Keep" in response.data

        # Checkboxes
        assert b"Check Same Address" in response.data
        assert b"Generate Remaining Tab" in response.data

    def test_create_gsheet_success(self, logged_in_admin, existing_assembly):
        """Test successful gsheet creation."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/1234567890abcdef123456789/edit",
                "team": "uk",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "id_column": "nationbuilder_id",
                "check_same_address_cols_string": "primary_address1, zip_royal_mail",
                "columns_to_keep_string": "first_name, last_name, email, mobile_number",
                "check_same_address": "y",
                "generate_remaining_tab": "y",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/gsheet"),
            },
            follow_redirects=False,
        )

        # Should redirect to view assembly page
        assert response.status_code == 302
        assert f"/assemblies/{existing_assembly.id}" in response.location

        # Check flash message
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("configuration created successfully" in msg for msg in flash_messages)

    def test_create_gsheet_validation_invalid_url(self, logged_in_admin, existing_assembly):
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
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/gsheet"),
            },
        )

        # Should return form with validation errors
        assert response.status_code == 200
        assert b"error" in response.data or b"Invalid" in response.data

    def test_create_gsheet_validation_required_fields(self, logged_in_admin, existing_assembly):
        """Test form validation errors for missing required fields."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/gsheet",
            data={
                "url": "",  # Missing required URL
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/gsheet"),
            },
        )

        # Should return form with validation errors
        assert response.status_code == 200
        assert b"error" in response.data or b"required" in response.data

    def test_create_gsheet_with_custom_team_and_string_fields(self, logged_in_admin, existing_assembly):
        """Test creating gsheet with 'other' team and custom string field values."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/custom123456789/edit",
                "team": "other",  # Custom configuration
                "select_registrants_tab": "CustomRespondents",
                "select_targets_tab": "CustomCategories",
                "id_column": "custom_id",
                "check_same_address_cols_string": "street_address, postal_code, city",
                "columns_to_keep_string": "first_name, last_name, email, phone, address",
                "check_same_address": True,
                "generate_remaining_tab": False,
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/gsheet"),
            },
            follow_redirects=False,
        )

        # Should succeed
        assert response.status_code == 302
        assert f"/assemblies/{existing_assembly.id}" in response.location

        # Check flash message
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("configuration created successfully" in msg for msg in flash_messages)

    def test_create_gsheet_permission_denied_for_user(self, logged_in_user, existing_assembly):
        """Test regular users cannot create gsheet configurations."""
        response = logged_in_user.get(f"/assemblies/{existing_assembly.id}/gsheet")
        # Should redirect or show permission error
        assert response.status_code in [302, 403, 500]

    def test_create_gsheet_redirects_when_not_logged_in(self, client, existing_assembly):
        """Test create gsheet redirects to login when not authenticated."""
        response = client.get(f"/assemblies/{existing_assembly.id}/gsheet")
        assert response.status_code == 302
        assert "login" in response.location


class TestAssemblyGSheetEditView:
    """Test AssemblyGSheet editing functionality."""

    def test_edit_gsheet_get_form_with_existing(self, logged_in_admin, assembly_with_gsheet):
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

    def test_edit_gsheet_success_with_team_eu(self, logged_in_admin, assembly_with_gsheet, postgres_session_factory):
        """Test successful gsheet editing with eu team overriding some settings."""
        assembly, gsheet = assembly_with_gsheet
        updated_url = "https://docs.google.com/spreadsheets/d/updated123456789/edit"

        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={
                "url": updated_url,
                "team": "eu",  # Changed from uk
                "select_registrants_tab": "UpdatedRespondents",
                "select_targets_tab": "UpdatedCategories",
                # "check_same_address": False - omit to set to False
                "generate_remaining_tab": "y",  # "y" to set to True
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{assembly.id}/gsheet"),
            },
            follow_redirects=False,
        )

        # Should redirect to view assembly page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}" in response.location

        # Check flash message
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("configuration updated successfully" in msg for msg in flash_messages)

        # Verify the changes were actually saved to the database
        from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            saved_gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly.id)
            assert saved_gsheet is not None

            # Check that all form values were properly saved
            assert saved_gsheet.url == updated_url
            assert saved_gsheet.select_registrants_tab == "UpdatedRespondents"
            assert saved_gsheet.select_targets_tab == "UpdatedCategories"
            assert saved_gsheet.id_column == DEFAULT_ID_COLUMN["eu"]
            assert saved_gsheet.check_same_address is False
            assert saved_gsheet.generate_remaining_tab is True

            # Check that the string fields were properly converted to lists
            assert saved_gsheet.check_same_address_cols == DEFAULT_ADDRESS_COLS["eu"]
            assert saved_gsheet.columns_to_keep == DEFAULT_COLS_TO_KEEP["eu"]

    def test_edit_gsheet_success_with_team_custom(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test successful gsheet editing."""
        assembly, gsheet = assembly_with_gsheet
        updated_url = "https://docs.google.com/spreadsheets/d/updated123456789/edit"

        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={
                "url": updated_url,
                "team": "other",  # Changed from uk
                "select_registrants_tab": "UpdatedRespondents",
                "select_targets_tab": "UpdatedCategories",
                "id_column": "updated_id_column",
                "check_same_address_cols_string": "address_line, postcode",  # EU team defaults
                "columns_to_keep_string": "first_name, last_name, email, phone_number, city",
                # "check_same_address": False - omit to set to False
                "generate_remaining_tab": "y",  # "y" to set to True
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{assembly.id}/gsheet"),
            },
            follow_redirects=False,
        )

        # Should redirect to view assembly page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}" in response.location

        # Check flash message
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("configuration updated successfully" in msg for msg in flash_messages)

        # Verify the changes were actually saved to the database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            saved_gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly.id)
            assert saved_gsheet is not None

            # Check that all form values were properly saved
            assert saved_gsheet.id_column == "updated_id_column"

            # Check that the string fields were properly converted to lists
            assert saved_gsheet.check_same_address_cols == ["address_line", "postcode"]
            assert saved_gsheet.columns_to_keep == ["first_name", "last_name", "email", "phone_number", "city"]

    def test_edit_gsheet_validation_errors(self, logged_in_admin, assembly_with_gsheet):
        """Test form validation errors on gsheet editing."""
        assembly, gsheet = assembly_with_gsheet
        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={
                "url": "",  # Empty URL should fail validation
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{assembly.id}/gsheet"),
            },
        )

        # Should return form with validation errors
        assert response.status_code == 200
        assert b"error" in response.data or b"required" in response.data

    def test_edit_gsheet_permission_denied_for_user(self, logged_in_user, assembly_with_gsheet):
        """Test regular users cannot edit gsheet configurations."""
        assembly, gsheet = assembly_with_gsheet
        response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet")
        # Should redirect or show permission error
        assert response.status_code in [302, 403, 500]


class TestAssemblyGSheetDeleteView:
    """Test AssemblyGSheet deletion functionality."""

    def test_delete_gsheet_success(self, logged_in_admin, assembly_with_gsheet):
        """Test successful gsheet deletion."""
        assembly, gsheet = assembly_with_gsheet
        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet/delete",
            data={
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{assembly.id}/gsheet/delete"),
            },
            follow_redirects=False,
        )

        # Should redirect to view assembly page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}" in response.location

        # Check flash message
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("configuration removed successfully" in msg for msg in flash_messages)

    def test_delete_nonexistent_gsheet(self, logged_in_admin, existing_assembly):
        """Test deleting non-existent gsheet shows error."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/gsheet/delete",
            data={
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/gsheet/delete"),
            },
            follow_redirects=False,
        )

        # Should redirect with error message
        assert response.status_code == 302
        assert f"/assemblies/{existing_assembly.id}" in response.location

        # Check error flash message
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("not found" in msg for msg in flash_messages)

    def test_delete_gsheet_permission_denied_for_user(self, logged_in_user, assembly_with_gsheet):
        """Test regular users cannot delete gsheet configurations."""
        assembly, gsheet = assembly_with_gsheet
        response = logged_in_user.post(
            f"/assemblies/{assembly.id}/gsheet/delete",
            data={
                "csrf_token": get_csrf_token(logged_in_user, f"/assemblies/{assembly.id}/gsheet/delete"),
            },
        )
        # Should redirect or show permission error
        assert response.status_code in [302, 403, 500]

    def test_delete_gsheet_redirects_when_not_logged_in(self, client, assembly_with_gsheet):
        """Test delete gsheet redirects to login when not authenticated."""
        assembly, gsheet = assembly_with_gsheet
        response = client.post(f"/assemblies/{assembly.id}/gsheet/delete")
        assert response.status_code == 302
        assert "login" in response.location


class TestAssemblyGSheetWorkflowIntegration:
    """Test complete gsheet workflows end-to-end."""

    def test_complete_create_edit_delete_workflow(self, logged_in_admin, existing_assembly):
        """Test complete workflow: create -> edit -> delete gsheet configuration."""
        assembly = existing_assembly

        # Step 1: Create gsheet configuration
        create_response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/workflow123456789/edit",
                "team": "uk",
                "select_registrants_tab": "WorkflowRespondents",
                "select_targets_tab": "WorkflowCategories",
                "id_column": "workflow_id",
                "check_same_address": True,
                "generate_remaining_tab": False,
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{assembly.id}/gsheet"),
            },
            follow_redirects=False,
        )

        assert create_response.status_code == 302
        assert f"/assemblies/{assembly.id}" in create_response.location

        # Step 2: Edit the gsheet configuration
        edit_response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/updated_workflow123456789/edit",
                "team": "eu",
                "select_registrants_tab": "UpdatedWorkflowRespondents",
                "select_targets_tab": "UpdatedWorkflowCategories",
                "id_column": "updated_workflow_id",
                "check_same_address": False,
                "generate_remaining_tab": True,
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{assembly.id}/gsheet"),
            },
            follow_redirects=False,
        )

        assert edit_response.status_code == 302
        assert f"/assemblies/{assembly.id}" in edit_response.location

        # Step 3: Delete the gsheet configuration
        delete_response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet/delete",
            data={
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{assembly.id}/gsheet/delete"),
            },
            follow_redirects=False,
        )

        assert delete_response.status_code == 302
        assert f"/assemblies/{assembly.id}" in delete_response.location

        # Step 4: Verify gsheet configuration is removed (form should show create again)
        verify_response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet")
        assert verify_response.status_code == 200
        assert b"Configure Google Spreadsheet" in verify_response.data  # Create form
        assert b"Edit Google Spreadsheet Configuration" not in verify_response.data

    def test_gsheet_state_transitions(self, logged_in_admin, existing_assembly):
        """Test state transitions between no gsheet -> has gsheet -> no gsheet."""
        assembly = existing_assembly

        # Initially no gsheet - should show create form
        initial_response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet")
        assert initial_response.status_code == 200
        assert b"Configure Google Spreadsheet" in initial_response.data
        assert b"Save Configuration" in initial_response.data

        # Create gsheet
        logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/state123456789/edit",
                "team": "uk",
                "select_registrants_tab": "StateRespondents",
                "select_targets_tab": "StateCategories",
                "id_column": "state_id",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{assembly.id}/gsheet"),
            },
        )

        # Now has gsheet - should show edit form
        edit_response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet")
        assert edit_response.status_code == 200
        assert b"Edit Google Spreadsheet Configuration" in edit_response.data
        assert b"Save Changes" in edit_response.data
        assert b"Remove Configuration" in edit_response.data
        assert b"state123456789" in edit_response.data

        # Delete gsheet
        logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet/delete",
            data={
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{assembly.id}/gsheet/delete"),
            },
        )

        # Back to no gsheet - should show create form again
        final_response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet")
        assert final_response.status_code == 200
        assert b"Configure Google Spreadsheet" in final_response.data
        assert b"Save Configuration" in final_response.data
        assert b"Edit Google Spreadsheet Configuration" not in final_response.data

    def test_navigation_breadcrumbs_work(self, logged_in_admin, existing_assembly):
        """Test that navigation breadcrumbs are functional."""
        assembly = existing_assembly

        # Create form should have breadcrumbs
        create_response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet")
        assert create_response.status_code == 200
        assert b"Dashboard" in create_response.data
        assert assembly.title.encode() in create_response.data

        # Create gsheet and test edit form breadcrumbs
        logged_in_admin.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/breadcrumb123456789/edit",
                "team": "uk",
                "select_registrants_tab": "BreadcrumbRespondents",
                "select_targets_tab": "BreadcrumbCategories",
                "id_column": "breadcrumb_id",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{assembly.id}/gsheet"),
            },
        )

        # Edit form should also have breadcrumbs
        edit_response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet")
        assert edit_response.status_code == 200
        assert b"Dashboard" in edit_response.data
        assert assembly.title.encode() in edit_response.data


class TestAssemblyGSheetPermissions:
    """Test gsheet permission handling."""

    def test_permissions_properly_enforced_for_regular_users(self, logged_in_user, existing_assembly):
        """Test that permission restrictions are properly enforced for regular users."""
        assembly = existing_assembly

        # GET request should be blocked
        get_response = logged_in_user.get(f"/assemblies/{assembly.id}/gsheet")
        assert get_response.status_code in [302, 403, 500]

        # POST request should also be blocked
        post_response = logged_in_user.post(
            f"/assemblies/{assembly.id}/gsheet",
            data={
                "url": "https://docs.google.com/spreadsheets/d/unauthorized123456789/edit",
                "csrf_token": get_csrf_token(logged_in_user, f"/assemblies/{assembly.id}/gsheet"),
            },
        )
        assert post_response.status_code in [302, 403, 500]

    def test_nonexistent_assembly_returns_error(self, logged_in_admin):
        """Test accessing gsheet for non-existent assembly returns error."""
        response = logged_in_admin.get("/assemblies/00000000-0000-0000-0000-000000000000/gsheet")
        assert response.status_code == 302  # Should redirect to dashboard with error

    def test_url_validation_enforced(self, logged_in_admin, existing_assembly):
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
                    "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{assembly.id}/gsheet"),
                },
            )
            # Should return form with validation error
            assert response.status_code == 200
            assert b"error" in response.data or b"Invalid" in response.data or b"required" in response.data
