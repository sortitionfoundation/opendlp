"""ABOUTME: Main application routes for dashboard and assembly listing
ABOUTME: Handles home page, dashboard, and assembly views with login requirements"""

from flask import Blueprint, current_app, redirect, render_template
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.service_layer.user_service import get_user_assemblies

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index() -> ResponseReturnValue:
    """Home page - redirects to dashboard if logged in, otherwise shows landing page."""
    if current_user.is_authenticated:
        return redirect("main.dashboard")
    return render_template("main/index.html"), 200


@main_bp.route("/dashboard")
@login_required
def dashboard() -> ResponseReturnValue:
    """User dashboard showing accessible assemblies."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assemblies = get_user_assemblies(uow, current_user.id)

        return render_template("main/dashboard.html", assemblies=assemblies), 200
    except Exception as e:
        current_app.logger.error(f"Dashboard error for user {current_user.id}: {e}")
        return render_template("errors/500.html"), 500


@main_bp.route("/assemblies")
@login_required
def assemblies() -> ResponseReturnValue:
    """List all assemblies user has access to."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            user_assemblies = get_user_assemblies(uow, current_user.id)

        return render_template("main/assemblies.html", assemblies=user_assemblies), 200
    except Exception as e:
        current_app.logger.error(f"Assemblies list error for user {current_user.id}: {e}")
        return render_template("errors/500.html"), 500
