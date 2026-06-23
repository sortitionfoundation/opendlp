# ABOUTME: Component tests for the backoffice DB selection blueprint over a FakeUnitOfWork
# ABOUTME: Drives the real DB selection routes + services (auth, render, validation, modal fragments, downloads, reset, history)

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from opendlp.adapters import database
from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import RespondentStatus, SelectionRunStatus, SelectionTaskType
from opendlp.service_layer import assembly_service, respondent_service
from opendlp.service_layer.assembly_service import create_assembly, update_csv_config, update_selection_settings
from opendlp.service_layer.exceptions import InvalidSelection, NotFoundError
from opendlp.service_layer.sortition import CheckDataResult
from tests.fakes import FakeUnitOfWork


@pytest.fixture(autouse=True)
def _mapped_domain_objects():
    """Settings/CSV-config writes call SQLAlchemy flag_modified, which needs mapped classes."""
    database.start_mappers()


@pytest.fixture
def assembly_with_csv_config(fake_store, admin_user):
    """Assembly configured for CSV selection with settings confirmed and data uploaded."""
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = create_assembly(
            uow=uow,
            title="CSV Selection Assembly",
            created_by_user_id=admin_user.id,
            question="What should we select?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            number_to_select=10,
        )
        assembly_id = assembly.id

    with FakeUnitOfWork(store=fake_store) as uow:
        update_selection_settings(
            uow=uow,
            user_id=admin_user.id,
            assembly_id=assembly_id,
            check_same_address=False,
        )

    with FakeUnitOfWork(store=fake_store) as uow:
        update_csv_config(
            uow=uow,
            user_id=admin_user.id,
            assembly_id=assembly_id,
            settings_confirmed=True,
        )

    targets_csv = "feature,value,min,max\nGender,Male,4,6\nGender,Female,4,6\nAge,18-30,3,5\nAge,31-50,3,5\nAge,51+,2,4"
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly_service.import_targets_from_csv(uow, admin_user.id, assembly_id, targets_csv)

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
    with FakeUnitOfWork(store=fake_store) as uow:
        respondent_service.import_respondents_from_csv(uow, admin_user.id, assembly_id, respondents_csv)

    with FakeUnitOfWork(store=fake_store) as uow:
        return uow.assemblies.get(assembly_id).create_detached_copy()


@pytest.fixture
def assembly_with_csv_config_unconfirmed(fake_store, admin_user):
    """Assembly with CSV config and data but settings NOT confirmed."""
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = create_assembly(
            uow=uow,
            title="CSV Selection Assembly Unconfirmed",
            created_by_user_id=admin_user.id,
            question="What should we select?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            number_to_select=10,
        )
        assembly_id = assembly.id

    with FakeUnitOfWork(store=fake_store) as uow:
        update_selection_settings(
            uow=uow,
            user_id=admin_user.id,
            assembly_id=assembly_id,
            check_same_address=False,
        )

    with FakeUnitOfWork(store=fake_store) as uow:
        update_csv_config(
            uow=uow,
            user_id=admin_user.id,
            assembly_id=assembly_id,
            settings_confirmed=False,
        )

    targets_csv = "feature,value,min,max\nGender,Male,4,6\nGender,Female,4,6"
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly_service.import_targets_from_csv(uow, admin_user.id, assembly_id, targets_csv)

    respondents_csv = "external_id,Gender\n1,Male\n2,Female"
    with FakeUnitOfWork(store=fake_store) as uow:
        respondent_service.import_respondents_from_csv(uow, admin_user.id, assembly_id, respondents_csv)

    with FakeUnitOfWork(store=fake_store) as uow:
        return uow.assemblies.get(assembly_id).create_detached_copy()


