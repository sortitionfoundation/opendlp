"""ABOUTME: Health check endpoint for monitoring service status
ABOUTME: Reports database, celery, and system configuration status as JSON"""

from datetime import UTC, datetime

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

health_bp = Blueprint("health", __name__)


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
    response_data = {
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
