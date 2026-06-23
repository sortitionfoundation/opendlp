"""ABOUTME: End-to-end smoke + Celery-dispatch tests for database selection routes
ABOUTME: Behavioural coverage lives in tests/component/test_db_selection_routes.py over a FakeUnitOfWork"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.assembly_service import create_assembly, update_csv_config, update_selection_settings
from opendlp.service_layer.sortition import CheckDataResult
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

# The selection-status routes build a Celery AsyncResult from a (possibly empty)
# celery_task_id; the real redis result backend warns when GC removes it. Benign in
# these PG smokes, which assert on the rendered fragment, not the Celery result.
pytestmark = pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")


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


class TestDbSelectionSmoke:
    def test_view_db_selection_page_loads(self, logged_in_admin, assembly_for_db_selection):
        assembly = assembly_for_db_selection
        response = logged_in_admin.get(f"/assemblies/{assembly.id}/db_select")

        assert response.status_code == 200
        assert b"Selection" in response.data
        assert b"Run Selection" in response.data

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


class TestDbSelectionCelery:
    """Tests that dispatch Celery tasks (run_select_from_db.delay / control.revoke)."""

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
