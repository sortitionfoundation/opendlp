"""ABOUTME: Unit tests for the run_monitoring_selection service function
ABOUTME: Uses FakeUnitOfWork plus injected fakes/spies — no Celery, no DB"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    GoogleSheetConfigNotFoundError,
    InsufficientPermissions,
    InvalidSelection,
)
from opendlp.service_layer.monitoring import (
    MonitorResult,
    MonitorSelectionStatus,
    check_monitor_selection,
    get_latest_monitor_run,
    run_monitoring_selection,
)
from tests.fakes import FakeUnitOfWork


class _FakeClock:
    """Minimal fake clock: now_fn() returns the current time, sleep_fn(seconds) advances it."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 1, 1, tzinfo=UTC)

    def now_fn(self) -> datetime:
        return self.now

    def sleep_fn(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def _make_record(assembly_id: uuid.UUID, status: SelectionRunStatus) -> SelectionRunRecord:
    return SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=uuid.uuid4(),
        status=status,
        task_type=SelectionTaskType.SELECT_GSHEET,
    )


class TestNotConfigured:
    def test_returns_not_configured_when_assembly_id_missing(self, clear_env_vars):
        clear_env_vars("MONITOR_ASSEMBLY_ID", "MONITOR_USER_ID")

        select_calls: list[tuple] = []
        cleanup_calls: list[tuple] = []

        def spy_select(*args: Any, **kwargs: Any) -> uuid.UUID:
            select_calls.append((args, kwargs))
            return uuid.uuid4()

        def spy_cleanup(*args: Any, **kwargs: Any) -> uuid.UUID:
            cleanup_calls.append((args, kwargs))
            return uuid.uuid4()

        result = run_monitoring_selection(
            FakeUnitOfWork(),
            start_select_fn=spy_select,
            start_cleanup_fn=spy_cleanup,
        )

        assert isinstance(result, MonitorResult)
        assert result.success is False
        assert result.not_configured is True
        assert result.task_id is None
        assert select_calls == []
        assert cleanup_calls == []

    def test_returns_not_configured_when_only_user_id_missing(self, temp_env_vars, clear_env_vars):
        temp_env_vars(MONITOR_ASSEMBLY_ID=str(uuid.uuid4()))
        clear_env_vars("MONITOR_USER_ID")

        result = run_monitoring_selection(FakeUnitOfWork())

        assert result.success is False
        assert result.not_configured is True


class TestHappyPath:
    def test_dispatches_select_polls_and_runs_cleanup(self, temp_env_vars):
        assembly_id = uuid.uuid4()
        user_id = uuid.uuid4()
        temp_env_vars(MONITOR_ASSEMBLY_ID=str(assembly_id), MONITOR_USER_ID=str(user_id))

        uow = FakeUnitOfWork()
        clock = _FakeClock()

        select_calls: list[dict[str, Any]] = []
        cleanup_calls: list[dict[str, Any]] = []
        poll_calls: list[uuid.UUID] = []

        def spy_select(uow_arg: Any, user_arg: uuid.UUID, assembly_arg: uuid.UUID, **kwargs: Any) -> uuid.UUID:
            assert assembly_arg == assembly_id
            assert user_arg == user_id
            select_calls.append(kwargs)
            record = _make_record(assembly_arg, SelectionRunStatus.PENDING)
            uow_arg.selection_run_records.add(record)
            return record.task_id

        def spy_cleanup(uow_arg: Any, user_arg: uuid.UUID, assembly_arg: uuid.UUID, **kwargs: Any) -> uuid.UUID:
            cleanup_calls.append({"user_id": user_arg, "assembly_id": assembly_arg, **kwargs})
            return uuid.uuid4()

        def spy_health(uow_arg: Any, task_id: uuid.UUID) -> None:
            return None

        def spy_poll(uow_arg: Any, task_id: uuid.UUID) -> None:
            poll_calls.append(task_id)
            record = uow_arg.selection_run_records.get_by_task_id(task_id)
            if record is not None and len(poll_calls) >= 2:
                record.status = SelectionRunStatus.COMPLETED
            return None

        result = run_monitoring_selection(
            uow,
            start_select_fn=spy_select,
            start_cleanup_fn=spy_cleanup,
            health_check_fn=spy_health,
            poll_status_fn=spy_poll,
            now_fn=clock.now_fn,
            sleep_fn=clock.sleep_fn,
            poll_interval_seconds=2.0,
        )

        assert len(select_calls) == 1
        assert select_calls[0].get("celery_apply_kwargs") == {"time_limit": 300, "soft_time_limit": 270}

        assert result.success is True
        assert result.task_id is not None
        assert result.not_configured is False

        assert len(cleanup_calls) == 1
        assert cleanup_calls[0]["dry_run"] is False
        assert cleanup_calls[0]["assembly_id"] == assembly_id


