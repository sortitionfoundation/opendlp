"""ABOUTME: End-to-end tests for backoffice gsheet selection (Celery dispatch + DB semantics)
ABOUTME: Tests gsheet save/delete smokes, selection_settings round-trip, and selection load/run/cancel"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from opendlp.service_layer.exceptions import InsufficientPermissions, NotFoundError
from opendlp.service_layer.sortition import InvalidSelection
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token


class TestBackofficeGSheetFormSubmission:
    """Smoke and DB-semantics tests for gsheet form submission."""

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
                "check_same_address_cols_string": "address1,city,postcode",
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

    @pytest.mark.db_semantics
    def test_update_gsheet_config_success_with_team_eu(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test successful gsheet editing with eu team verifying DB values."""
        assembly, _gsheet = assembly_with_gsheet
        updated_url = "https://docs.google.com/spreadsheets/d/updated_eu_123/edit"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/gsheet/save",
            data={
                "url": updated_url,
                "team": "eu",
                "select_registrants_tab": "UpdatedRespondents",
                "select_targets_tab": "UpdatedCategories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement",
                "already_selected_tab": "Selected",
                "generate_remaining_tab": "y",
                "csrf_token": get_csrf_token(
                    logged_in_admin, f"/backoffice/assembly/{assembly.id}/data?source=gsheet&mode=edit"
                ),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302

        # Verify the changes were saved to the database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            saved_gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly.id)
            assert saved_gsheet is not None
            assert saved_gsheet.url == updated_url
            assert saved_gsheet.select_registrants_tab == "UpdatedRespondents"
            assert saved_gsheet.generate_remaining_tab is True

    @pytest.mark.db_semantics
    def test_update_gsheet_config_success_with_custom_team(
        self, logged_in_admin, assembly_with_gsheet, postgres_session_factory
    ):
        """Test successful gsheet editing with custom team verifying DB values."""
        assembly, _gsheet = assembly_with_gsheet
        updated_url = "https://docs.google.com/spreadsheets/d/updated_custom_123/edit"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/gsheet/save",
            data={
                "url": updated_url,
                "team": "other",
                "select_registrants_tab": "CustomRespondents",
                "select_targets_tab": "CustomCategories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement",
                "already_selected_tab": "Selected",
                "id_column": "custom_id",
                "check_same_address_cols_string": "address_line, postcode",
                "columns_to_keep_string": "first_name, last_name, email, phone",
                "generate_remaining_tab": "y",
                "csrf_token": get_csrf_token(
                    logged_in_admin, f"/backoffice/assembly/{assembly.id}/data?source=gsheet&mode=edit"
                ),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302

        # Verify the changes were saved to the database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            saved_gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly.id)
            assert saved_gsheet is not None

            # Selection settings fields are now on SelectionSettings, not GSheet
            saved_assembly = uow.assemblies.get(assembly.id)
            assert saved_assembly.selection_settings is not None
            assert saved_assembly.selection_settings.id_column == "custom_id"
            assert saved_assembly.selection_settings.check_same_address_cols == ["address_line", "postcode"]
            assert saved_assembly.selection_settings.columns_to_keep == ["first_name", "last_name", "email", "phone"]


class TestBackofficeGSheetDelete:
    """Smoke test for gsheet configuration deletion."""

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

    def test_gsheet_state_transitions(self, logged_in_admin, existing_assembly):
        """Test state transitions between no gsheet -> has gsheet -> no gsheet."""
        assembly = existing_assembly

        # Initially no gsheet - should show new form
        initial_response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=gsheet")
        assert initial_response.status_code == 200
        assert b'name="url"' in initial_response.data

        # Create gsheet
        logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/gsheet/save",
            data={
                "url": "https://docs.google.com/spreadsheets/d/state_transition_123/edit",
                "team": "uk",
                "select_registrants_tab": "StateRespondents",
                "select_targets_tab": "StateCategories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement",
                "already_selected_tab": "Selected",
                "id_column": "state_id",
                "csrf_token": get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/data?source=gsheet"),
            },
        )

        # Now has gsheet - should show view mode
        view_response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=gsheet")
        assert view_response.status_code == 200
        assert b"state_transition_123" in view_response.data

        # Delete gsheet
        logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/gsheet/delete",
            data={
                "csrf_token": get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/data?source=gsheet"),
            },
        )

        # Back to no gsheet - should show new form again
        final_response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/data?source=gsheet")
        assert final_response.status_code == 200
        assert b'name="url"' in final_response.data


