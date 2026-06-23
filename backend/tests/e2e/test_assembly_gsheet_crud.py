"""ABOUTME: End-to-end AssemblyGSheet CRUD smoke + DB-semantics tests
ABOUTME: Keeps create/delete/workflow smokes and SelectionSettings JSON round-trip checks on real PostgreSQL"""

import pytest

from opendlp.domain.selection_settings import DEFAULT_ADDRESS_COLS, DEFAULT_COLS_TO_KEEP, DEFAULT_ID_COLUMN
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token


class TestAssemblyGSheetCreateView:
    """Test AssemblyGSheet creation functionality."""

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

        # Should redirect to view assembly data page
        assert response.status_code == 302
        assert f"/assemblies/{existing_assembly.id}/data" in response.location

        # Check flash message
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("configuration created successfully" in msg for msg in flash_messages)


class TestAssemblyGSheetEditView:
    """Test AssemblyGSheet editing DB semantics on real PostgreSQL."""

    @pytest.mark.db_semantics
    def test_edit_gsheet_get_form_populates_selection_settings_fields(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """The edit form must show the SelectionSettings values that are actually saved.

        Regression: previously the form was built with ``obj=existing_gsheet`` which only
        populated AssemblyGSheet fields, leaving ``id_column``, ``check_same_address_cols_string``
        and ``columns_to_keep_string`` rendering as static form defaults rather than the values
        saved on the assembly's SelectionSettings.
        """
        assembly, _gsheet = assembly_with_gsheet

        # Confirm the saved SelectionSettings (team="uk" applied UK defaults in the fixture).
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            saved_assembly = uow.assemblies.get(assembly.id)
            assert saved_assembly.selection_settings is not None
            sel_settings = saved_assembly.selection_settings
            assert sel_settings.id_column == DEFAULT_ID_COLUMN["uk"]
            assert sel_settings.check_same_address_cols == DEFAULT_ADDRESS_COLS["uk"]
            assert sel_settings.columns_to_keep == DEFAULT_COLS_TO_KEEP["uk"]
            address_cols_string = sel_settings.check_same_address_cols_string
            columns_to_keep_string = sel_settings.columns_to_keep_string

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/gsheet")
        assert response.status_code == 200

        # The rendered form must contain the actual saved SelectionSettings values.
        # These fields live on SelectionSettings, not AssemblyGSheet, so they are not
        # populated by ``obj=existing_gsheet`` alone.
        assert f'value="{address_cols_string}"'.encode() in response.data, (
            "Address columns string from SelectionSettings should pre-populate the form"
        )
        assert f'value="{columns_to_keep_string}"'.encode() in response.data, (
            "Columns to keep string from SelectionSettings should pre-populate the form"
        )

    @pytest.mark.db_semantics
    def test_edit_gsheet_success_with_team_eu(self, logged_in_admin, assembly_with_gsheet, postgres_session_factory):
        """Test successful gsheet editing with eu team overriding some settings."""
        assembly, _gsheet = assembly_with_gsheet
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

        # Should redirect to view assembly data page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/data" in response.location

        # Check flash message
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("configuration updated successfully" in msg for msg in flash_messages)

        # Verify the changes were actually saved to the database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            saved_gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly.id)
            assert saved_gsheet is not None

            # Check that gsheet-specific form values were properly saved
            assert saved_gsheet.url == updated_url
            assert saved_gsheet.select_registrants_tab == "UpdatedRespondents"
            assert saved_gsheet.select_targets_tab == "UpdatedCategories"
            assert saved_gsheet.generate_remaining_tab is True

            # Check that selection settings were properly saved (team defaults applied)
            saved_assembly = uow.assemblies.get(assembly.id)
            assert saved_assembly.selection_settings is not None
            assert saved_assembly.selection_settings.id_column == DEFAULT_ID_COLUMN["eu"]
            assert saved_assembly.selection_settings.check_same_address is False
            assert saved_assembly.selection_settings.check_same_address_cols == DEFAULT_ADDRESS_COLS["eu"]
            assert saved_assembly.selection_settings.columns_to_keep == DEFAULT_COLS_TO_KEEP["eu"]

    @pytest.mark.db_semantics
    def test_edit_gsheet_success_with_team_custom(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test successful gsheet editing."""
        assembly, _gsheet = assembly_with_gsheet
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

        # Should redirect to view assembly data page
        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/data" in response.location

        # Check flash message
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("configuration updated successfully" in msg for msg in flash_messages)

        # Verify the changes were actually saved to the database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            saved_gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly.id)
            assert saved_gsheet is not None

            # Check that selection settings were properly saved
            saved_assembly = uow.assemblies.get(assembly.id)
            assert saved_assembly.selection_settings is not None
            assert saved_assembly.selection_settings.id_column == "updated_id_column"
            assert saved_assembly.selection_settings.check_same_address_cols == ["address_line", "postcode"]
            assert saved_assembly.selection_settings.columns_to_keep == [
                "first_name",
                "last_name",
                "email",
                "phone_number",
                "city",
            ]


class TestAssemblyGSheetDeleteView:
    """Test AssemblyGSheet deletion functionality."""

    def test_delete_gsheet_success(self, logged_in_admin, assembly_with_gsheet):
        """Test successful gsheet deletion."""
        assembly, _gsheet = assembly_with_gsheet
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
                # check_same_address defaults to True in the form, but team='uk' will set address columns
                "check_same_address_cols_string": "primary_address1, zip_royal_mail",  # Provide columns for validation
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