class TestWrapperTimeout:
    def test_returns_timeout_when_record_never_finishes(self, temp_env_vars):
        assembly_id = uuid.uuid4()
        user_id = uuid.uuid4()
        temp_env_vars(MONITOR_ASSEMBLY_ID=str(assembly_id), MONITOR_USER_ID=str(user_id))

        uow = FakeUnitOfWork()
        clock = _FakeClock()
        cleanup_calls: list[Any] = []
        health_calls: list[uuid.UUID] = []

        def spy_select(uow_arg: Any, user_arg: uuid.UUID, assembly_arg: uuid.UUID, **kwargs: Any) -> uuid.UUID:
            record = _make_record(assembly_arg, SelectionRunStatus.RUNNING)
            uow_arg.selection_run_records.add(record)
            return record.task_id

        def spy_cleanup(*args: Any, **kwargs: Any) -> uuid.UUID:
            cleanup_calls.append((args, kwargs))
            return uuid.uuid4()

        def spy_health(uow_arg: Any, task_id: uuid.UUID) -> None:
            health_calls.append(task_id)

        def spy_poll(uow_arg: Any, task_id: uuid.UUID) -> None:
            # record stays RUNNING forever
            return None

        result = run_monitoring_selection(
            uow,
            start_select_fn=spy_select,
            start_cleanup_fn=spy_cleanup,
            health_check_fn=spy_health,
            poll_status_fn=spy_poll,
            now_fn=clock.now_fn,
            sleep_fn=clock.sleep_fn,
            wrapper_timeout_seconds=10,
            poll_interval_seconds=2.0,
        )

        assert result.success is False
        assert "timeout" in result.message.lower()
        assert len(health_calls) >= 1
        assert cleanup_calls == []


class TestServiceFunctionExceptions:
    @pytest.mark.parametrize(
        "exc_cls",
        [AssemblyNotFoundError, GoogleSheetConfigNotFoundError, InvalidSelection, InsufficientPermissions],
    )
    def test_typed_exceptions_become_failure_results(self, temp_env_vars, exc_cls):
        assembly_id = uuid.uuid4()
        user_id = uuid.uuid4()
        temp_env_vars(MONITOR_ASSEMBLY_ID=str(assembly_id), MONITOR_USER_ID=str(user_id))

        def bad_select(*args: Any, **kwargs: Any) -> uuid.UUID:
            raise exc_cls("boom")

        def spy_cleanup(*args: Any, **kwargs: Any) -> uuid.UUID:
            return uuid.uuid4()

        result = run_monitoring_selection(
            FakeUnitOfWork(),
            start_select_fn=bad_select,
            start_cleanup_fn=spy_cleanup,
        )

        assert result.success is False
        assert exc_cls.__name__ in result.message


