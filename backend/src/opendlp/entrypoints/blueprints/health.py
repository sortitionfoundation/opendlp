"""ABOUTME: Health check endpoint for monitoring service status
ABOUTME: Reports database, celery, and system configuration status as JSON"""

import os
import uuid
from datetime import UTC, datetime, timedelta

from flask import Blueprint, current_app, jsonify, request, url_for
from flask.typing import ResponseReturnValue

from opendlp import bootstrap, config
from opendlp.config import to_bool
from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.entrypoints.celery.app import app as celery_app
from opendlp.entrypoints.context_processors import (
    get_opendlp_version,
    get_service_account_email,
    service_account_email_problem,
)
from opendlp.service_layer.monitoring import get_latest_monitor_run

health_bp = Blueprint("health", __name__)

# Record process start time at module load
_PROCESS_STARTED_AT = datetime.now(UTC)


def check_database() -> tuple[bool, int | str]:
    """
    Check database connectivity and return user count.

    Returns:
        Tuple of (success: bool, user_count: int | "UNKNOWN")
    """
    try:
        uow = bootstrap.bootstrap()
        with uow:
            # Get all users and count them
            all_users = list(uow.users.all())
            user_count = len(all_users)
        return True, user_count
    except Exception:
        return False, "UNKNOWN"


def check_celery_worker() -> bool:
    """
    Check if celery worker is running.

    Returns:
        True if at least one worker is active, False otherwise
    """
    try:
        # Use celery inspect to check for active workers
        inspect = celery_app.control.inspect()
        # Get active workers
        active_workers = inspect.active()
        # active_workers will be None if no workers respond, or a dict of workers
        return active_workers is not None and len(active_workers) > 0
    except Exception:
        return False


def check_microsoft_oauth_expiry() -> tuple[int | None, str]:
    """
    Check Microsoft OAuth client secret expiry status.

    Returns:
        Tuple of (days_to_expiry: int | None, status: str)
        - days_to_expiry: days remaining (negative if expired), None if not applicable
        - status: "NO_MICROSOFT_OAUTH" (MS OAuth not configured),
                  "OK" (>30 days), "WARNING" (≤30 days), "EXPIRED" (passed), "UNKNOWN" (expiry not set)
    """
    # First check if Microsoft OAuth is configured at all
    client_id = current_app.config.get("OAUTH_MICROSOFT_CLIENT_ID", "")
    if not client_id:
        return None, "NO_MICROSOFT_OAUTH"

    # Microsoft OAuth is configured, check expiry date
    expiry_str = current_app.config.get("OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY", "")

    # If expiry date not configured, return UNKNOWN
    if not expiry_str:
        return None, "UNKNOWN"

    try:
        # Parse the expiry date (format: YYYY-MM-DD)
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        today = datetime.now(UTC).date()

        # Calculate days remaining
        days_remaining = (expiry_date - today).days

        # Determine status
        if days_remaining < 0:
            status = "EXPIRED"
        elif days_remaining <= 30:
            status = "WARNING"
        else:
            status = "OK"

        return days_remaining, status

    except ValueError:
        # Invalid date format
        current_app.logger.warning(f"Invalid OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY format: {expiry_str}")
        return None, "UNKNOWN"


_FAILED_TERMINAL_STATUSES = (SelectionRunStatus.FAILED, SelectionRunStatus.CANCELLED)


def _truncate(text: str, limit: int = 200) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _build_run_url(assembly_id: uuid.UUID, task_id: uuid.UUID) -> str:
    try:
        return url_for(
            "gsheets.view_assembly_selection_with_run",
            assembly_id=assembly_id,
            run_id=task_id,
            _external=True,
        )
    except Exception:
        return ""


