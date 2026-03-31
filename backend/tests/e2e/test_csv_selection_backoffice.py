"""ABOUTME: End-to-end tests for backoffice CSV selection routes
ABOUTME: Tests CSV selection check, run, progress modal, cancel, and download endpoints"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer import assembly_service, respondent_service
from opendlp.service_layer.assembly_service import create_assembly, update_csv_config, update_selection_settings
from opendlp.service_layer.exceptions import InvalidSelection, NotFoundError
from opendlp.service_layer.sortition import CheckDataResult
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token


@pytest.fixture
def assembly_with_csv_config(postgres_session_factory, admin_user):
    """Create an assembly configured for CSV selection with settings confirmed and data uploaded."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="CSV Selection Assembly",
            created_by_user_id=admin_user.id,
            question="What should we select?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            number_to_select=10,
        )
        assembly_id = assembly.id

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        update_selection_settings(
            uow=uow,
            user_id=admin_user.id,
            assembly_id=assembly_id,
            check_same_address=False,
        )

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        update_csv_config(
            uow=uow,
            user_id=admin_user.id,
            assembly_id=assembly_id,
            settings_confirmed=True,
        )

    # Upload targets CSV
    targets_csv = "feature,value,min,max\nGender,Male,4,6\nGender,Female,4,6\nAge,18-30,3,5\nAge,31-50,3,5\nAge,51+,2,4"
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly_service.import_targets_from_csv(uow, admin_user.id, assembly_id, targets_csv)

    # Upload respondents CSV
    respondents_csv = """external_id,Gender,Age
1,Male,18-30
2,Female,31-50
3,Male,51+
4,Female,18-30
5,Male,31-50
6,Female,51+
7,Male,18-30
8,Female,31-50
9,Male,51+
10,Female,18-30
"""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        respondent_service.import_respondents_from_csv(uow, admin_user.id, assembly_id, respondents_csv)

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        a = uow.assemblies.get(assembly_id)
        return a.create_detached_copy()


