"""ABOUTME: End-to-end tests for monitor selection health checks
ABOUTME: Exercises /health and /health/monitor_selection across all monitor states"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest
from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.value_objects import AssemblyStatus, SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


def _seed_record(
    session_factory,
    assembly_id: uuid.UUID,
    *,
    task_type: SelectionTaskType,
    status: SelectionRunStatus,
    age: timedelta,
    error_message: str = "",
) -> SelectionRunRecord:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        record = SelectionRunRecord(
            assembly_id=assembly_id,
            task_id=uuid.uuid4(),
            status=status,
            task_type=task_type,
            created_at=datetime.now(UTC) - age,
            error_message=error_message,
        )
        if status in (SelectionRunStatus.FAILED, SelectionRunStatus.CANCELLED, SelectionRunStatus.COMPLETED):
            record.completed_at = datetime.now(UTC) - age + timedelta(seconds=10)
        uow.selection_run_records.add(record)
        uow.commit()
        return record.create_detached_copy()


def _mock_other_health_checks():
    """Patch the other health helpers so this test focuses on monitor checks."""
    return [
        patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 1)),
        patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
    ]


@pytest.fixture
def configured_assembly(postgres_session_factory, admin_user, temp_env_vars):
    """Create a monitor assembly and configure env vars to point at it."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = Assembly(
            title="Monitor Assembly",
            question="?",
            first_assembly_date=date.today() + timedelta(days=30),
            status=AssemblyStatus.ACTIVE,
        )
        uow.assemblies.add(assembly)
        uow.commit()
        detached = assembly.create_detached_copy()

    temp_env_vars(
        MONITOR_ASSEMBLY_ID=str(detached.id),
        MONITOR_USER_ID=str(admin_user.id),
        MONITOR_HEALTH_MAX_AGE_MINUTES="120",
    )
    return detached


def _run_with_mocked_helpers(client: FlaskClient, url: str):
    with _mock_other_health_checks()[0], _mock_other_health_checks()[1]:
        return client.get(url)


class TestMonitorSelectionHealth:
    def test_not_configured_health_endpoint_is_200(self, client: FlaskClient, clear_env_vars):
        clear_env_vars("MONITOR_ASSEMBLY_ID")
        response = _run_with_mocked_helpers(client, "/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["monitor_selection_status"] == "NOT_CONFIGURED"

    def test_not_configured_monitor_endpoint_is_500(self, client: FlaskClient, clear_env_vars):
        clear_env_vars("MONITOR_ASSEMBLY_ID")
        response = _run_with_mocked_helpers(client, "/health/monitor_selection")
        assert response.status_code == 500
        data = response.get_json()
        assert data["monitor_selection_status"] == "NOT_CONFIGURED"

    @pytest.mark.db_semantics
    def test_ok_when_recent_completed_select_and_completed_cleanup(
        self, client: FlaskClient, postgres_session_factory, configured_assembly
    ):
        _seed_record(
            postgres_session_factory,
            configured_assembly.id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.COMPLETED,
            age=timedelta(minutes=30),
        )
        _seed_record(
            postgres_session_factory,
            configured_assembly.id,
            task_type=SelectionTaskType.DELETE_OLD_TABS,
            status=SelectionRunStatus.COMPLETED,
            age=timedelta(minutes=29),
        )

        for url in ("/health", "/health/monitor_selection"):
            response = _run_with_mocked_helpers(client, url)
            assert response.status_code == 200, url
            data = response.get_json()
            assert data["monitor_selection_status"] == "OK"
            assert data["monitor_cleanup_status"] == "OK"
            assert data["monitor_selection_last_run_url"]
            assert "/assembly/" in data["monitor_selection_last_run_url"]
            assert "/selection/" in data["monitor_selection_last_run_url"]

    @pytest.mark.db_semantics
    def test_stale_when_completed_select_too_old(
        self, client: FlaskClient, postgres_session_factory, configured_assembly
    ):
        _seed_record(
            postgres_session_factory,
            configured_assembly.id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.COMPLETED,
            age=timedelta(hours=3),
        )
        for url in ("/health", "/health/monitor_selection"):
            response = _run_with_mocked_helpers(client, url)
            assert response.status_code == 500, url
            assert response.get_json()["monitor_selection_status"] == "STALE"

    @pytest.mark.db_semantics
    def test_stale_when_no_records_exist(self, client: FlaskClient, configured_assembly):
        for url in ("/health", "/health/monitor_selection"):
            response = _run_with_mocked_helpers(client, url)
            assert response.status_code == 500, url
            assert response.get_json()["monitor_selection_status"] == "STALE"

    @pytest.mark.db_semantics
    def test_failed_when_latest_select_failed(self, client: FlaskClient, postgres_session_factory, configured_assembly):
        _seed_record(
            postgres_session_factory,
            configured_assembly.id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.FAILED,
            age=timedelta(minutes=5),
            error_message="permission denied on sheet",
        )
        for url in ("/health", "/health/monitor_selection"):
            response = _run_with_mocked_helpers(client, url)
            assert response.status_code == 500, url
            data = response.get_json()
            assert data["monitor_selection_status"] == "FAILED"
            assert "permission denied" in data["monitor_selection_message"]

    @pytest.mark.db_semantics
    def test_failed_when_latest_select_cancelled(
        self, client: FlaskClient, postgres_session_factory, configured_assembly
    ):
        _seed_record(
            postgres_session_factory,
            configured_assembly.id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.CANCELLED,
            age=timedelta(minutes=5),
        )
        response = _run_with_mocked_helpers(client, "/health/monitor_selection")
        assert response.status_code == 500
        assert response.get_json()["monitor_selection_status"] == "FAILED"

    @pytest.mark.db_semantics
    def test_cleanup_failed_overrides_ok_status(
        self, client: FlaskClient, postgres_session_factory, configured_assembly
    ):
        _seed_record(
            postgres_session_factory,
            configured_assembly.id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.COMPLETED,
            age=timedelta(minutes=20),
        )
        _seed_record(
            postgres_session_factory,
            configured_assembly.id,
            task_type=SelectionTaskType.DELETE_OLD_TABS,
            status=SelectionRunStatus.FAILED,
            age=timedelta(minutes=15),
            error_message="cleanup blew up",
        )
        for url in ("/health", "/health/monitor_selection"):
            response = _run_with_mocked_helpers(client, url)
            assert response.status_code == 500, url
            data = response.get_json()
            assert data["monitor_cleanup_status"] == "FAILED"

    @pytest.mark.db_semantics
    def test_pending_within_window(self, client: FlaskClient, postgres_session_factory, configured_assembly):
        _seed_record(
            postgres_session_factory,
            configured_assembly.id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            age=timedelta(minutes=10),
        )
        for url in ("/health", "/health/monitor_selection"):
            response = _run_with_mocked_helpers(client, url)
            assert response.status_code == 200, url
            assert response.get_json()["monitor_selection_status"] == "PENDING"

    @pytest.mark.db_semantics
    def test_stale_when_running_too_long(self, client: FlaskClient, postgres_session_factory, configured_assembly):
        _seed_record(
            postgres_session_factory,
            configured_assembly.id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
            age=timedelta(hours=3),
        )
        response = _run_with_mocked_helpers(client, "/health/monitor_selection")
        assert response.status_code == 500
        assert response.get_json()["monitor_selection_status"] == "STALE"