class TestBackofficeSelectionTab:
    """Test the selection tab Celery-dispatch and status-poll routes for backoffice."""

    def test_selection_load_endpoint_starts_task(self, logged_in_admin, assembly_with_gsheet):
        """Test that load endpoint starts a gsheet load task and redirects to run page."""

        assembly, _gsheet = assembly_with_gsheet
        mock_task_id = "12345678-1234-1234-1234-123456789012"

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_load_task",
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

    def test_selection_load_redirects_when_not_logged_in(self, client, assembly_with_gsheet):
        """Test that load endpoint redirects to login when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.post(f"/backoffice/assembly/{assembly.id}/selection/load")
        assert response.status_code == 302
        assert "login" in response.location

    def test_selection_run_endpoint_starts_task(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint starts a gsheet select task and redirects to run page."""

        assembly, _gsheet = assembly_with_gsheet
        mock_task_id = "12345678-1234-1234-1234-123456789012"

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_select_task",
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

    def test_selection_run_redirects_when_not_logged_in(self, client, assembly_with_gsheet):
        """Test that run endpoint redirects to login when not authenticated."""
        assembly, _ = assembly_with_gsheet
        response = client.post(f"/backoffice/assembly/{assembly.id}/selection/run")
        assert response.status_code == 302
        assert "login" in response.location

    def test_selection_run_test_mode_endpoint(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint with test=1 passes test_selection=True."""

        assembly, _gsheet = assembly_with_gsheet
        mock_task_id = "12345678-1234-1234-1234-123456789012"

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_select_task",
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

    def test_selection_run_handles_not_found_error(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint handles NotFoundError gracefully."""

        assembly, _gsheet = assembly_with_gsheet

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_select_task",
            side_effect=NotFoundError("Gsheet config not found"),
        ):
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/selection/run",
                data={"csrf_token": csrf_token},
                follow_redirects=True,
            )

            assert response.status_code == 200

    def test_selection_run_handles_invalid_selection_error(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint handles InvalidSelection error gracefully."""

        assembly, _gsheet = assembly_with_gsheet

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_select_task",
            side_effect=InvalidSelection("Cannot run selection"),
        ):
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/selection/run",
                data={"csrf_token": csrf_token},
                follow_redirects=True,
            )

            assert response.status_code == 200

    def test_selection_progress_modal_endpoint_returns_html(self, logged_in_admin, assembly_with_gsheet):
        """Test that modal progress endpoint returns HTML fragment with HTMX attributes."""

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
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.gsheets.get_selection_run_status",
                return_value=mock_result,
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/modal-progress/{run_id}")

            assert response.status_code == 200
            assert b"hx-get" in response.data
            assert b"hx-trigger" in response.data
            assert b"Loading data..." in response.data
            assert b"Processing..." in response.data

    def test_selection_cancel_endpoint_cancels_task(self, logged_in_admin, assembly_with_gsheet):
        """Test that cancel endpoint cancels the task and redirects."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        with patch("opendlp.entrypoints.blueprints.gsheets.cancel_task") as mock_cancel:
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
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_load_task",
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

    def test_selection_load_handles_insufficient_permissions(self, logged_in_admin, assembly_with_gsheet):
        """Test that load endpoint handles InsufficientPermissions gracefully."""

        assembly, _gsheet = assembly_with_gsheet

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_load_task",
            side_effect=InsufficientPermissions(action="load_gsheet", required_role="admin"),
        ):
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/selection/load",
                data={"csrf_token": csrf_token},
                follow_redirects=True,
            )

            assert response.status_code == 200

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
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.gsheets.get_selection_run_status",
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
            "opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health",
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

    def test_selection_progress_modal_not_found(self, logged_in_admin, assembly_with_gsheet):
        """Test modal progress endpoint returns 404 when task not found."""

        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.run_record = None

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.gsheets.get_selection_run_status",
                return_value=mock_result,
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/modal-progress/{run_id}")
            assert response.status_code == 404
            assert response.data == b""

    def test_selection_progress_modal_permission_denied(self, logged_in_admin, existing_assembly):
        """Test modal progress endpoint returns 403 when user lacks permission."""

        run_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.get_assembly_with_permissions",
            side_effect=InsufficientPermissions("No access"),
        ):
            response = logged_in_admin.get(
                f"/backoffice/assembly/{existing_assembly.id}/selection/modal-progress/{run_id}"
            )
            assert response.status_code == 403
            assert response.data == b""

    def test_selection_progress_modal_no_hx_get_when_completed(self, logged_in_admin, assembly_with_gsheet):
        """Test that modal progress HTML omits hx-get when task is completed (stops polling)."""

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
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.gsheets.get_selection_run_status",
                return_value=mock_result,
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/modal-progress/{run_id}")

            assert response.status_code == 200
            # Modal stops polling by not including hx-get when finished
            assert b"hx-get" not in response.data

    def test_selection_progress_modal_no_hx_get_on_failed(self, logged_in_admin, assembly_with_gsheet):
        """Test that modal progress HTML omits hx-get for failed tasks (stops polling)."""

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
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.gsheets.get_selection_run_status",
                return_value=mock_result,
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/modal-progress/{run_id}")

            assert response.status_code == 200
            # Modal stops polling by not including hx-get when finished
            assert b"hx-get" not in response.data

    def test_selection_progress_modal_assembly_ownership_validation(self, logged_in_admin, assembly_with_gsheet):
        """Test that modal progress returns 404 when run belongs to a different assembly."""

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
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.gsheets.get_selection_run_status",
                return_value=mock_result,
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/modal-progress/{run_id}")
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
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch(
                "opendlp.entrypoints.blueprints.gsheets.get_selection_run_status",
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
            "opendlp.entrypoints.blueprints.gsheets.cancel_task",
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