@pytest.fixture
def assembly_with_csv_config_unconfirmed(postgres_session_factory, admin_user):
    """Create an assembly with CSV config but settings NOT confirmed."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="CSV Selection Assembly Unconfirmed",
            created_by_user_id=admin_user.id,
            question="What should we select?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            number_to_select=10,
        )
        assembly_id = assembly.id

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        update_selection_settings(
            uow=uow,
            user_id=admin_user.id,
            assembly_id=assembly_id,
            check_same_address=False,
        )

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        update_csv_config(
            uow=uow,
            user_id=admin_user.id,
            assembly_id=assembly_id,
            settings_confirmed=False,
        )

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        a = uow.assemblies.get(assembly_id)
        return a.create_detached_copy()


class TestCsvSelectionCheckData:
    """Tests for the CSV check data endpoint."""

    @patch("opendlp.entrypoints.blueprints.csv_selection_backoffice.check_db_selection_data")
    def test_check_csv_data_success(self, mock_check, logged_in_admin, assembly_with_csv_config):
        """Test successful data validation shows success message."""
        assembly = assembly_with_csv_config
        mock_check.return_value = CheckDataResult(
            success=True,
            errors=[],
            features_report_html="<p>Features OK</p>",
            people_report_html="<p>People OK</p>",
            num_features=5,
            num_people=50,
        )

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/csv/check",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Data validation passed" in response.data
        assert b"5 targets" in response.data
        assert b"50 respondents" in response.data

    @patch("opendlp.entrypoints.blueprints.csv_selection_backoffice.check_db_selection_data")
    def test_check_csv_data_failure(self, mock_check, logged_in_admin, assembly_with_csv_config):
        """Test failed data validation shows error messages."""
        assembly = assembly_with_csv_config
        mock_check.return_value = CheckDataResult(
            success=False,
            errors=["Missing target category: Age"],
            features_report_html="",
            people_report_html="",
            num_features=0,
            num_people=0,
        )

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/csv/check",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Missing target category" in response.data

    def test_check_csv_data_requires_settings_confirmed(self, logged_in_admin, assembly_with_csv_config_unconfirmed):
        """Test that check data requires settings to be confirmed first."""
        assembly = assembly_with_csv_config_unconfirmed

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/csv/check",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"review and save" in response.data.lower() or b"settings" in response.data.lower()

    def test_check_csv_data_requires_auth(self, client, assembly_with_csv_config):
        """Test that check endpoint requires authentication."""
        assembly = assembly_with_csv_config
        response = client.post(f"/backoffice/assembly/{assembly.id}/selection/csv/check")

        assert response.status_code == 302
        assert "login" in response.location


class TestCsvSelectionRun:
    """Tests for the CSV selection run endpoint."""

    @patch("opendlp.entrypoints.blueprints.csv_selection_backoffice.start_db_select_task")
    def test_start_csv_selection_success(self, mock_start, logged_in_admin, assembly_with_csv_config):
        """Test successfully starting a CSV selection task."""
        assembly = assembly_with_csv_config
        mock_task_id = uuid.uuid4()
        mock_start.return_value = mock_task_id

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/csv/run",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "selection" in response.location
        assert str(mock_task_id) in response.location
        mock_start.assert_called_once()
        # Verify test_selection=False was passed
        call_kwargs = mock_start.call_args[1] if mock_start.call_args[1] else {}
        assert call_kwargs.get("test_selection", False) is False

    @patch("opendlp.entrypoints.blueprints.csv_selection_backoffice.start_db_select_task")
    def test_start_csv_test_selection_success(self, mock_start, logged_in_admin, assembly_with_csv_config):
        """Test successfully starting a CSV test selection task."""
        assembly = assembly_with_csv_config
        mock_task_id = uuid.uuid4()
        mock_start.return_value = mock_task_id

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/csv/run?test=1",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        assert response.status_code == 302
        mock_start.assert_called_once()
        # Verify test_selection=True was passed
        call_kwargs = mock_start.call_args[1] if mock_start.call_args[1] else {}
        assert call_kwargs.get("test_selection", False) is True

    def test_start_csv_selection_requires_settings_confirmed(
        self, logged_in_admin, assembly_with_csv_config_unconfirmed
    ):
        """Test that run selection requires settings to be confirmed first."""
        assembly = assembly_with_csv_config_unconfirmed

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/csv/run",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"review and save" in response.data.lower() or b"settings" in response.data.lower()

    @patch("opendlp.entrypoints.blueprints.csv_selection_backoffice.start_db_select_task")
    def test_start_csv_selection_handles_invalid_selection_error(
        self, mock_start, logged_in_admin, assembly_with_csv_config
    ):
        """Test that InvalidSelection error is handled gracefully."""
        assembly = assembly_with_csv_config
        mock_start.side_effect = InvalidSelection("No respondents available")

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/csv/run",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"No respondents available" in response.data

    def test_start_csv_selection_requires_auth(self, client, assembly_with_csv_config):
        """Test that run endpoint requires authentication."""
        assembly = assembly_with_csv_config
        response = client.post(f"/backoffice/assembly/{assembly.id}/selection/csv/run")

        assert response.status_code == 302
        assert "login" in response.location


class TestCsvSelectionProgressModal:
    """Tests for the CSV selection progress modal endpoint."""

    def test_progress_modal_returns_html_for_running_task(
        self, logged_in_admin, assembly_with_csv_config, postgres_session_factory
    ):
        """Test that progress modal endpoint returns HTML for running tasks."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        # Create a running task record
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=run_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                log_messages=["Processing data..."],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/csv/modal-progress/{run_id}")

        assert response.status_code == 200
        # Modal should be present
        assert b"csv-selection-progress-modal" in response.data
        # Running status should enable HTMX polling
        assert b"hx-get" in response.data

    def test_progress_modal_no_htmx_when_completed(
        self, logged_in_admin, assembly_with_csv_config, postgres_session_factory
    ):
        """Test that completed tasks don't include HTMX polling (stops polling)."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=run_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                log_messages=["Done"],
                completed_at=datetime.now(UTC),
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/csv/modal-progress/{run_id}")

        assert response.status_code == 200
        assert b"hx-get" not in response.data

    def test_progress_modal_returns_404_when_not_found(self, logged_in_admin, assembly_with_csv_config):
        """Test that progress modal returns 404 for non-existent task."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/csv/modal-progress/{run_id}")

        assert response.status_code == 404

    def test_progress_modal_returns_404_for_wrong_assembly(
        self, logged_in_admin, assembly_with_csv_config, existing_assembly, postgres_session_factory
    ):
        """Test that progress modal returns 404 when task belongs to different assembly."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        # Create task for a different assembly
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=existing_assembly.id,  # Different assembly
                task_id=run_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.SELECT_FROM_DB,
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/csv/modal-progress/{run_id}")

        assert response.status_code == 404


class TestCsvSelectionCancel:
    """Tests for the CSV selection cancel endpoint."""

    @patch("opendlp.entrypoints.blueprints.csv_selection_backoffice.cancel_task")
    def test_cancel_csv_selection_success(self, mock_cancel, logged_in_admin, assembly_with_csv_config):
        """Test successfully cancelling a running CSV selection task."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/csv/{run_id}/cancel",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "selection" in response.location
        mock_cancel.assert_called_once()

    @patch("opendlp.entrypoints.blueprints.csv_selection_backoffice.cancel_task")
    def test_cancel_csv_selection_handles_invalid_selection(
        self, mock_cancel, logged_in_admin, assembly_with_csv_config
    ):
        """Test that cancelling a completed task handles error gracefully."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        mock_cancel.side_effect = InvalidSelection("Cannot cancel completed task")

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/csv/{run_id}/cancel",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Cannot cancel" in response.data

    def test_cancel_csv_selection_requires_auth(self, client, assembly_with_csv_config):
        """Test that cancel endpoint requires authentication."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        response = client.post(f"/backoffice/assembly/{assembly.id}/selection/csv/{run_id}/cancel")

        assert response.status_code == 302
        assert "login" in response.location