def _classify_select_record(
    record: SelectionRunRecord | None,
    max_age: timedelta,
    now: datetime,
) -> tuple[str, datetime | None, str]:
    """Classify the most recent SELECT_GSHEET record.

    Returns (status, last_run_at, message).
    """
    if record is None:
        return "STALE", None, "no monitor selection runs recorded yet"

    age = now - (record.created_at or now)
    last_run_at = record.created_at

    if record.status in _FAILED_TERMINAL_STATUSES:
        return (
            "FAILED",
            last_run_at,
            _truncate(record.error_message or f"latest selection {record.status.value}"),
        )

    if record.is_completed:
        if age > max_age:
            return "STALE", last_run_at, "latest successful selection is older than threshold"
        return "OK", last_run_at, "latest selection completed successfully"

    # PENDING or RUNNING
    if age > max_age:
        return "STALE", last_run_at, "selection has been pending/running longer than threshold"
    return "PENDING", last_run_at, f"selection is currently {record.status.value}"


def _classify_cleanup_record(record: SelectionRunRecord | None) -> str:
    if record is None:
        return "OK"
    if record.status in _FAILED_TERMINAL_STATUSES:
        return "FAILED"
    return "OK"


def check_monitor_selection() -> tuple[str, datetime | None, str, str, str]:
    """Check the monitor assembly's most recent runs.

    Returns (status, last_run_at, message, run_url, cleanup_status).

    status:
        "NOT_CONFIGURED" - MONITOR_ASSEMBLY_ID is not set
        "OK"             - latest SELECT_GSHEET COMPLETED within max-age window
        "STALE"          - latest SELECT_GSHEET stale, pending too long, or absent
        "FAILED"         - latest SELECT_GSHEET in a terminal-failed state
        "PENDING"        - latest SELECT_GSHEET in flight within window
        "UNKNOWN"        - bootstrap or DB query failed

    cleanup_status:
        "OK" or "FAILED" — based on the latest DELETE_OLD_TABS record (if any).
    """
    assembly_id = config.get_monitor_assembly_id()
    if assembly_id is None:
        return "NOT_CONFIGURED", None, "MONITOR_ASSEMBLY_ID is not set", "", "OK"

    try:
        uow = bootstrap.bootstrap()
        with uow:
            select_record = get_latest_monitor_run(uow, task_type=SelectionTaskType.SELECT_GSHEET)
            cleanup_record = get_latest_monitor_run(uow, task_type=SelectionTaskType.DELETE_OLD_TABS)
    except Exception:
        return "UNKNOWN", None, "could not query monitor selection records", "", "OK"

    max_age = timedelta(minutes=config.get_monitor_health_max_age_minutes())
    now = datetime.now(UTC)

    status, last_run_at, message = _classify_select_record(select_record, max_age, now)
    cleanup_status = _classify_cleanup_record(cleanup_record)

    if cleanup_status == "FAILED" and status == "OK":
        # Cleanup failure overrides the otherwise-clean SELECT result for the
        # aggregate status, since the operator needs to see the failure.
        status = "FAILED"
        message = "tab cleanup failed after latest selection"
        if cleanup_record is not None and cleanup_record.error_message:
            message = _truncate(cleanup_record.error_message)

    run_url = ""
    if select_record is not None:
        run_url = _build_run_url(select_record.assembly_id, select_record.task_id)

    return status, last_run_at, message, run_url, cleanup_status


def _build_monitor_payload() -> tuple[dict[str, object], str]:
    status, last_run_at, message, run_url, cleanup_status = check_monitor_selection()
    payload: dict[str, object] = {
        "monitor_selection_status": status,
        "monitor_selection_last_run_at": last_run_at.isoformat() if last_run_at else None,
        "monitor_selection_message": message,
        "monitor_selection_last_run_url": run_url,
        "monitor_cleanup_status": cleanup_status,
    }
    return payload, status