def _add_run_record(fake_store, **kwargs):
    """Seed a SelectionRunRecord into the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        record = SelectionRunRecord(**kwargs)
        uow.selection_run_records.add(record)
        uow.commit()
        return record


class TestCsvSelectionCheckData:
    """Tests for the CSV check data endpoint."""

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.check_db_selection_data")
    def test_check_csv_data_failure(self, mock_check, logged_in_admin, assembly_with_csv_config):
        """Failed data validation shows error messages."""
        assembly = assembly_with_csv_config
        mock_check.return_value = CheckDataResult(
            success=False,
            errors=["Missing target category: Age"],
            features_report_html="",
            people_report_html="",
            num_features=0,
            num_people=0,
        )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/db/check",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Missing target category" in response.data

    def test_check_csv_data_requires_settings_confirmed(self, logged_in_admin, assembly_with_csv_config_unconfirmed):
        """Check data requires settings to be confirmed first."""
        assembly = assembly_with_csv_config_unconfirmed

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/db/check",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"review and save" in response.data.lower() or b"settings" in response.data.lower()

    def test_check_csv_data_requires_auth(self, client, assembly_with_csv_config):
        """Check endpoint requires authentication."""
        assembly = assembly_with_csv_config
        response = client.post(f"/backoffice/assembly/{assembly.id}/selection/db/check")

        assert response.status_code == 302
        assert "login" in response.location


class TestCsvSelectionRun:
    """Tests for pre-dispatch validation on the CSV selection run endpoint."""

    def test_start_csv_selection_requires_settings_confirmed(
        self, logged_in_admin, assembly_with_csv_config_unconfirmed
    ):
        """Run selection requires settings to be confirmed first."""
        assembly = assembly_with_csv_config_unconfirmed

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/db/run",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"review and save" in response.data.lower() or b"settings" in response.data.lower()

    def test_start_csv_selection_requires_auth(self, client, assembly_with_csv_config):
        """Run endpoint requires authentication."""
        assembly = assembly_with_csv_config
        response = client.post(f"/backoffice/assembly/{assembly.id}/selection/db/run")

        assert response.status_code == 302
        assert "login" in response.location


class TestCsvSelectionProgressModal:
    """Tests for the CSV selection progress modal endpoint."""

    def test_progress_modal_returns_html_for_running_task(self, logged_in_admin, assembly_with_csv_config, fake_store):
        """Progress modal endpoint returns HTML for running tasks."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        _add_run_record(
            fake_store,
            assembly_id=assembly.id,
            task_id=run_id,
            status=SelectionRunStatus.RUNNING,
            task_type=SelectionTaskType.SELECT_FROM_DB,
            log_messages=["Processing data..."],
        )

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/db/modal-progress/{run_id}")

        assert response.status_code == 200
        assert b"db-selection-progress-modal" in response.data
        assert b"hx-get" in response.data

    def test_progress_modal_no_htmx_when_completed(self, logged_in_admin, assembly_with_csv_config, fake_store):
        """Completed tasks don't include HTMX polling (stops polling)."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        _add_run_record(
            fake_store,
            assembly_id=assembly.id,
            task_id=run_id,
            status=SelectionRunStatus.COMPLETED,
            task_type=SelectionTaskType.SELECT_FROM_DB,
            log_messages=["Done"],
            completed_at=datetime.now(UTC),
        )

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/db/modal-progress/{run_id}")

        assert response.status_code == 200
        assert b"hx-get" not in response.data

    def test_progress_modal_returns_404_when_not_found(self, logged_in_admin, assembly_with_csv_config):
        """Progress modal returns 404 for non-existent task."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/db/modal-progress/{run_id}")

        assert response.status_code == 404

    def test_progress_modal_returns_404_for_wrong_assembly(
        self, logged_in_admin, assembly_with_csv_config, existing_assembly, fake_store
    ):
        """Progress modal returns 404 when task belongs to a different assembly."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        _add_run_record(
            fake_store,
            assembly_id=existing_assembly.id,
            task_id=run_id,
            status=SelectionRunStatus.RUNNING,
            task_type=SelectionTaskType.SELECT_FROM_DB,
        )

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection/db/modal-progress/{run_id}")

        assert response.status_code == 404


class TestCsvSelectionCancel:
    """Tests for authentication on the CSV selection cancel endpoint."""

    def test_cancel_csv_selection_requires_auth(self, client, assembly_with_csv_config):
        """Cancel endpoint requires authentication."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        response = client.post(f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/cancel")

        assert response.status_code == 302
        assert "login" in response.location


