"""ABOUTME: End-to-end tests for backoffice DB selection routes
ABOUTME: Tests DB selection check, run, progress modal, cancel, and download endpoints"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import RespondentStatus, SelectionRunStatus, SelectionTaskType
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
    """Create an assembly with CSV config and data but settings NOT confirmed."""
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

    # Upload targets CSV (needed for data_source detection)
    targets_csv = "feature,value,min,max\nGender,Male,4,6\nGender,Female,4,6"
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly_service.import_targets_from_csv(uow, admin_user.id, assembly_id, targets_csv)

    # Upload respondents CSV (needed for data_source detection)
    respondents_csv = "external_id,Gender\n1,Male\n2,Female"
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        respondent_service.import_respondents_from_csv(uow, admin_user.id, assembly_id, respondents_csv)

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        a = uow.assemblies.get(assembly_id)
        return a.create_detached_copy()


class TestCsvSelectionCheckData:
    """Tests for the CSV check data endpoint."""

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.check_db_selection_data")
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
            f"/backoffice/assembly/{assembly.id}/selection/db/check",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Data validation passed" in response.data
        assert b"5 targets" in response.data
        assert b"50 respondents" in response.data

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.check_db_selection_data")
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
            f"/backoffice/assembly/{assembly.id}/selection/db/check",
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
            f"/backoffice/assembly/{assembly.id}/selection/db/check",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"review and save" in response.data.lower() or b"settings" in response.data.lower()

    def test_check_csv_data_requires_auth(self, client, assembly_with_csv_config):
        """Test that check endpoint requires authentication."""
        assembly = assembly_with_csv_config
        response = client.post(f"/backoffice/assembly/{assembly.id}/selection/db/check")

        assert response.status_code == 302
        assert "login" in response.location


class TestCsvSelectionRun:
    """Tests for the CSV selection run endpoint."""

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.start_db_select_task")
    def test_start_csv_selection_success(self, mock_start, logged_in_admin, assembly_with_csv_config):
        """Test successfully starting a CSV selection task."""
        assembly = assembly_with_csv_config
        mock_task_id = uuid.uuid4()
        mock_start.return_value = mock_task_id

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/db/run",
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

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.start_db_select_task")
    def test_start_csv_test_selection_success(self, mock_start, logged_in_admin, assembly_with_csv_config):
        """Test successfully starting a CSV test selection task."""
        assembly = assembly_with_csv_config
        mock_task_id = uuid.uuid4()
        mock_start.return_value = mock_task_id

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/db/run?test=1",
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
            f"/backoffice/assembly/{assembly.id}/selection/db/run",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"review and save" in response.data.lower() or b"settings" in response.data.lower()

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.start_db_select_task")
    def test_start_csv_selection_handles_invalid_selection_error(
        self, mock_start, logged_in_admin, assembly_with_csv_config
    ):
        """Test that InvalidSelection error is handled gracefully."""
        assembly = assembly_with_csv_config
        mock_start.side_effect = InvalidSelection("No respondents available")

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/db/run",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"No respondents available" in response.data

    def test_start_csv_selection_requires_auth(self, client, assembly_with_csv_config):
        """Test that run endpoint requires authentication."""
        assembly = assembly_with_csv_config
        response = client.post(f"/backoffice/assembly/{assembly.id}/selection/db/run")

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

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/db/modal-progress/{run_id}")

        assert response.status_code == 200
        # Modal should be present
        assert b"db-selection-progress-modal" in response.data
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

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/db/modal-progress/{run_id}")

        assert response.status_code == 200
        assert b"hx-get" not in response.data

    def test_progress_modal_returns_404_when_not_found(self, logged_in_admin, assembly_with_csv_config):
        """Test that progress modal returns 404 for non-existent task."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/db/modal-progress/{run_id}")

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

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/db/modal-progress/{run_id}")

        assert response.status_code == 404