@health_bp.route("/health")
def health_check() -> ResponseReturnValue:
    """
    Health check endpoint returning JSON with system status.

    Returns:
        JSON response with:
        - database_ok: bool
        - user_count: int | "UNKNOWN"
        - celery_worker_running: bool
        - service_account_email: str
        - version: str
        - oauth_microsoft_days_to_expiry: int | None (days remaining, negative if expired)
        - oauth_microsoft_expiry_status: "NO_MICROSOFT_OAUTH" | "OK" | "WARNING" | "EXPIRED" | "UNKNOWN"

    Query parameters:
        - fail_on_warning: if "true", returns 500 on WARNING or UNKNOWN status
                          (NO_MICROSOFT_OAUTH never causes failure)

    HTTP status 200 if everything is healthy, 500 if any check fails.
    """
    # Perform all checks
    db_ok, user_count = check_database()
    celery_ok = check_celery_worker()

    service_account = get_service_account_email()
    service_account_ok = True

    version = get_opendlp_version()
    version_ok = version != "UNKNOWN"

    # Microsoft OAuth expiry affects health status (but only if Microsoft OAuth is configured)
    # status can be NO_MICROSOFT_OAUTH, UNKNOWN, EXPIRED, WARNING or OK
    # NO_MICROSOFT_OAUTH never causes failure
    ms_days_to_expiry, ms_expiry_status = check_microsoft_oauth_expiry()
    ms_expiry_ok = ms_expiry_status != "EXPIRED"

    # Check fail_on_warning query parameter
    try:
        fail_on_warning = to_bool(request.args.get("fail_on_warning", ""))
    except ValueError:
        fail_on_warning = False
    # if fail_on_warning, then fail for more conditions
    if fail_on_warning:
        if ms_expiry_status in ["EXPIRED", "WARNING", "UNKNOWN"]:
            ms_expiry_ok = False
        if service_account == "UNKNOWN":
            service_account_ok = False

    monitor_payload, monitor_status = _build_monitor_payload()
    monitor_ok = monitor_status in ("OK", "PENDING", "NOT_CONFIGURED")
    cleanup_ok = monitor_payload["monitor_cleanup_status"] != "FAILED"

    # Determine overall health status
    is_healthy = all((db_ok, celery_ok, service_account_ok, version_ok, ms_expiry_ok, monitor_ok, cleanup_ok))

    # Build response
    response_data: dict[str, object] = {
        "database_ok": db_ok,
        "user_count": user_count,
        "celery_worker_running": celery_ok,
        "service_account_email": service_account,
        "version": version,
        "oauth_microsoft_days_to_expiry": ms_days_to_expiry,
        "oauth_microsoft_expiry_status": ms_expiry_status,
    }
    response_data.update(monitor_payload)

    # do some debugging, but only if there is an issue
    if service_account == "UNKNOWN":
        response_data["service_account_email_problem"] = service_account_email_problem()

    # Return appropriate status code
    status_code = 200 if is_healthy else 500

    return jsonify(response_data), status_code


@health_bp.route("/health/monitor_selection")
def monitor_selection_health() -> ResponseReturnValue:
    """
    Focused health endpoint for the end-to-end monitor selection feature.

    Unlike /health, this endpoint treats NOT_CONFIGURED as unhealthy because
    pointing a watcher at this URL is itself a declaration that monitoring
    should be live.

    HTTP status 200 when status is OK or PENDING; 500 otherwise (including
    NOT_CONFIGURED, STALE, FAILED, UNKNOWN).
    """
    payload, status = _build_monitor_payload()
    cleanup_failed = payload.get("monitor_cleanup_status") == "FAILED"
    is_healthy = status in ("OK", "PENDING") and not cleanup_failed
    status_code = 200 if is_healthy else 500
    return jsonify(payload), status_code


@health_bp.route("/health/bdd")
def bdd_health_check() -> ResponseReturnValue:
    """
    BDD test configuration endpoint.

    Returns key environment settings so the BDD test fixture can verify
    that a reused server is properly configured. Only available when
    FLASK_ENV starts with "testing".
    """
    flask_env = os.environ.get("FLASK_ENV", "development")
    if not flask_env.startswith("testing"):
        return jsonify({"error": "Not available outside testing"}), 404

    age = datetime.now(UTC) - _PROCESS_STARTED_AT
    running_hours = round(age.total_seconds() / 3600, 1)

    return jsonify({
        "flask_env": flask_env,
        "db_port": os.environ.get("DB_PORT", ""),
        "redis_port": os.environ.get("REDIS_PORT", ""),
        "use_csv_data_source": os.environ.get("USE_CSV_DATA_SOURCE", ""),
        "running_hours": running_hours,
    }), 200
