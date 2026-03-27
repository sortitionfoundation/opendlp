"""ABOUTME: End-to-end tests for gsheets blueprint routes: replacement, manage tabs, and context helpers
ABOUTME: Covers replacement_progress_modal, manage tabs CRUD, cancel flows, and _get_*_context() coverage"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from opendlp.domain.value_objects import ManageOldTabsState, ManageOldTabsStatus, SelectionTaskType
from opendlp.service_layer.exceptions import InsufficientPermissions, NotFoundError
from opendlp.service_layer.sortition import InvalidSelection, LoadRunResult, TabManagementResult
from tests.e2e.helpers import get_csrf_token


def _make_mock_run_record(assembly_id, *, status="running", task_type_verbose="Load Google Spreadsheet", **overrides):
    """Create a MagicMock run record with sensible defaults."""
    record = MagicMock()
    record.status.value = status
    record.error_message = overrides.get("error_message")
    record.completed_at = overrides.get("completed_at")
    record.created_at = overrides.get("created_at", datetime.now(UTC))
    record.assembly_id = assembly_id
    record.has_finished = status in ("completed", "failed", "cancelled")
    record.is_running = status == "running"
    record.is_pending = status == "pending"
    record.is_completed = status == "completed"
    record.is_failed = status == "failed"
    record.is_cancelled = status == "cancelled"
    record.task_type_verbose = task_type_verbose
    record.task_type = overrides.get("task_type", SelectionTaskType.LOAD_GSHEET)
    record.log_messages = overrides.get("log_messages", [])
    return record


def _make_mock_result(run_record, *, log_messages=None, run_report=None):
    """Create a MagicMock result wrapping a run record."""
    result = MagicMock()
    result.run_record = run_record
    result.log_messages = log_messages or []
    result.run_report = run_report
    return result


class TestReplacementProgressModal:
    """Test the replacement_progress_modal HTMX endpoint."""

    def test_replacement_progress_modal_returns_html_while_running(self, logged_in_admin, assembly_with_gsheet):
        """Test that replacement progress modal returns HTML with HTMX polling when task is running."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_record = _make_mock_run_record(assembly.id, task_type_verbose="Load Replacement Google Spreadsheet")
        mock_result = _make_mock_result(mock_record, log_messages=["Loading replacement data..."])

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch("opendlp.entrypoints.blueprints.gsheets.get_selection_run_status", return_value=mock_result),
        ):
            response = logged_in_admin.get(
                f"/backoffice/assembly/{assembly.id}/selection/replacement-modal-progress/{run_id}"
            )

            assert response.status_code == 200
            assert b"replacement-modal" in response.data
            assert b"hx-get" in response.data
            assert b"hx-trigger" in response.data

    def test_replacement_progress_modal_stops_polling_when_completed(self, logged_in_admin, assembly_with_gsheet):
        """Test that replacement progress modal omits hx-get when task is completed."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_record = _make_mock_run_record(
            assembly.id,
            status="completed",
            completed_at=datetime.now(UTC),
            task_type_verbose="Load Replacement Google Spreadsheet",
        )
        mock_result = _make_mock_result(mock_record, log_messages=["Done"])

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch("opendlp.entrypoints.blueprints.gsheets.get_selection_run_status", return_value=mock_result),
        ):
            response = logged_in_admin.get(
                f"/backoffice/assembly/{assembly.id}/selection/replacement-modal-progress/{run_id}"
            )

            assert response.status_code == 200
            assert b"hx-get" not in response.data

    def test_replacement_progress_modal_returns_404_when_not_found(self, logged_in_admin, assembly_with_gsheet):
        """Test that replacement progress modal returns 404 when run record not found."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_result = _make_mock_result(None)

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch("opendlp.entrypoints.blueprints.gsheets.get_selection_run_status", return_value=mock_result),
        ):
            response = logged_in_admin.get(
                f"/backoffice/assembly/{assembly.id}/selection/replacement-modal-progress/{run_id}"
            )
            assert response.status_code == 404

    def test_replacement_progress_modal_returns_404_wrong_assembly(self, logged_in_admin, assembly_with_gsheet):
        """Test that replacement progress modal returns 404 when run belongs to different assembly."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_record = _make_mock_run_record(uuid.uuid4())  # different assembly
        mock_result = _make_mock_result(mock_record)

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch("opendlp.entrypoints.blueprints.gsheets.get_selection_run_status", return_value=mock_result),
        ):
            response = logged_in_admin.get(
                f"/backoffice/assembly/{assembly.id}/selection/replacement-modal-progress/{run_id}"
            )
            assert response.status_code == 404

    def test_replacement_progress_modal_returns_403_no_permission(self, logged_in_admin, existing_assembly):
        """Test that replacement progress modal returns 403 when user lacks permission."""
        run_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.get_assembly_with_permissions",
            side_effect=InsufficientPermissions("No access"),
        ):
            response = logged_in_admin.get(
                f"/backoffice/assembly/{existing_assembly.id}/selection/replacement-modal-progress/{run_id}"
            )
            assert response.status_code == 403


class TestReplacementLegacyRoutes:
    """Test the legacy replacement redirect routes."""

    def test_view_assembly_replacement_redirects_with_modal_open(self, logged_in_admin, assembly_with_gsheet):
        """Test that /replacement redirects to selection page with replacement_modal=open."""
        assembly, _gsheet = assembly_with_gsheet
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/replacement",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "replacement_modal=open" in response.location

    def test_view_assembly_replacement_with_run_redirects(self, logged_in_admin, assembly_with_gsheet):
        """Test that /replacement/<run_id> redirects with current_replacement param."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/replacement/{run_id}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"current_replacement={run_id}" in response.location

    def test_view_assembly_replacement_with_run_preserves_min_max(self, logged_in_admin, assembly_with_gsheet):
        """Test that /replacement/<run_id> preserves min_select and max_select params."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/replacement/{run_id}?min_select=5&max_select=20",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "min_select=5" in response.location
        assert "max_select=20" in response.location


class TestStartReplacementLoad:
    """Test the start_replacement_load endpoint."""

    def test_start_replacement_load_success(self, logged_in_admin, assembly_with_gsheet):
        """Test that load endpoint starts a replacement load task and redirects."""
        assembly, _gsheet = assembly_with_gsheet
        mock_task_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_replace_load_task",
            return_value=mock_task_id,
        ) as mock_start:
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/replacement/load",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

            assert response.status_code == 302
            assert f"replacement/{mock_task_id}" in response.location
            mock_start.assert_called_once()

    def test_start_replacement_load_not_found(self, logged_in_admin, assembly_with_gsheet):
        """Test that load endpoint handles NotFoundError gracefully."""
        assembly, _gsheet = assembly_with_gsheet

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_replace_load_task",
            side_effect=NotFoundError("GSheet not found"),
        ):
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/replacement/load",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

            assert response.status_code == 302
            assert "replacement" in response.location

    def test_start_replacement_load_invalid_selection(self, logged_in_admin, assembly_with_gsheet):
        """Test that load endpoint handles InvalidSelection gracefully."""
        assembly, _gsheet = assembly_with_gsheet

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_replace_load_task",
            side_effect=InvalidSelection("No initial selection found"),
        ):
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/replacement/load",
                data={"csrf_token": csrf_token},
                follow_redirects=True,
            )
            assert response.status_code == 200


class TestStartReplacementRun:
    """Test the start_replacement_run endpoint."""

    def test_start_replacement_run_success(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint starts a replacement task with number_to_select."""
        assembly, _gsheet = assembly_with_gsheet
        mock_task_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_replace_task",
            return_value=mock_task_id,
        ) as mock_start:
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/replacement/run?min_select=3&max_select=10",
                data={"csrf_token": csrf_token, "number_to_select": "5"},
                follow_redirects=False,
            )

            assert response.status_code == 302
            assert f"replacement/{mock_task_id}" in response.location
            # Verify number_to_select was passed to service
            call_args = mock_start.call_args
            assert call_args[0][3] == 5 or call_args[1].get("number_to_select") == 5

    def test_start_replacement_run_missing_number_to_select(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint flashes error when number_to_select is missing."""
        assembly, _gsheet = assembly_with_gsheet

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/replacement/run",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "replacement" in response.location

    def test_start_replacement_run_zero_number_to_select(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint rejects zero number_to_select."""
        assembly, _gsheet = assembly_with_gsheet

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/replacement/run",
            data={"csrf_token": csrf_token, "number_to_select": "0"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "replacement" in response.location

    def test_start_replacement_run_invalid_number_to_select(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint rejects non-integer number_to_select."""
        assembly, _gsheet = assembly_with_gsheet

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/replacement/run",
            data={"csrf_token": csrf_token, "number_to_select": "abc"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "replacement" in response.location

    def test_start_replacement_run_negative_number_to_select(self, logged_in_admin, assembly_with_gsheet):
        """Test that run endpoint rejects negative number_to_select."""
        assembly, _gsheet = assembly_with_gsheet

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/replacement/run",
            data={"csrf_token": csrf_token, "number_to_select": "-3"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "replacement" in response.location


class TestCancelReplacementRun:
    """Test the cancel_replacement_run endpoint."""

    def test_cancel_replacement_run_success(self, logged_in_admin, assembly_with_gsheet):
        """Test that cancel endpoint cancels the task and redirects."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        with patch("opendlp.entrypoints.blueprints.gsheets.cancel_task") as mock_cancel:
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/replacement/{run_id}/cancel",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

            assert response.status_code == 302
            assert f"replacement/{run_id}" in response.location
            mock_cancel.assert_called_once()

    def test_cancel_replacement_run_not_found(self, logged_in_admin, assembly_with_gsheet):
        """Test that cancel endpoint handles NotFoundError."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.cancel_task",
            side_effect=NotFoundError("Task not found"),
        ):
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/replacement/{run_id}/cancel",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

            assert response.status_code == 302
            assert "replacement" in response.location

    def test_cancel_replacement_run_invalid_selection(self, logged_in_admin, assembly_with_gsheet):
        """Test that cancel endpoint handles InvalidSelection error."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.cancel_task",
            side_effect=InvalidSelection("Cannot cancel completed task"),
        ):
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/replacement/{run_id}/cancel",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

            assert response.status_code == 302
            assert f"replacement/{run_id}" in response.location


class TestStartManageTabsList:
    """Test the start_manage_tabs_list endpoint."""

    def test_start_manage_tabs_list_success(self, logged_in_admin, assembly_with_gsheet):
        """Test that list tabs endpoint starts a dry-run task and redirects."""
        assembly, _gsheet = assembly_with_gsheet
        mock_task_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_manage_tabs_task",
            return_value=mock_task_id,
        ) as mock_start:
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/manage-tabs/start-list",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

            assert response.status_code == 302
            assert f"current_manage_tabs={mock_task_id}" in response.location
            # Verify dry_run=True was passed
            mock_start.assert_called_once()
            call_kwargs = mock_start.call_args
            assert call_kwargs[1].get("dry_run") is True or call_kwargs[0][3] is True

    def test_start_manage_tabs_list_not_found(self, logged_in_admin, assembly_with_gsheet):
        """Test that list tabs endpoint handles NotFoundError."""
        assembly, _gsheet = assembly_with_gsheet

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_manage_tabs_task",
            side_effect=NotFoundError("GSheet not found"),
        ):
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/manage-tabs/start-list",
                data={"csrf_token": csrf_token},
                follow_redirects=True,
            )
            assert response.status_code == 200


