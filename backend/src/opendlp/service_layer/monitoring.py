"""ABOUTME: Service-layer orchestration for the end-to-end selection-monitoring feature
ABOUTME: Wraps start_gsheet_select_task in a polled wrapper used by health checks, CLI, and Celery beat"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from flask import url_for

from opendlp import config
from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionTaskType
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    GoogleSheetConfigNotFoundError,
    InsufficientPermissions,
    InvalidSelection,
)
from opendlp.service_layer.sortition import (
    check_and_update_task_health,
    get_selection_run_status,
    start_gsheet_manage_tabs_task,
    start_gsheet_select_task,
)
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork

logger = structlog.get_logger(__name__)

MONITOR_CELERY_TIME_LIMIT_SECONDS = 300
MONITOR_WRAPPER_TIMEOUT_SECONDS = 360
_DEFAULT_POLL_INTERVAL_SECONDS = 2.0
_SOFT_TIME_LIMIT_GAP_SECONDS = 30


def _aware_utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class MonitorResult:
    success: bool
    task_id: uuid.UUID | None = None
    duration_seconds: float = 0.0
    message: str = ""
    error: str = ""
    not_configured: bool = False
    run_url: str = ""


def _safe_run_url(assembly_id: uuid.UUID, task_id: uuid.UUID) -> str:
    try:
        return url_for(
            "gsheets.view_assembly_selection_with_run",
            assembly_id=assembly_id,
            run_id=task_id,
            _external=True,
        )
    except Exception:
        # No Flask app/request context, or SERVER_NAME unset — degrade gracefully.
        return ""


def _poll_until_finished(
    uow: AbstractUnitOfWork,
    task_id: uuid.UUID,
    *,
    start_time: datetime,
    wrapper_timeout_seconds: int,
    poll_interval_seconds: float,
    health_check_fn: Callable[..., None],
    poll_status_fn: Callable[..., object],
    now_fn: Callable[[], datetime],
    sleep_fn: Callable[[float], None],
) -> tuple[SelectionRunRecord | None, float, bool]:
    """Poll until the record is finished or wrapper times out.

    Returns (record, elapsed_seconds, timed_out).
    """
    half_budget_hit = False
    while True:
        elapsed = (now_fn() - start_time).total_seconds()
        if elapsed >= wrapper_timeout_seconds:
            try:
                health_check_fn(uow, task_id)
            except Exception as exc:
                logger.warning("monitor health check on timeout failed", error=str(exc))
            return None, elapsed, True

        if not half_budget_hit and elapsed >= wrapper_timeout_seconds / 2:
            half_budget_hit = True
            try:
                health_check_fn(uow, task_id)
            except Exception as exc:
                logger.warning("monitor mid-run health check failed", error=str(exc))

        poll_status_fn(uow, task_id)
        record = uow.selection_run_records.get_by_task_id(task_id)
        if record is not None and record.has_finished:
            return record, elapsed, False

        sleep_fn(poll_interval_seconds)


def _start_select_or_failure(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    start_select_fn: Callable[..., uuid.UUID],
    apply_kwargs: dict[str, int],
    start_time: datetime,
    now_fn: Callable[[], datetime],
) -> tuple[uuid.UUID | None, MonitorResult | None]:
    try:
        task_id = start_select_fn(uow, user_id, assembly_id, celery_apply_kwargs=apply_kwargs)
    except (
        AssemblyNotFoundError,
        GoogleSheetConfigNotFoundError,
        InvalidSelection,
        InsufficientPermissions,
    ) as exc:
        elapsed = (now_fn() - start_time).total_seconds()
        cls_name = type(exc).__name__
        logger.warning("monitor selection failed to start", error=cls_name, message=str(exc))
        return None, MonitorResult(
            success=False,
            duration_seconds=elapsed,
            message=f"failed to start monitor selection ({cls_name})",
            error=str(exc),
        )
    return task_id, None


def run_monitoring_selection(
    uow: AbstractUnitOfWork,
    *,
    start_select_fn: Callable[..., uuid.UUID] = start_gsheet_select_task,
    start_cleanup_fn: Callable[..., uuid.UUID] = start_gsheet_manage_tabs_task,
    health_check_fn: Callable[..., None] = check_and_update_task_health,
    poll_status_fn: Callable[..., object] = get_selection_run_status,
    now_fn: Callable[[], datetime] = _aware_utcnow,
    sleep_fn: Callable[[float], None] = time.sleep,
    wrapper_timeout_seconds: int = MONITOR_WRAPPER_TIMEOUT_SECONDS,
    celery_time_limit_seconds: int = MONITOR_CELERY_TIME_LIMIT_SECONDS,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
) -> MonitorResult:
    """Run one full monitor selection (start → poll → cleanup) end-to-end.

    Production callers (CLI, beat) call without overriding the injected
    dependencies; tests substitute fakes for the boundary calls.
    """
    assembly_id = config.get_monitor_assembly_id()
    user_id = config.get_monitor_user_id()
    if assembly_id is None or user_id is None:
        return MonitorResult(
            success=False,
            not_configured=True,
            message="monitoring not configured",
        )

    start_time = now_fn()
    apply_kwargs = {
        "time_limit": celery_time_limit_seconds,
        "soft_time_limit": max(1, celery_time_limit_seconds - _SOFT_TIME_LIMIT_GAP_SECONDS),
    }

    task_id, failure = _start_select_or_failure(
        uow,
        user_id,
        assembly_id,
        start_select_fn=start_select_fn,
        apply_kwargs=apply_kwargs,
        start_time=start_time,
        now_fn=now_fn,
    )
    if failure is not None:
        return failure
    assert task_id is not None

    record, elapsed, timed_out = _poll_until_finished(
        uow,
        task_id,
        start_time=start_time,
        wrapper_timeout_seconds=wrapper_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        health_check_fn=health_check_fn,
        poll_status_fn=poll_status_fn,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
    )

    run_url = _safe_run_url(assembly_id, task_id)

    if timed_out:
        return MonitorResult(
            success=False,
            task_id=task_id,
            duration_seconds=elapsed,
            message="monitor exceeded wall-clock timeout",
            run_url=run_url,
        )

    if record is None:
        return MonitorResult(
            success=False,
            task_id=task_id,
            duration_seconds=elapsed,
            message="monitor selection record not found after dispatch",
            run_url=run_url,
        )

    if record.is_completed:
        try:
            start_cleanup_fn(uow, user_id, assembly_id, dry_run=False)
        except Exception as exc:
            logger.warning("monitor cleanup dispatch failed", error=str(exc))
        return MonitorResult(
            success=True,
            task_id=task_id,
            duration_seconds=elapsed,
            message="monitor selection completed successfully",
            run_url=run_url,
        )

    return MonitorResult(
        success=False,
        task_id=task_id,
        duration_seconds=elapsed,
        message=f"monitor selection finished with status {record.status.value}",
        error=record.error_message,
        run_url=run_url,
    )


def get_latest_monitor_run(
    uow: AbstractUnitOfWork,
    task_type: SelectionTaskType = SelectionTaskType.SELECT_GSHEET,
) -> SelectionRunRecord | None:
    """Most recent SelectionRunRecord of a given type for the monitor assembly.

    Defaults to SELECT_GSHEET because that is the heartbeat. Pass
    DELETE_OLD_TABS to inspect the latest cleanup pass.
    """
    assembly_id = config.get_monitor_assembly_id()
    if assembly_id is None:
        return None
    return uow.selection_run_records.get_latest_for_assembly(assembly_id, task_type=task_type)