class TestCsvSelectionDownload:
    """Tests for the CSV selection download error branches and auth."""

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.generate_selection_csvs")
    def test_download_handles_not_found_error(self, mock_generate, logged_in_admin, assembly_with_csv_config):
        """NotFoundError redirects with error message."""
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
        """InvalidSelection error redirects with error message."""
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
        """Download endpoints require authentication."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        response = client.get(f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/selected")
        assert response.status_code == 302
        assert "login" in response.location

        response = client.get(f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/remaining")
        assert response.status_code == 302
        assert "login" in response.location


class TestSelectionReportDownload:
    """Tests for the selection summary report download error branches and auth."""

    def test_download_report_when_targets_empty_redirects(self, logged_in_admin, assembly_with_csv_config, fake_store):
        """A completed run with no target snapshot redirects with an error."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        _add_run_record(
            fake_store,
            assembly_id=assembly.id,
            task_id=run_id,
            status=SelectionRunStatus.COMPLETED,
            task_type=SelectionTaskType.SELECT_FROM_DB,
            selected_ids=[["1"]],
            remaining_ids=["2"],
            targets_used=[],
            completed_at=datetime.now(UTC),
        )

        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/report",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"no target snapshot" in response.data.lower()

    def test_download_report_unknown_run_redirects(self, logged_in_admin, assembly_with_csv_config):
        """An unknown run redirects with a not-found error."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/report",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"not found" in response.data.lower()

    def test_download_report_requires_auth(self, client, assembly_with_csv_config):
        """Report download requires authentication."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()

        response = client.get(f"/backoffice/assembly/{assembly.id}/selection/db/{run_id}/download/report")
        assert response.status_code == 302
        assert "login" in response.location