class TestStartManageTabsDelete:
    """Test the start_manage_tabs_delete endpoint."""

    def test_start_manage_tabs_delete_success(self, logged_in_admin, assembly_with_gsheet):
        """Test that delete tabs endpoint starts a non-dry-run task and redirects."""
        assembly, _gsheet = assembly_with_gsheet
        mock_task_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_manage_tabs_task",
            return_value=mock_task_id,
        ) as mock_start:
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/manage-tabs/start-delete",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

            assert response.status_code == 302
            assert f"current_manage_tabs={mock_task_id}" in response.location
            # Verify dry_run=False was passed
            mock_start.assert_called_once()
            call_kwargs = mock_start.call_args
            assert call_kwargs[1].get("dry_run") is False or call_kwargs[0][3] is False

    def test_start_manage_tabs_delete_not_found(self, logged_in_admin, assembly_with_gsheet):
        """Test that delete tabs endpoint handles NotFoundError."""
        assembly, _gsheet = assembly_with_gsheet

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.start_gsheet_manage_tabs_task",
            side_effect=NotFoundError("GSheet not found"),
        ):
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/manage-tabs/start-delete",
                data={"csrf_token": csrf_token},
                follow_redirects=True,
            )
            assert response.status_code == 200


class TestManageTabsProgress:
    """Test the manage_tabs_progress HTMX endpoint."""

    def test_manage_tabs_progress_returns_html_while_running(self, logged_in_admin, assembly_with_gsheet):
        """Test that manage tabs progress returns HTML with HTMX polling when task is running."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_record = _make_mock_run_record(
            assembly.id,
            task_type_verbose="List Old Tabs",
            task_type=SelectionTaskType.LIST_OLD_TABS,
        )
        mock_result = MagicMock(spec=TabManagementResult)
        mock_result.run_record = mock_record
        mock_result.log_messages = []
        mock_result.run_report = None
        mock_result.tab_names = []

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch("opendlp.entrypoints.blueprints.gsheets.get_selection_run_status", return_value=mock_result),
            patch(
                "opendlp.entrypoints.blueprints.gsheets.get_manage_old_tabs_status",
                return_value=ManageOldTabsStatus(ManageOldTabsState.LIST_RUNNING),
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/manage-tabs/{run_id}/progress")

            assert response.status_code == 200
            assert b"manage-tabs-progress-modal" in response.data
            assert b"hx-get" in response.data

    def test_manage_tabs_progress_shows_tab_names_when_list_completed(self, logged_in_admin, assembly_with_gsheet):
        """Test that manage tabs progress shows tab names when list task is completed."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_record = _make_mock_run_record(
            assembly.id,
            status="completed",
            completed_at=datetime.now(UTC),
            task_type_verbose="List Old Tabs",
            task_type=SelectionTaskType.LIST_OLD_TABS,
        )
        mock_result = MagicMock(spec=TabManagementResult)
        mock_result.run_record = mock_record
        mock_result.log_messages = []
        mock_result.run_report = None
        mock_result.tab_names = ["Old Tab 1", "Old Tab 2"]

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch("opendlp.entrypoints.blueprints.gsheets.get_selection_run_status", return_value=mock_result),
            patch(
                "opendlp.entrypoints.blueprints.gsheets.get_manage_old_tabs_status",
                return_value=ManageOldTabsStatus(ManageOldTabsState.LIST_COMPLETED),
            ),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/manage-tabs/{run_id}/progress")

            assert response.status_code == 200
            assert b"Old Tab 1" in response.data
            assert b"Old Tab 2" in response.data
            # Should not poll when finished
            assert b"hx-get" not in response.data

    def test_manage_tabs_progress_returns_404_when_not_found(self, logged_in_admin, assembly_with_gsheet):
        """Test that manage tabs progress returns 404 when run record not found."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_result = _make_mock_result(None)

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch("opendlp.entrypoints.blueprints.gsheets.get_selection_run_status", return_value=mock_result),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/manage-tabs/{run_id}/progress")
            assert response.status_code == 404

    def test_manage_tabs_progress_returns_404_wrong_assembly(self, logged_in_admin, assembly_with_gsheet):
        """Test that manage tabs progress returns 404 when run belongs to different assembly."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        mock_record = _make_mock_run_record(uuid.uuid4())  # different assembly
        mock_result = _make_mock_result(mock_record)

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch("opendlp.entrypoints.blueprints.gsheets.get_selection_run_status", return_value=mock_result),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/manage-tabs/{run_id}/progress")
            assert response.status_code == 404

    def test_manage_tabs_progress_returns_403_no_permission(self, logged_in_admin, existing_assembly):
        """Test that manage tabs progress returns 403 when user lacks permission."""
        run_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.get_assembly_with_permissions",
            side_effect=InsufficientPermissions("No access"),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/manage-tabs/{run_id}/progress")
            assert response.status_code == 403


