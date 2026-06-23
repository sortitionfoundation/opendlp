"""ABOUTME: End-to-end smokes for backoffice DB selection routes
ABOUTME: Real-CSRF POST smokes plus Celery dispatch/cancel seams and real CSV/report generation"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer import assembly_service, respondent_service
from opendlp.service_layer.assembly_service import create_assembly, update_csv_config, update_selection_settings
from opendlp.service_layer.exceptions import InvalidSelection
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
    """CSRF-exercising smoke for the CSV check data endpoint."""

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


class TestCsvSelectionRun:
    """Celery dispatch seam for the CSV selection run endpoint."""

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


class TestCsvSelectionCancel:
    """Celery revoke seam for the CSV selection cancel endpoint."""

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


class TestCsvSelectionDownload:
    """Real end-to-end CSV download smokes from a persisted SelectionRunRecord."""

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


class TestSelectionReportDownload:
    """Real end-to-end selection summary report download smoke."""

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


class TestSaveCsvSettings:
    """CSRF-exercising smoke for the save CSV settings endpoint."""

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