class TestCheckMonitorSelection:
    def test_not_configured_when_no_assembly_id(self, clear_env_vars):
        clear_env_vars("MONITOR_ASSEMBLY_ID", "MONITOR_USER_ID")
        result = check_monitor_selection(FakeUnitOfWork())
        assert isinstance(result, MonitorSelectionStatus)
        assert result.status == "NOT_CONFIGURED"
        assert result.last_run_at is None
        assert result.cleanup_status == "OK"

    def test_stale_when_no_records(self, temp_env_vars):
        temp_env_vars(MONITOR_ASSEMBLY_ID=str(uuid.uuid4()), MONITOR_USER_ID=str(uuid.uuid4()))
        result = check_monitor_selection(FakeUnitOfWork())
        assert result.status == "STALE"
        assert "no monitor selection runs" in result.message

    def test_ok_when_recent_completed(self, temp_env_vars):
        assembly_id = uuid.uuid4()
        temp_env_vars(MONITOR_ASSEMBLY_ID=str(assembly_id), MONITOR_USER_ID=str(uuid.uuid4()))
        uow = FakeUnitOfWork()
        record = SelectionRunRecord(
            assembly_id=assembly_id,
            task_id=uuid.uuid4(),
            status=SelectionRunStatus.COMPLETED,
            task_type=SelectionTaskType.SELECT_GSHEET,
            created_at=datetime.now(UTC) - timedelta(minutes=30),
        )
        uow.selection_run_records.add(record)

        result = check_monitor_selection(uow)
        assert result.status == "OK"
        assert result.cleanup_status == "OK"
        assert result.last_run_at == record.created_at

    def test_failed_select_record(self, temp_env_vars):
        assembly_id = uuid.uuid4()
        temp_env_vars(MONITOR_ASSEMBLY_ID=str(assembly_id), MONITOR_USER_ID=str(uuid.uuid4()))
        uow = FakeUnitOfWork()
        uow.selection_run_records.add(
            SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=uuid.uuid4(),
                status=SelectionRunStatus.FAILED,
                task_type=SelectionTaskType.SELECT_GSHEET,
                created_at=datetime.now(UTC) - timedelta(minutes=5),
                error_message="permission denied",
            )
        )
        result = check_monitor_selection(uow)
        assert result.status == "FAILED"
        assert "permission denied" in result.message

    def test_cleanup_failure_overrides_ok(self, temp_env_vars):
        assembly_id = uuid.uuid4()
        temp_env_vars(MONITOR_ASSEMBLY_ID=str(assembly_id), MONITOR_USER_ID=str(uuid.uuid4()))
        uow = FakeUnitOfWork()
        uow.selection_run_records.add(
            SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=uuid.uuid4(),
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_GSHEET,
                created_at=datetime.now(UTC) - timedelta(minutes=20),
            )
        )
        uow.selection_run_records.add(
            SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=uuid.uuid4(),
                status=SelectionRunStatus.FAILED,
                task_type=SelectionTaskType.DELETE_OLD_TABS,
                created_at=datetime.now(UTC) - timedelta(minutes=15),
                error_message="cleanup blew up",
            )
        )
        result = check_monitor_selection(uow)
        assert result.status == "FAILED"
        assert result.cleanup_status == "FAILED"


class TestGetLatestMonitorRun:
    def test_returns_none_when_unconfigured(self, clear_env_vars):
        clear_env_vars("MONITOR_ASSEMBLY_ID", "MONITOR_USER_ID")
        assert get_latest_monitor_run(FakeUnitOfWork()) is None

    def test_returns_none_when_no_records(self, temp_env_vars):
        assembly_id = uuid.uuid4()
        temp_env_vars(MONITOR_ASSEMBLY_ID=str(assembly_id), MONITOR_USER_ID=str(uuid.uuid4()))

        assert get_latest_monitor_run(FakeUnitOfWork()) is None

    def test_returns_select_record_by_default(self, temp_env_vars):
        assembly_id = uuid.uuid4()
        temp_env_vars(MONITOR_ASSEMBLY_ID=str(assembly_id), MONITOR_USER_ID=str(uuid.uuid4()))

        uow = FakeUnitOfWork()
        select_record = SelectionRunRecord(
            assembly_id=assembly_id,
            task_id=uuid.uuid4(),
            status=SelectionRunStatus.COMPLETED,
            task_type=SelectionTaskType.SELECT_GSHEET,
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )
        cleanup_record = SelectionRunRecord(
            assembly_id=assembly_id,
            task_id=uuid.uuid4(),
            status=SelectionRunStatus.COMPLETED,
            task_type=SelectionTaskType.DELETE_OLD_TABS,
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
        uow.selection_run_records.add(select_record)
        uow.selection_run_records.add(cleanup_record)

        latest = get_latest_monitor_run(uow)
        assert latest is not None
        assert latest.task_id == select_record.task_id

        latest_cleanup = get_latest_monitor_run(uow, task_type=SelectionTaskType.DELETE_OLD_TABS)
        assert latest_cleanup is not None
        assert latest_cleanup.task_id == cleanup_record.task_id