class TestCsvSelectionCancel:
    """Tests for the CSV selection cancel endpoint."""

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.cancel_task")
    def test_cancel_csv_selection_success(self, mock_cancel, logged_in_admin, assembly_with_csv_config):
        """Test successfully cancelling a running CSV selection task."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/cancel",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "selection" in response.location
        mock_cancel.assert_called_once()

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.cancel_task")
    def test_cancel_csv_selection_handles_invalid_selection(
        self, mock_cancel, logged_in_admin, assembly_with_csv_config
    ):
        """Test that cancelling a completed task handles error gracefully."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        mock_cancel.side_effect = InvalidSelection("Cannot cancel completed task")

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/cancel",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Cannot cancel" in response.data

    def test_cancel_csv_selection_requires_auth(self, client, assembly_with_csv_config):
        """Test that cancel endpoint requires authentication."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        response = client.post(f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/cancel")

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

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/selected")

        assert response.status_code == 200
        assert response.content_type == "text/csv; charset=utf-8"
        assert f"selected-{run_id}.csv" in response.headers["Content-Disposition"]
        assert response.data.startswith("﻿".encode())

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

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/remaining")

        assert response.status_code == 200
        assert response.content_type == "text/csv; charset=utf-8"
        assert f"remaining-{run_id}.csv" in response.headers["Content-Disposition"]
        assert response.data.startswith("﻿".encode())

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.generate_selection_csvs")
    def test_download_handles_not_found_error(self, mock_generate, logged_in_admin, assembly_with_csv_config):
        """Test that NotFoundError redirects with error message."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        mock_generate.side_effect = NotFoundError("Run not found")

        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/selected",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"not found" in response.data.lower()

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.generate_selection_csvs")
    def test_download_handles_invalid_selection_error(self, mock_generate, logged_in_admin, assembly_with_csv_config):
        """Test that InvalidSelection error redirects with error message."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        mock_generate.side_effect = InvalidSelection("Selection not completed")

        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/selected",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Selection not completed" in response.data

    def test_download_requires_auth(self, client, assembly_with_csv_config):
        """Test that download endpoints require authentication."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        response = client.get(f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/selected")
        assert response.status_code == 302
        assert "login" in response.location

        response = client.get(f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/remaining")
        assert response.status_code == 302
        assert "login" in response.location


class TestSelectionReportDownload:
    """Tests for the selection summary report download endpoint."""

    def _completed_run_with_targets(
        self,
        postgres_session_factory,
        assembly_id,
    ):
        run_id = uuid.uuid4()
        snapshot = [
            {
                "name": "Gender",
                "description": "",
                "sort_order": 0,
                "values": [
                    {
                        "value": "Male",
                        "min": 4,
                        "max": 6,
                        "min_flex": 0,
                        "max_flex": -1,
                        "percentage_target": 50.0,
                        "description": "",
                    },
                    {
                        "value": "Female",
                        "min": 4,
                        "max": 6,
                        "min_flex": 0,
                        "max_flex": -1,
                        "percentage_target": 50.0,
                        "description": "",
                    },
                ],
            },
            {
                "name": "Age",
                "description": "",
                "sort_order": 1,
                "values": [
                    {
                        "value": "18-30",
                        "min": 3,
                        "max": 5,
                        "min_flex": 0,
                        "max_flex": -1,
                        "percentage_target": 40.0,
                        "description": "",
                    },
                    {
                        "value": "31-50",
                        "min": 3,
                        "max": 5,
                        "min_flex": 0,
                        "max_flex": -1,
                        "percentage_target": 40.0,
                        "description": "",
                    },
                    {
                        "value": "51+",
                        "min": 2,
                        "max": 4,
                        "min_flex": 0,
                        "max_flex": -1,
                        "percentage_target": 20.0,
                        "description": "",
                    },
                ],
            },
        ]
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=run_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                selected_ids=[["1", "3", "5", "7", "9"]],
                remaining_ids=["2", "4", "6", "8", "10"],
                targets_used=snapshot,
                completed_at=datetime.now(UTC),
            )
            uow.selection_run_records.add(record)
            uow.commit()
        return run_id

    def test_download_report_success(
        self,
        logged_in_admin,
        assembly_with_csv_config,
        postgres_session_factory,
    ):
        assembly = assembly_with_csv_config
        run_id = self._completed_run_with_targets(postgres_session_factory, assembly.id)

        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/report",
        )

        assert response.status_code == 200
        assert response.content_type == "text/csv; charset=utf-8"
        assert f"selection-report-{run_id}.csv" in response.headers["Content-Disposition"]
        assert response.data.startswith("﻿".encode())
        assert b"CSV Selection Assembly" in response.data
        assert b"Gender" in response.data
        assert b"Age" in response.data

    def test_download_report_when_targets_empty_redirects(
        self,
        logged_in_admin,
        assembly_with_csv_config,
        postgres_session_factory,
    ):
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly.id,
                    task_id=run_id,
                    status=SelectionRunStatus.COMPLETED,
                    task_type=SelectionTaskType.SELECT_FROM_DB,
                    selected_ids=[["1"]],
                    remaining_ids=["2"],
                    targets_used=[],
                    completed_at=datetime.now(UTC),
                ),
            )
            uow.commit()

        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/report",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"no target snapshot" in response.data.lower()

    def test_download_report_unknown_run_redirects(
        self,
        logged_in_admin,
        assembly_with_csv_config,
    ):
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/report",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"not found" in response.data.lower()

    def test_download_report_requires_auth(self, client, assembly_with_csv_config):
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        response = client.get(f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/report")
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

    def test_selection_page_shows_view_running_button_when_db_task_running(
        self, logged_in_admin, assembly_with_csv_config, postgres_session_factory
    ):
        """When a SELECT_FROM_DB task is running, the Initial Selection card shows
        'View Running Selection' instead of the check/test/run buttons."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly.id,
                    task_id=run_id,
                    status=SelectionRunStatus.RUNNING,
                    task_type=SelectionTaskType.SELECT_FROM_DB,
                )
            )
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"View Running Selection" in response.data
        assert f"current_selection={run_id}".encode() in response.data
        # The check/test/run button forms should not be rendered
        assert f"/backoffice/assembly/{assembly.id}/selection/db/check".encode() not in response.data
        assert f"/backoffice/assembly/{assembly.id}/selection/db/start".encode() not in response.data

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
        assert b"db-selection-progress-modal" in response.data


class TestCsvSelectionReset:
    """Tests for the CSV selection reset endpoint."""

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.reset_selection_status")
    def test_reset_csv_selection_success(self, mock_reset, logged_in_admin, assembly_with_csv_config):
        """Test successfully resetting respondents to Pool status."""
        assembly = assembly_with_csv_config
        mock_reset.return_value = 10  # 10 respondents reset

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/db/reset",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Reset 10 respondents" in response.data
        mock_reset.assert_called_once()

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.reset_selection_status")
    def test_reset_csv_selection_handles_not_found(self, mock_reset, logged_in_admin, assembly_with_csv_config):
        """Test that NotFoundError redirects to dashboard."""
        assembly = assembly_with_csv_config
        mock_reset.side_effect = NotFoundError("Assembly not found")

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/selection")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/db/reset",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"not found" in response.data.lower()

    def test_reset_csv_selection_requires_auth(self, client, assembly_with_csv_config):
        """Test that reset endpoint requires authentication."""
        assembly = assembly_with_csv_config
        response = client.post(f"/backoffice/assembly/{assembly.id}/selection/db/reset")

        assert response.status_code == 302
        assert "login" in response.location


class TestCsvSelectionSelectedCount:
    """Tests for CSV selection page showing selected count and reset button."""

    def test_selection_page_shows_selected_count_when_respondents_selected(
        self, logged_in_admin, assembly_with_csv_config, postgres_session_factory
    ):
        """Test that selection page shows selected count when respondents have been selected."""
        assembly = assembly_with_csv_config

        # Mark some respondents as selected (not Pool)
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondents = uow.respondents.get_by_assembly_id(assembly.id)
            # Mark 5 respondents as selected
            for respondent in respondents[:5]:
                respondent.selection_status = RespondentStatus.SELECTED
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        # Should show warning about selected respondents
        assert b"5 respondents have been selected" in response.data
        # Should show reset button
        assert b"Reset Selected People" in response.data
        # Should NOT show Run Selection button (only Reset and Check Data)
        assert b"Run Selection" not in response.data

    def test_selection_page_shows_normal_ui_when_no_selection(self, logged_in_admin, assembly_with_csv_config):
        """Test that selection page shows normal UI when no selection has been run."""
        assembly = assembly_with_csv_config

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        # Should NOT show reset button
        assert b"Reset Selected People" not in response.data
        # Should show Run Selection buttons
        assert b"Run Selection" in response.data
        assert b"Run Test Selection" in response.data


class TestSaveCsvSettings:
    """Tests for the save CSV settings endpoint."""

    def test_save_csv_settings_success(self, logged_in_admin, assembly_with_csv_config_unconfirmed):
        """Test successfully saving CSV selection settings."""
        assembly = assembly_with_csv_config_unconfirmed

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/data?source=csv")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/data/csv/settings",
            data={
                "csrf_token": csrf_token,
                # check_same_address not included = False (no address columns required)
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "Gender",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Selection settings saved successfully" in response.data

    def test_save_csv_settings_with_address_columns(self, logged_in_admin, assembly_with_csv_config_unconfirmed):
        """Test saving settings with address columns specified."""
        assembly = assembly_with_csv_config_unconfirmed

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/data?source=csv")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/data/csv/settings",
            data={
                "csrf_token": csrf_token,
                "check_same_address": "y",
                "check_same_address_cols_string": "Gender",
                "columns_to_keep_string": "Gender",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Selection settings saved successfully" in response.data

    def test_save_csv_settings_without_check_address(self, logged_in_admin, assembly_with_csv_config_unconfirmed):
        """Test saving settings with check_same_address disabled."""
        assembly = assembly_with_csv_config_unconfirmed

        csrf_token = get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly.id}/data?source=csv")
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/data/csv/settings",
            data={
                "csrf_token": csrf_token,
                # check_same_address not included = False
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Selection settings saved successfully" in response.data

    def test_save_csv_settings_requires_auth(self, client, assembly_with_csv_config_unconfirmed):
        """Test that save settings endpoint requires authentication."""
        assembly = assembly_with_csv_config_unconfirmed
        response = client.post(f"/backoffice/assembly/{assembly.id}/data/csv/settings")

        assert response.status_code == 302
        assert "login" in response.location


class TestCsvSelectionSettingsWarning:
    """Tests for CSV selection settings confirmation warning."""

    def test_selection_page_shows_warning_when_settings_not_confirmed(
        self, logged_in_admin, assembly_with_csv_config_unconfirmed
    ):
        """Test that selection page shows warning when settings are not confirmed."""
        assembly = assembly_with_csv_config_unconfirmed

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        # Should show warning message
        assert b"review and save the selection settings" in response.data
        # Should have link to data settings in edit mode with anchor
        assert b"Go to Data Settings" in response.data
        assert b"source=csv" in response.data
        assert b"mode=edit" in response.data
        assert b"#selection-settings" in response.data

    def test_selection_page_buttons_disabled_when_settings_not_confirmed(
        self, logged_in_admin, assembly_with_csv_config_unconfirmed
    ):
        """Test that selection buttons are disabled when settings are not confirmed."""
        assembly = assembly_with_csv_config_unconfirmed

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        # Buttons should be disabled - check for disabled attribute in HTML
        assert b"disabled" in response.data

    def test_selection_page_no_warning_when_settings_confirmed(self, logged_in_admin, assembly_with_csv_config):
        """Test that selection page does not show warning when settings are confirmed."""
        assembly = assembly_with_csv_config

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        # Should NOT show warning message
        assert b"review and save the selection settings" not in response.data


class TestCsvSelectionHistory:
    """Tests for CSV selection history display."""

    def test_selection_page_shows_history_section(self, logged_in_admin, assembly_with_csv_config):
        """Test that CSV selection page shows the Selection History section."""
        assembly = assembly_with_csv_config

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"Selection History" in response.data
        # Empty state message when no history
        assert b"No selection runs yet" in response.data

    def test_selection_page_shows_history_with_runs(
        self, logged_in_admin, assembly_with_csv_config, postgres_session_factory, admin_user
    ):
        """Test that CSV selection page shows selection runs in history table."""
        assembly = assembly_with_csv_config

        # Create a completed selection run
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=uuid.uuid4(),
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                user_id=admin_user.id,
                completed_at=datetime.now(UTC),
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"Selection History" in response.data
        # Should show completed status
        assert b"Completed" in response.data
        # Should have View action link
        assert b"View" in response.data
