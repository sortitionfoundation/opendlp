"""ABOUTME: Health check endpoint for monitoring service status
ABOUTME: Reports database, celery, and system configuration status as JSON"""

import os
from datetime import UTC, datetime

import structlog
from flask import Blueprint, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from opendlp import bootstrap
from opendlp.config import to_bool
from opendlp.entrypoints.celery.app import app as celery_app
from opendlp.entrypoints.context_processors import (
    get_opendlp_version,
    get_service_account_email,
    service_account_email_problem,
)
from opendlp.service_layer.monitoring import MonitorSelectionStatus, check_monitor_selection, truncate

health_bp = Blueprint("health", __name__)

logger = structlog.get_logger(__name__)

# Record process start time at module load
_PROCESS_STARTED_AT = datetime.now(UTC)


def check_database() -> tuple[bool, int | str]:
    """
    Check database connectivity and return user count.

    Returns:
        Tuple of (success: bool, user_count: int | "UNKNOWN")
    """
    try:
        uow = bootstrap.get_flask_uow()
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
        logger.warning("Invalid OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY format", expiry_str=expiry_str)
        return None, "UNKNOWN"


def _check_monitor_selection() -> MonitorSelectionStatus:
    """Bootstrap a Unit of Work and call the service-layer check.

    Returns an UNKNOWN status if bootstrap itself fails (eg. DB unreachable).
    """
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            return check_monitor_selection(uow)
    except Exception as error:
        return MonitorSelectionStatus(
            status="UNKNOWN",
            message=truncate(f"could not query monitor selection records: {error}"),
        )


def _build_monitor_payload() -> tuple[dict[str, object], MonitorSelectionStatus]:
    monitor = _check_monitor_selection()
    payload: dict[str, object] = {
        "monitor_selection_status": monitor.status,
        "monitor_selection_last_run_at": monitor.last_run_at.isoformat() if monitor.last_run_at else None,
        "monitor_selection_message": monitor.message,
        "monitor_selection_last_run_url": monitor.run_url,
        "monitor_cleanup_status": monitor.cleanup_status,
        "monitor_selection_consecutive_failures": monitor.consecutive_failures,
        "monitor_selection_recent_failures": [
            {
                "error_class": failure.error_class,
                "status": failure.status,
                "at": failure.at.isoformat() if failure.at else None,
            }
            for failure in monitor.recent_failures
        ],
    }
    return payload, monitor


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

    # Determine overall health status
    is_healthy = all((db_ok, celery_ok, service_account_ok, version_ok, ms_expiry_ok))

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

    HTTP status 200 when status is OK, PENDING, or DEGRADED; 500 otherwise
    (including NOT_CONFIGURED, STALE, FAILED, UNKNOWN). DEGRADED means the
    latest run failed but not enough times in a row to page anyone yet.
    """
    payload, monitor = _build_monitor_payload()
    is_healthy = monitor.status in ("OK", "PENDING", "DEGRADED") and monitor.cleanup_status != "FAILED"
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