class TestCsvSelectionPageIntegration:
    """Tests for CSV selection page integration with the main selection template."""

    def test_selection_page_shows_csv_ui_when_csv_configured(self, logged_in_admin, assembly_with_csv_config):
        """Selection page shows CSV selection UI when CSV is configured."""
        assembly = assembly_with_csv_config

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"Initial Selection" in response.data
        assert b"Check Data" in response.data
        assert b"Run Test Selection" in response.data
        assert b"Run Selection" in response.data
        assert b"Check Spreadsheet" not in response.data

    def test_selection_page_shows_view_running_button_when_db_task_running(
        self, logged_in_admin, assembly_with_csv_config, fake_store
    ):
        """When a SELECT_FROM_DB task is running, the Initial Selection card shows
        'View Running Selection' instead of the check/test/run buttons."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        _add_run_record(
            fake_store,
            assembly_id=assembly.id,
            task_id=run_id,
            status=SelectionRunStatus.RUNNING,
            task_type=SelectionTaskType.SELECT_FROM_DB,
        )

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"View Running Selection" in response.data
        assert f"current_selection={run_id}".encode() in response.data
        assert f"/backoffice/assembly/{assembly.id}/selection/db/check".encode() not in response.data
        assert f"/backoffice/assembly/{assembly.id}/selection/db/start".encode() not in response.data

    def test_selection_page_shows_csv_progress_modal_when_running(
        self, logged_in_admin, assembly_with_csv_config, fake_store
    ):
        """Selection page with current_selection shows the CSV progress modal."""
        assembly = assembly_with_csv_config
        run_id = uuid.uuid4()
        _add_run_record(
            fake_store,
            assembly_id=assembly.id,
            task_id=run_id,
            status=SelectionRunStatus.RUNNING,
            task_type=SelectionTaskType.SELECT_FROM_DB,
            log_messages=["Running..."],
        )

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection?current_selection={run_id}")

        assert response.status_code == 200
        assert b"db-selection-progress-modal" in response.data


class TestCsvSelectionReset:
    """Tests for the CSV selection reset endpoint, asserting FakeStore state."""

    def test_reset_csv_selection_success(self, logged_in_admin, assembly_with_csv_config, fake_store, admin_user):
        """Resetting moves all selected respondents back to POOL status."""
        assembly = assembly_with_csv_config

        with FakeUnitOfWork(store=fake_store) as uow:
            respondents = uow.respondents.get_by_assembly_id(assembly.id)
            for respondent in respondents:
                respondent.selection_status = RespondentStatus.SELECTED
            uow.commit()

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/db/reset",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Reset 10 respondents" in response.data
        with FakeUnitOfWork(store=fake_store) as uow:
            respondents = uow.respondents.get_by_assembly_id(assembly.id)
            assert len(respondents) == 10
            assert all(r.selection_status == RespondentStatus.POOL for r in respondents)

    @patch("opendlp.entrypoints.blueprints.db_selection_backoffice.reset_selection_status")
    def test_reset_csv_selection_handles_not_found(self, mock_reset, logged_in_admin, assembly_with_csv_config):
        """A NotFoundError from the reset service redirects with a not-found error."""
        assembly = assembly_with_csv_config
        mock_reset.side_effect = NotFoundError("Assembly not found")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/selection/db/reset",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"not found" in response.data.lower()

    def test_reset_csv_selection_requires_auth(self, client, assembly_with_csv_config):
        """Reset endpoint requires authentication."""
        assembly = assembly_with_csv_config
        response = client.post(f"/backoffice/assembly/{assembly.id}/selection/db/reset")

        assert response.status_code == 302
        assert "login" in response.location


class TestCsvSelectionSelectedCount:
    """Tests for CSV selection page showing selected count and reset button."""

    def test_selection_page_shows_selected_count_when_respondents_selected(
        self, logged_in_admin, assembly_with_csv_config, fake_store
    ):
        """Selection page shows selected count when respondents have been selected."""
        assembly = assembly_with_csv_config

        with FakeUnitOfWork(store=fake_store) as uow:
            respondents = uow.respondents.get_by_assembly_id(assembly.id)
            for respondent in respondents[:5]:
                respondent.selection_status = RespondentStatus.SELECTED
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"5 respondents have been selected" in response.data
        assert b"Reset Selected People" in response.data
        assert b"Run Selection" not in response.data

    def test_selection_page_shows_normal_ui_when_no_selection(self, logged_in_admin, assembly_with_csv_config):
        """Selection page shows normal UI when no selection has been run."""
        assembly = assembly_with_csv_config

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"Reset Selected People" not in response.data
        assert b"Run Selection" in response.data
        assert b"Run Test Selection" in response.data


class TestSaveCsvSettings:
    """Tests for the save CSV settings endpoint."""

    def test_save_csv_settings_with_address_columns(self, logged_in_admin, assembly_with_csv_config_unconfirmed):
        """Saving settings with address columns specified succeeds."""
        assembly = assembly_with_csv_config_unconfirmed

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/data/csv/settings",
            data={
                "check_same_address": "y",
                "check_same_address_cols_string": "Gender",
                "columns_to_keep_string": "Gender",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Selection settings saved successfully" in response.data

    def test_save_csv_settings_without_check_address(self, logged_in_admin, assembly_with_csv_config_unconfirmed):
        """Saving settings with check_same_address disabled succeeds."""
        assembly = assembly_with_csv_config_unconfirmed

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/data/csv/settings",
            data={
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Selection settings saved successfully" in response.data

    def test_save_csv_settings_requires_auth(self, client, assembly_with_csv_config_unconfirmed):
        """Save settings endpoint requires authentication."""
        assembly = assembly_with_csv_config_unconfirmed
        response = client.post(f"/backoffice/assembly/{assembly.id}/data/csv/settings")

        assert response.status_code == 302
        assert "login" in response.location


class TestCsvSelectionSettingsWarning:
    """Tests for CSV selection settings confirmation warning."""

    def test_selection_page_shows_warning_when_settings_not_confirmed(
        self, logged_in_admin, assembly_with_csv_config_unconfirmed
    ):
        """Selection page shows warning when settings are not confirmed."""
        assembly = assembly_with_csv_config_unconfirmed

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"review and save the selection settings" in response.data
        assert b"Go to Data Settings" in response.data
        assert b"source=csv" in response.data
        assert b"mode=edit" in response.data
        assert b"#selection-settings" in response.data

    def test_selection_page_buttons_disabled_when_settings_not_confirmed(
        self, logged_in_admin, assembly_with_csv_config_unconfirmed
    ):
        """Selection buttons are disabled when settings are not confirmed."""
        assembly = assembly_with_csv_config_unconfirmed

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"disabled" in response.data

    def test_selection_page_no_warning_when_settings_confirmed(self, logged_in_admin, assembly_with_csv_config):
        """Selection page does not show warning when settings are confirmed."""
        assembly = assembly_with_csv_config

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"review and save the selection settings" not in response.data


class TestCsvSelectionHistory:
    """Tests for CSV selection history display."""

    def test_selection_page_shows_history_section(self, logged_in_admin, assembly_with_csv_config):
        """CSV selection page shows the Selection History section."""
        assembly = assembly_with_csv_config

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"Selection History" in response.data
        assert b"No selection runs yet" in response.data

    def test_selection_page_shows_history_with_runs(
        self, logged_in_admin, assembly_with_csv_config, fake_store, admin_user
    ):
        """CSV selection page shows selection runs in the history table."""
        assembly = assembly_with_csv_config
        _add_run_record(
            fake_store,
            assembly_id=assembly.id,
            task_id=uuid.uuid4(),
            status=SelectionRunStatus.COMPLETED,
            task_type=SelectionTaskType.SELECT_FROM_DB,
            user_id=admin_user.id,
            completed_at=datetime.now(UTC),
        )

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")

        assert response.status_code == 200
        assert b"Selection History" in response.data
        assert b"Completed" in response.data
        assert b"View" in response.data
