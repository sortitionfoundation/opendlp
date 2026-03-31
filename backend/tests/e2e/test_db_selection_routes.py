"""ABOUTME: End-to-end tests for database selection routes
ABOUTME: Tests DB selection page, check data, start selection, progress, cancel, downloads, and settings"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.assembly_service import create_assembly, update_csv_config, update_selection_settings
from opendlp.service_layer.exceptions import InvalidSelection, NotFoundError
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.sortition import CheckDataResult
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def assembly_for_db_selection(postgres_session_factory, admin_user):
    """Create an assembly configured for DB selection (no gsheet needed)."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="DB Selection Assembly",
            created_by_user_id=admin_user.id,
            question="What should we select?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            number_to_select=10,
        )
        assembly_id = assembly.id

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        update_csv_config(
            uow=uow,
            user_id=admin_user.id,
            assembly_id=assembly_id,
            settings_confirmed=True,
        )

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        update_selection_settings(
            uow=uow,
            user_id=admin_user.id,
            assembly_id=assembly_id,
            check_same_address=False,
        )

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        a = uow.assemblies.get(assembly_id)
        return a.create_detached_copy()


class TestDbSelectionRoutes:
    def test_view_db_selection_page_loads(self, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select")

        assert response.status_code == 200
        assert b"Selection" in response.data
        assert b"Run Selection" in response.data
        assert b"Run Test Selection" in response.data
        assert b"Check Targets" in response.data

    def test_view_db_selection_requires_auth(self, client, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        response = client.get(f"/assemblies/{assembly.id}/db_select")

        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_view_db_selection_with_run_shows_status(
        self, logged_in_admin, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        task_id = uuid.uuid4()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                log_messages=["Task started", "Loading data"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select/{task_id}")

        assert response.status_code == 200
        assert b"Current status: running" in response.data
        assert b"Loading data" in response.data

    @patch("opendlp.service_layer.sortition.tasks.run_select_from_db.delay")
    def test_start_db_selection_success(
        self, mock_celery, logged_in_admin, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        mock_result = Mock()
        mock_result.id = "celery-task-id"
        mock_celery.return_value = mock_result

        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/run",
            data={"test_selection": "0"},
        )

        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/db_select/" in response.headers["Location"]

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            records = list(uow.selection_run_records.get_by_assembly_id(assembly.id))
            assert len(records) == 1
            assert records[0].task_type == SelectionTaskType.SELECT_FROM_DB

    @patch("opendlp.service_layer.sortition.tasks.run_select_from_db.delay")
    def test_start_db_test_selection_success(
        self, mock_celery, logged_in_admin, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        mock_result = Mock()
        mock_result.id = "celery-task-id"
        mock_celery.return_value = mock_result

        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/run",
            data={"test_selection": "1"},
        )

        assert response.status_code == 302

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            records = list(uow.selection_run_records.get_by_assembly_id(assembly.id))
            assert len(records) == 1
            assert records[0].task_type == SelectionTaskType.TEST_SELECT_FROM_DB

    @patch("opendlp.entrypoints.blueprints.db_selection_legacy.check_db_selection_data")
    def test_check_db_data_success(self, mock_check, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        mock_check.return_value = CheckDataResult(
            success=True,
            errors=[],
            features_report_html="<p>Features OK</p>",
            people_report_html="<p>People OK</p>",
            num_features=3,
            num_people=100,
        )

        response = logged_in_admin.post(f"/assemblies/{assembly.id}/db_select/check")

        assert response.status_code == 200
        assert b"Data Check Passed" in response.data
        assert b"3 target categories" in response.data
        assert b"100 eligible respondents" in response.data

    @patch("opendlp.entrypoints.blueprints.db_selection_legacy.check_db_selection_data")
    def test_check_db_data_failure(self, mock_check, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        mock_check.return_value = CheckDataResult(
            success=False,
            errors=["<p>Feature mismatch</p>"],
            features_report_html="",
            people_report_html="",
            num_features=0,
            num_people=0,
        )

        response = logged_in_admin.post(f"/assemblies/{assembly.id}/db_select/check")

        assert response.status_code == 200
        assert b"Data Check Failed" in response.data
        assert b"Feature mismatch" in response.data

    def test_progress_polling_returns_fragment(
        self, logged_in_admin, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        task_id = uuid.uuid4()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                log_messages=["Running selection"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select/{task_id}/progress")

        assert response.status_code == 200
        assert b"progress-section" in response.data
        assert b"Running selection" in response.data

    def test_progress_polling_completed_sends_refresh(
        self, logged_in_admin, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        task_id = uuid.uuid4()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                log_messages=["Done"],
                completed_at=datetime.now(UTC),
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select/{task_id}/progress")

        assert response.status_code == 200
        assert response.headers.get("HX-Refresh") == "true"

    def test_cancel_db_selection(self, logged_in_admin, assembly_for_db_selection, postgres_session_factory):
        assembly = assembly_for_db_selection
        task_id = uuid.uuid4()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                celery_task_id="fake-celery-id",
                log_messages=["Task started"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        with patch("opendlp.service_layer.sortition.app.app.control.revoke"):
            response = logged_in_admin.post(
                f"/assemblies/{assembly.id}/db_select/{task_id}/cancel",
            )

        assert response.status_code == 302

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record.status == SelectionRunStatus.CANCELLED

    def test_view_db_selection_settings_loads(self, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select/settings")

        assert response.status_code == 200
        assert b"Selection Settings" in response.data
        assert b"Check Same Address" in response.data

    def test_save_db_selection_settings(self, logged_in_admin, assembly_for_db_selection, postgres_session_factory):
        assembly = assembly_for_db_selection
        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/settings",
            data={
                "check_same_address": "y",
                "check_same_address_cols_string": "address1, postcode",
                "columns_to_keep_string": "first_name, last_name",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/db_select" in response.headers["Location"]

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            a = uow.assemblies.get(assembly.id)
            assert a.selection_settings is not None
            assert a.selection_settings.check_same_address is True
            assert a.selection_settings.check_same_address_cols == ["address1", "postcode"]
            assert a.selection_settings.columns_to_keep == ["first_name", "last_name"]

    def test_save_db_selection_settings_marks_confirmed(self, logged_in_admin, admin_user, postgres_session_factory):
        """Saving selection settings should set settings_confirmed=True."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(
                uow=uow,
                title="Unconfirmed Assembly",
                created_by_user_id=admin_user.id,
                question="Test?",
                number_to_select=10,
            )
            assembly_id = assembly.id

        # Verify settings_confirmed starts as False
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            a = uow.assemblies.get(assembly_id)
            assert a.csv is None or a.csv.settings_confirmed is False

        logged_in_admin.post(
            f"/assemblies/{assembly_id}/db_select/settings",
            data={
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "",
            },
            follow_redirects=False,
        )

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            a = uow.assemblies.get(assembly_id)
            assert a.csv is not None
            assert a.csv.settings_confirmed is True

    def test_save_settings_rejects_check_same_address_without_columns(self, logged_in_admin, assembly_for_db_selection):
        """Saving settings with check_same_address=True but no columns should show a validation error."""
        assembly = assembly_for_db_selection
        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/settings",
            data={
                "check_same_address": "y",
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "",
            },
        )

        assert response.status_code == 200
        assert b"address attributes" in response.data.lower()

    def test_settings_page_shows_available_columns(
        self, logged_in_admin, admin_user, assembly_for_db_selection, postgres_session_factory
    ):
        """Settings page should display available respondent attribute columns."""
        assembly = assembly_for_db_selection
        csv_content = "external_id,email,Gender,Age,PostalCode\nR001,a@b.com,Female,30,SW1A\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=assembly.id,
                csv_content=csv_content,
            )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select/settings")
        assert response.status_code == 200
        assert b"Available respondent attributes" in response.data
        assert b"Age" in response.data
        assert b"Gender" in response.data
        assert b"PostalCode" in response.data

    def test_settings_page_shows_no_columns_message_without_respondents(
        self, logged_in_admin, assembly_for_db_selection
    ):
        """Settings page should show a message when no respondent data exists."""
        assembly = assembly_for_db_selection
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select/settings")
        assert response.status_code == 200
        assert b"No respondent data has been uploaded yet" in response.data

    def test_save_settings_rejects_unknown_address_column(
        self, logged_in_admin, admin_user, assembly_for_db_selection, postgres_session_factory
    ):
        """Saving settings with unknown column names in address cols should show validation error."""
        assembly = assembly_for_db_selection
        csv_content = "external_id,email,Gender,Age\nR001,a@b.com,Female,30\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=assembly.id,
                csv_content=csv_content,
            )

        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/settings",
            data={
                "check_same_address": "y",
                "check_same_address_cols_string": "Gender, nonexistent_col",
                "columns_to_keep_string": "",
            },
        )
        assert response.status_code == 200
        assert b"nonexistent_col" in response.data

    def test_save_settings_rejects_unknown_columns_to_keep(
        self, logged_in_admin, admin_user, assembly_for_db_selection, postgres_session_factory
    ):
        """Saving settings with unknown column names in columns_to_keep should show validation error."""
        assembly = assembly_for_db_selection
        csv_content = "external_id,email,Gender,Age\nR001,a@b.com,Female,30\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=assembly.id,
                csv_content=csv_content,
            )

        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/settings",
            data={
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "Gender, bad_col",
            },
        )
        assert response.status_code == 200
        assert b"bad_col" in response.data

    def test_save_settings_accepts_valid_columns(
        self, logged_in_admin, admin_user, assembly_for_db_selection, postgres_session_factory
    ):
        """Saving settings with valid column names should succeed."""
        assembly = assembly_for_db_selection
        csv_content = "external_id,email,Gender,Age\nR001,a@b.com,Female,30\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=assembly.id,
                csv_content=csv_content,
            )

        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/settings",
            data={
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "Gender, Age",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_save_settings_skips_column_validation_without_respondents(
        self, logged_in_admin, assembly_for_db_selection
    ):
        """Saving settings should succeed with any column names when no respondents exist."""
        assembly = assembly_for_db_selection
        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/settings",
            data={
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "anything, whatever",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_view_db_replacement_placeholder(self, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_replace")

        assert response.status_code == 200
        assert b"coming soon" in response.data

    def test_view_gsheet_run_routes_db_selection_tasks(
        self, logged_in_admin, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        task_id = uuid.uuid4()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                log_messages=["Done"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(
            f"/assemblies/{assembly.id}/gsheet_runs/{task_id}/view",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/db_select/{task_id}" in response.headers["Location"]


class TestDbSelectionDownloads:
    @patch("opendlp.entrypoints.blueprints.db_selection_legacy.generate_selection_csvs")
    def test_download_selected_csv(self, mock_generate, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        run_id = uuid.uuid4()
        mock_generate.return_value = ("name,age\nAlice,30\nBob,25\n", "name,age\nCharlie,35\n")

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select/{run_id}/download/selected")

        assert response.status_code == 200
        assert response.content_type == "text/csv; charset=utf-8"
        assert b"Alice" in response.data
        assert f"selected-{run_id}.csv" in response.headers["Content-Disposition"]

    @patch("opendlp.entrypoints.blueprints.db_selection_legacy.generate_selection_csvs")
    def test_download_remaining_csv(self, mock_generate, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        run_id = uuid.uuid4()
        mock_generate.return_value = ("name,age\nAlice,30\n", "name,age\nBob,25\nCharlie,35\n")

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select/{run_id}/download/remaining")

        assert response.status_code == 200
        assert response.content_type == "text/csv; charset=utf-8"
        assert b"Bob" in response.data
        assert f"remaining-{run_id}.csv" in response.headers["Content-Disposition"]

    @patch("opendlp.entrypoints.blueprints.db_selection_legacy.generate_selection_csvs")
    def test_download_selected_csv_not_found(self, mock_generate, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        run_id = uuid.uuid4()
        mock_generate.side_effect = NotFoundError("Run not found")

        response = logged_in_admin.get(
            f"/assemblies/{assembly.id}/db_select/{run_id}/download/selected",
            follow_redirects=False,
        )

        assert response.status_code == 302

    @patch("opendlp.entrypoints.blueprints.db_selection_legacy.generate_selection_csvs")
    def test_download_selected_csv_invalid_selection(self, mock_generate, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        run_id = uuid.uuid4()
        mock_generate.side_effect = InvalidSelection("No results yet")

        response = logged_in_admin.get(
            f"/assemblies/{assembly.id}/db_select/{run_id}/download/selected",
            follow_redirects=False,
        )

        assert response.status_code == 302

    @patch("opendlp.entrypoints.blueprints.db_selection_legacy.generate_selection_csvs")
    def test_download_remaining_csv_not_found(self, mock_generate, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        run_id = uuid.uuid4()
        mock_generate.side_effect = NotFoundError("Run not found")

        response = logged_in_admin.get(
            f"/assemblies/{assembly.id}/db_select/{run_id}/download/remaining",
            follow_redirects=False,
        )

        assert response.status_code == 302

    @patch("opendlp.entrypoints.blueprints.db_selection_legacy.generate_selection_csvs")
    def test_download_remaining_csv_invalid_selection(self, mock_generate, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        run_id = uuid.uuid4()
        mock_generate.side_effect = InvalidSelection("No results yet")

        response = logged_in_admin.get(
            f"/assemblies/{assembly.id}/db_select/{run_id}/download/remaining",
            follow_redirects=False,
        )

        assert response.status_code == 302


class TestDbSelectionErrorHandling:
    def test_view_db_selection_nonexistent_assembly(self, logged_in_admin):
        fake_id = uuid.uuid4()
        response = logged_in_admin.get(f"/assemblies/{fake_id}/db_select", follow_redirects=False)
        assert response.status_code == 404

    def test_progress_nonexistent_run(self, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        fake_run = uuid.uuid4()
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select/{fake_run}/progress")
        assert response.status_code == 404

    def test_progress_wrong_assembly(
        self, logged_in_admin, assembly_for_db_selection, postgres_session_factory, admin_user
    ):
        assembly = assembly_for_db_selection
        task_id = uuid.uuid4()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            other_assembly = create_assembly(
                uow=uow,
                title="Other Assembly",
                created_by_user_id=admin_user.id,
                question="Other question",
                first_assembly_date=(datetime.now(UTC).date() + timedelta(days=60)),
                number_to_select=5,
            )
            other_id = other_assembly.id

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=other_id,
                task_id=task_id,
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                log_messages=["Running"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select/{task_id}/progress")
        assert response.status_code == 404

    @patch("opendlp.entrypoints.blueprints.db_selection_legacy.check_db_selection_data")
    def test_check_db_data_unexpected_error(self, mock_check, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        mock_check.side_effect = RuntimeError("Unexpected error")

        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/check",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_cancel_nonexistent_run(self, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        fake_run = uuid.uuid4()
        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/{fake_run}/cancel",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_start_db_selection_redirects_to_settings_when_not_confirmed(
        self, logged_in_admin, admin_user, postgres_session_factory
    ):
        """Running selection should redirect to settings page if settings have never been confirmed."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(
                uow=uow,
                title="Unconfirmed Settings Assembly",
                created_by_user_id=admin_user.id,
                question="Test?",
                number_to_select=10,
            )
            assembly_id = assembly.id

        response = logged_in_admin.post(
            f"/assemblies/{assembly_id}/db_select/run",
            data={"test_selection": "0"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/assemblies/{assembly_id}/db_select/settings" in response.headers["Location"]

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("review" in msg.lower() or "settings" in msg.lower() for msg in flash_messages)

    def test_check_db_data_redirects_to_settings_when_not_confirmed(
        self, logged_in_admin, admin_user, postgres_session_factory
    ):
        """Checking targets should redirect to settings page if settings have never been confirmed."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(
                uow=uow,
                title="Unconfirmed Check Assembly",
                created_by_user_id=admin_user.id,
                question="Test?",
                number_to_select=10,
            )
            assembly_id = assembly.id

        response = logged_in_admin.post(
            f"/assemblies/{assembly_id}/db_select/check",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/assemblies/{assembly_id}/db_select/settings" in response.headers["Location"]

    def test_start_db_selection_with_invalid_settings_shows_useful_error(
        self, logged_in_admin, admin_user, postgres_session_factory
    ):
        """When selection settings are invalid (e.g. check_same_address=True with no columns),
        the user should see a descriptive error, not a generic 'unexpected error' message."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(
                uow=uow,
                title="Bad Settings Assembly",
                created_by_user_id=admin_user.id,
                question="Will this fail?",
                number_to_select=10,
            )
            assembly_id = assembly.id

        # Set check_same_address=True but leave check_same_address_cols empty — this is invalid.
        # Mark settings_confirmed=True so we get past the guard and hit the actual validation.
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            update_csv_config(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=assembly_id,
                check_same_address=True,
                check_same_address_cols=[],
                settings_confirmed=True,
            )

        response = logged_in_admin.post(
            f"/assemblies/{assembly_id}/db_select/run",
            data={"test_selection": "0"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            # Should show a useful error about the settings, not "unexpected error"
            assert any("Could not start selection task" in msg for msg in flash_messages)
            assert not any("unexpected error" in msg.lower() for msg in flash_messages)

    @patch("opendlp.service_layer.sortition.tasks.run_select_from_db.delay")
    def test_start_db_selection_unexpected_error(self, mock_celery, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        mock_celery.side_effect = RuntimeError("Celery down")

        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/run",
            data={"test_selection": "0"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_view_db_selection_with_run_wrong_assembly(
        self, logged_in_admin, assembly_for_db_selection, postgres_session_factory, admin_user
    ):
        assembly = assembly_for_db_selection
        task_id = uuid.uuid4()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            other_assembly = create_assembly(
                uow=uow,
                title="Other Assembly",
                created_by_user_id=admin_user.id,
                question="Other question",
                first_assembly_date=(datetime.now(UTC).date() + timedelta(days=60)),
                number_to_select=5,
            )
            other_id = other_assembly.id

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=other_id,
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                log_messages=["Done"],
            )
            uow.selection_run_records.add(record)
            uow.commit()

        response = logged_in_admin.get(
            f"/assemblies/{assembly.id}/db_select/{task_id}",
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestSelectionReadinessWarnings:
    """Tests for readiness warnings on the selection page."""

    def test_shows_no_targets_warning(self, logged_in_admin, assembly_for_db_selection):
        """Selection page should warn when no target categories exist."""
        assembly = assembly_for_db_selection
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select")

        assert response.status_code == 200
        assert b"Target categories" in response.data
        assert b"none have been set up yet" in response.data

    def test_shows_no_respondents_warning(self, logged_in_admin, assembly_for_db_selection):
        """Selection page should warn when no respondents have been uploaded."""
        assembly = assembly_for_db_selection
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select")

        assert response.status_code == 200
        assert b"Respondents" in response.data
        assert b"none have been uploaded yet" in response.data

    def test_shows_no_settings_warning(self, logged_in_admin, admin_user, postgres_session_factory):
        """Selection page should warn when settings haven't been confirmed."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(
                uow=uow,
                title="No Settings Assembly",
                created_by_user_id=admin_user.id,
                question="Test?",
                number_to_select=10,
            )
            assembly_id = assembly.id

        response = logged_in_admin.get(f"/assemblies/{assembly_id}/db_select")

        assert response.status_code == 200
        assert b"Selection settings" in response.data
        assert b"need to be reviewed and saved" in response.data

    def test_buttons_disabled_when_not_ready(self, logged_in_admin, assembly_for_db_selection):
        """Selection buttons should be disabled when prerequisites are missing."""
        assembly = assembly_for_db_selection
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select")

        assert response.status_code == 200
        data = response.data.decode("utf-8")
        # Both Run Selection and Run Test Selection should be disabled
        assert "disabled" in data

    def test_no_warnings_when_all_ready(
        self, logged_in_admin, admin_user, assembly_for_db_selection, postgres_session_factory
    ):
        """No readiness warnings when settings, targets, and respondents all exist."""
        assembly = assembly_for_db_selection
        # Add respondents
        csv_content = "external_id,Gender\nR001,Female\nR002,Male\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=assembly.id,
                csv_content=csv_content,
            )
        # Add a target category
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            cat = TargetCategory(
                assembly_id=assembly.id,
                name="Gender",
                sort_order=0,
                values=[TargetValue(value="Female", min=0, max=5), TargetValue(value="Male", min=0, max=5)],
            )
            uow.target_categories.add(cat)
            uow.commit()

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select")

        assert response.status_code == 200
        assert b"cannot run yet" not in response.data
        assert b"already have a selection status" not in response.data

    def test_check_targets_button_always_enabled(self, logged_in_admin, assembly_for_db_selection):
        """Check Targets button should remain enabled even when prerequisites are missing."""
        assembly = assembly_for_db_selection
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select")

        assert response.status_code == 200
        data = response.data.decode("utf-8")
        # Find the Check Targets button - it should NOT be disabled
        # The button text appears after the submit button tag
        check_idx = data.find("Check Targets")
        assert check_idx > 0
        # Look backwards from "Check Targets" to find the button tag
        button_region = data[max(0, check_idx - 200) : check_idx]
        assert "disabled" not in button_region


class TestNonPoolRespondentWarning:
    """Tests for the warning shown when respondents have non-POOL status."""

    def _import_and_select_respondents(self, postgres_session_factory, admin_user, assembly_id):
        """Import respondents and mark some as SELECTED so they are non-POOL."""
        csv_content = "external_id,Gender,Age\nR001,Female,30\nR002,Male,25\nR003,Female,40\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=assembly_id,
                csv_content=csv_content,
            )
        # Create a SelectionRunRecord so the FK constraint is satisfied
        run_id = uuid.uuid4()
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=run_id,
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                log_messages=["Done"],
                completed_at=datetime.now(UTC),
            )
            uow.selection_run_records.add(record)
            uow.commit()
        # Mark one respondent as SELECTED
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.respondents.bulk_mark_as_selected(
                assembly_id=assembly_id,
                external_ids=["R001"],
                selection_run_id=run_id,
            )
            uow.commit()

    def test_selection_page_shows_warning_with_non_pool_respondents(
        self, logged_in_admin, admin_user, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        self._import_and_select_respondents(postgres_session_factory, admin_user, assembly.id)

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select")

        assert response.status_code == 200
        assert b"already have a selection status" in response.data
        assert b"Reset all respondents to Pool" in response.data

    def test_selection_buttons_disabled_with_non_pool_respondents(
        self, logged_in_admin, admin_user, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        self._import_and_select_respondents(postgres_session_factory, admin_user, assembly.id)

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select")

        assert response.status_code == 200
        # The Run Selection and Run Test Selection buttons should be disabled
        data = response.data.decode("utf-8")
        assert (
            "disabled>Run Selection" in data
            or 'disabled="">Run Selection' in data
            or "disabled>Run Selection" in data.replace(" ", "")
        )

    def test_check_targets_button_enabled_with_non_pool_respondents(
        self, logged_in_admin, admin_user, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        self._import_and_select_respondents(postgres_session_factory, admin_user, assembly.id)

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select")

        assert response.status_code == 200
        # Check Targets button should NOT be disabled
        data = response.data.decode("utf-8")
        assert "Check Targets" in data

    def test_selection_page_no_warning_when_all_pool(
        self, logged_in_admin, admin_user, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        # Import respondents but don't select any
        csv_content = "external_id,Gender,Age\nR001,Female,30\nR002,Male,25\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=assembly.id,
                csv_content=csv_content,
            )

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select")

        assert response.status_code == 200
        assert b"already have a selection status" not in response.data
        assert b"Reset all respondents to Pool" not in response.data

    def test_reset_respondents_from_selection_page(
        self, logged_in_admin, admin_user, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        self._import_and_select_respondents(postgres_session_factory, admin_user, assembly.id)

        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/reset-respondents",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert f"/assemblies/{assembly.id}/db_select" in response.headers["Location"]

        # Verify respondents are reset
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            non_pool = uow.respondents.count_non_pool(assembly.id)
            assert non_pool == 0

    def test_reset_respondents_shows_success_flash(
        self, logged_in_admin, admin_user, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        self._import_and_select_respondents(postgres_session_factory, admin_user, assembly.id)

        response = logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/reset-respondents",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Reset" in response.data
        assert b"Pool status" in response.data

    def test_after_reset_warning_disappears(
        self, logged_in_admin, admin_user, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        self._import_and_select_respondents(postgres_session_factory, admin_user, assembly.id)

        # Reset
        logged_in_admin.post(
            f"/assemblies/{assembly.id}/db_select/reset-respondents",
            follow_redirects=False,
        )

        # Check the page no longer shows warning
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select")
        assert response.status_code == 200
        assert b"already have a selection status" not in response.data

    def test_replacements_link_shown_in_warning(
        self, logged_in_admin, admin_user, assembly_for_db_selection, postgres_session_factory
    ):
        assembly = assembly_for_db_selection
        self._import_and_select_respondents(postgres_session_factory, admin_user, assembly.id)

        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select")

        assert response.status_code == 200
        assert b"Do replacements" in response.data
        assert f"/assemblies/{assembly.id}/db_replace".encode() in response.data


class TestRespondentsStatusFilter:
    def test_respondents_page_shows_status_filter(self, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/respondents")
        assert response.status_code == 200

    def test_respondents_filter_by_status_param(self, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/respondents?status=SELECTED")
        assert response.status_code == 200

    def test_respondents_invalid_status_ignored(self, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/respondents?status=INVALID")
        assert response.status_code == 200
