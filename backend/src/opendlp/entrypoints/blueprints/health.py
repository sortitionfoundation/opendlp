"""ABOUTME: Health check endpoint for monitoring service status
ABOUTME: Reports database, celery, and system configuration status as JSON"""

from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue

from opendlp import bootstrap
from opendlp.entrypoints.celery.app import app as celery_app
from opendlp.entrypoints.context_processors import get_opendlp_version, get_service_account_email

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

    HTTP status 200 if everything is healthy, 500 if any check fails.
    """
    # Perform all checks
    db_ok, user_count = check_database()
    celery_ok = check_celery_worker()
    service_account = get_service_account_email()
    version = get_opendlp_version()

    # Determine overall health status
    is_healthy = db_ok and celery_ok and service_account != "UNKNOWN" and version != "UNKNOWN"

    # Build response
    response_data = {
        "database_ok": db_ok,
        "user_count": user_count,
        "celery_worker_running": celery_ok,
        "service_account_email": service_account,
        "version": version,
    }

    # Return appropriate status code
    status_code = 200 if is_healthy else 500

    return jsonify(response_data), status_code