class TestCancelManageTabs:
    """Test the cancel_manage_tabs endpoint."""

    def test_cancel_manage_tabs_success(self, logged_in_admin, assembly_with_gsheet):
        """Test that cancel manage tabs cancels the task and redirects."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        with patch("opendlp.entrypoints.blueprints.gsheets.cancel_task") as mock_cancel:
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/manage-tabs/{run_id}/cancel",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

            assert response.status_code == 302
            assert f"current_manage_tabs={run_id}" in response.location
            mock_cancel.assert_called_once()

    def test_cancel_manage_tabs_not_found(self, logged_in_admin, assembly_with_gsheet):
        """Test that cancel manage tabs handles NotFoundError."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.cancel_task",
            side_effect=NotFoundError("Task not found"),
        ):
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/manage-tabs/{run_id}/cancel",
                data={"csrf_token": csrf_token},
                follow_redirects=True,
            )
            assert response.status_code == 200

    def test_cancel_manage_tabs_invalid_selection(self, logged_in_admin, assembly_with_gsheet):
        """Test that cancel manage tabs handles InvalidSelection error."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()

        with patch(
            "opendlp.entrypoints.blueprints.gsheets.cancel_task",
            side_effect=InvalidSelection("Cannot cancel completed task"),
        ):
            csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly.id}/manage-tabs/{run_id}/cancel",
                data={"csrf_token": csrf_token},
                follow_redirects=True,
            )
            assert response.status_code == 200


class TestSelectionPageWithManageTabsContext:
    """Test view_assembly_selection with current_manage_tabs param for _get_manage_tabs_context coverage."""

    def test_selection_page_with_running_manage_tabs_shows_modal(self, logged_in_admin, assembly_with_gsheet):
        """Test that selection page with current_manage_tabs param shows the manage tabs modal."""
        assembly, _gsheet = assembly_with_gsheet
        task_id = uuid.uuid4()

        mock_record = _make_mock_run_record(
            assembly.id,
            task_type_verbose="List Old Tabs",
            task_type=SelectionTaskType.LIST_OLD_TABS,
        )
        mock_result = MagicMock(spec=TabManagementResult)
        mock_result.run_record = mock_record
        mock_result.log_messages = []
        mock_result.run_report = None
        mock_result.tab_names = []

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch("opendlp.entrypoints.blueprints.gsheets.get_selection_run_status", return_value=mock_result),
            patch(
                "opendlp.entrypoints.blueprints.gsheets.get_manage_old_tabs_status",
                return_value=ManageOldTabsStatus(ManageOldTabsState.LIST_RUNNING),
            ),
        ):
            response = logged_in_admin.get(
                f"/backoffice/assembly/{assembly.id}/selection?current_manage_tabs={task_id}"
            )

            assert response.status_code == 200
            assert b"manage-tabs-progress-modal" in response.data

    def test_selection_page_with_completed_manage_tabs_shows_tab_names(self, logged_in_admin, assembly_with_gsheet):
        """Test that selection page shows tab names when manage tabs list is completed."""
        assembly, _gsheet = assembly_with_gsheet
        task_id = uuid.uuid4()

        mock_record = _make_mock_run_record(
            assembly.id,
            status="completed",
            completed_at=datetime.now(UTC),
            task_type_verbose="List Old Tabs",
            task_type=SelectionTaskType.LIST_OLD_TABS,
        )
        mock_result = MagicMock(spec=TabManagementResult)
        mock_result.run_record = mock_record
        mock_result.log_messages = []
        mock_result.run_report = None
        mock_result.tab_names = ["Selection_2024-01-01", "Remaining_2024-01-01"]

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch("opendlp.entrypoints.blueprints.gsheets.get_selection_run_status", return_value=mock_result),
            patch(
                "opendlp.entrypoints.blueprints.gsheets.get_manage_old_tabs_status",
                return_value=ManageOldTabsStatus(ManageOldTabsState.LIST_COMPLETED),
            ),
        ):
            response = logged_in_admin.get(
                f"/backoffice/assembly/{assembly.id}/selection?current_manage_tabs={task_id}"
            )

            assert response.status_code == 200
            assert b"Selection_2024-01-01" in response.data
            assert b"Remaining_2024-01-01" in response.data

    def test_selection_page_with_invalid_manage_tabs_param_loads_normally(self, logged_in_admin, assembly_with_gsheet):
        """Test that invalid manage_tabs param is ignored and page loads normally."""
        assembly, _gsheet = assembly_with_gsheet

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection?current_manage_tabs=not-a-uuid")
        assert response.status_code == 200
        # Modal should NOT appear because the param is invalid
        assert b"manage-tabs-progress-modal" not in response.data

    def test_selection_page_with_wrong_assembly_manage_tabs_ignored(self, logged_in_admin, assembly_with_gsheet):
        """Test that manage tabs param for a different assembly is ignored."""
        assembly, _gsheet = assembly_with_gsheet
        task_id = uuid.uuid4()

        mock_record = _make_mock_run_record(
            uuid.uuid4(),  # different assembly
            task_type=SelectionTaskType.LIST_OLD_TABS,
        )
        mock_result = _make_mock_result(mock_record)

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch("opendlp.entrypoints.blueprints.gsheets.get_selection_run_status", return_value=mock_result),
        ):
            response = logged_in_admin.get(
                f"/backoffice/assembly/{assembly.id}/selection?current_manage_tabs={task_id}"
            )

            assert response.status_code == 200
            # Modal should NOT appear because the task belongs to a different assembly
            assert b"manage-tabs-progress-modal" not in response.data


class TestSelectionPageWithReplacementContext:
    """Test view_assembly_selection with current_replacement param for _get_replacement_modal_context coverage."""

    def test_selection_page_with_running_replacement_shows_modal(self, logged_in_admin, assembly_with_gsheet):
        """Test that selection page with current_replacement param shows the replacement modal."""
        assembly, _gsheet = assembly_with_gsheet
        task_id = uuid.uuid4()

        mock_record = _make_mock_run_record(
            assembly.id,
            task_type_verbose="Load Replacement Google Spreadsheet",
            task_type=SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
        )
        mock_result = _make_mock_result(mock_record, log_messages=["Loading replacement data..."])

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch("opendlp.entrypoints.blueprints.gsheets.get_selection_run_status", return_value=mock_result),
        ):
            response = logged_in_admin.get(
                f"/backoffice/assembly/{assembly.id}/selection?current_replacement={task_id}"
            )

            assert response.status_code == 200
            assert b"replacement-modal" in response.data

    def test_selection_page_with_completed_replacement_load_shows_min_max(self, logged_in_admin, assembly_with_gsheet):
        """Test that completed replacement load shows min/max selection from features."""
        assembly, _gsheet = assembly_with_gsheet
        task_id = uuid.uuid4()

        mock_record = _make_mock_run_record(
            assembly.id,
            status="completed",
            completed_at=datetime.now(UTC),
            task_type_verbose="Load Replacement Google Spreadsheet",
            task_type=SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
        )

        mock_features = MagicMock()
        mock_result = LoadRunResult(
            run_record=mock_record,
            log_messages=["Data loaded"],
            success=True,
            features=mock_features,
            people=None,
        )

        with (
            patch("opendlp.entrypoints.blueprints.gsheets.check_and_update_task_health"),
            patch("opendlp.entrypoints.blueprints.gsheets.get_selection_run_status", return_value=mock_result),
            patch("opendlp.entrypoints.blueprints.gsheets.minimum_selection", return_value=3),
            patch("opendlp.entrypoints.blueprints.gsheets.maximum_selection", return_value=15),
        ):
            response = logged_in_admin.get(
                f"/backoffice/assembly/{assembly.id}/selection?current_replacement={task_id}"
            )

            assert response.status_code == 200
            assert b"replacement-modal" in response.data
            # Should show available replacements range from features
            assert b"3" in response.data
            assert b"15" in response.data

    def test_selection_page_with_invalid_replacement_param_loads_normally(self, logged_in_admin, assembly_with_gsheet):
        """Test that invalid replacement param is ignored and page loads normally."""
        assembly, _gsheet = assembly_with_gsheet

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection?current_replacement=not-a-uuid")
        assert response.status_code == 200
        # Replacement modal should NOT appear
        assert b"replacement-modal" not in response.data

    def test_selection_page_replacement_modal_open_param(self, logged_in_admin, assembly_with_gsheet):
        """Test that replacement_modal=open param opens the replacement modal."""
        assembly, _gsheet = assembly_with_gsheet

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection?replacement_modal=open")

        assert response.status_code == 200
        assert b"replacement-modal" in response.data