class TestCsvSelectionDownload:
    """Tests for the CSV selection download endpoints."""

    def test_download_selected_csv_success(self, logged_in_admin, assembly_with_csv_config, postgres_session_factory):
        """Test successfully downloading selected participants CSV."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        # Create a completed selection run with selected_ids
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=run_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                selected_ids=[["1", "2", "3"]],
                remaining_ids=["4", "5", "6"],
                completed_at=datetime.now(UTC),
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/csv/{run_id}/download/selected")

        assert response.status_code == 200
        assert response.content_type == "text/csv; charset=utf-8"
        assert f"selected-{run_id}.csv" in response.headers["Content-Disposition"]

    def test_download_remaining_csv_success(self, logged_in_admin, assembly_with_csv_config, postgres_session_factory):
        """Test successfully downloading remaining participants CSV."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        # Create a completed selection run with remaining_ids
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=run_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                selected_ids=[["1", "2", "3"]],
                remaining_ids=["4", "5", "6"],
                completed_at=datetime.now(UTC),
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/csv/{run_id}/download/remaining")

        assert response.status_code == 200
        assert response.content_type == "text/csv; charset=utf-8"
        assert f"remaining-{run_id}.csv" in response.headers["Content-Disposition"]

    @patch("opendlp.entrypoints.blueprints.csv_selection_backoffice.generate_selection_csvs")
    def test_download_handles_not_found_error(self, mock_generate, logged_in_admin, assembly_with_csv_config):
        """Test that NotFoundError redirects with error message."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        mock_generate.side_effect = NotFoundError("Run not found")

        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/selection/csv/{run_id}/download/selected",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"not found" in response.data.lower()

    @patch("opendlp.entrypoints.blueprints.csv_selection_backoffice.generate_selection_csvs")
    def test_download_handles_invalid_selection_error(self, mock_generate, logged_in_admin, assembly_with_csv_config):
        """Test that InvalidSelection error redirects with error message."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        mock_generate.side_effect = InvalidSelection("Selection not completed")

        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/selection/csv/{run_id}/download/selected",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Selection not completed" in response.data

    def test_download_requires_auth(self, client, assembly_with_csv_config):
        """Test that download endpoints require authentication."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        response = client.get(f"/backoffice/assembly/{assembly.id}/selection/csv/{run_id}/download/selected")
        assert response.status_code == 302
        assert "login" in response.location

        response = client.get(f"/backoffice/assembly/{assembly.id}/selection/csv/{run_id}/download/remaining")
        assert response.status_code == 302
        assert "login" in response.location


class TestCsvSelectionPageIntegration:
    """Tests for CSV selection page integration with the main selection template."""

    def test_selection_page_shows_csv_ui_when_csv_configured(self, logged_in_admin, assembly_with_csv_config):
        """Test that selection page shows CSV selection UI when CSV is configured."""
        assembly = assembly_with_csv_config

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"Initial Selection" in response.data
        assert b"Check Data" in response.data
        assert b"Run Test Selection" in response.data
        assert b"Run Selection" in response.data
        # Should not show gsheet-specific elements
        assert b"Check Spreadsheet" not in response.data

    def test_selection_page_shows_csv_progress_modal_when_running(
        self, logged_in_admin, assembly_with_csv_config, postgres_session_factory
    ):
        """Test that selection page with current_selection shows CSV progress modal."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=run_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                log_messages=["Running..."],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection?current_selection={run_id}")

        assert response.status_code == 200
        # CSV progress modal should be shown (not the gsheet one)
        assert b"csv-selection-progress-modal" in response.data
