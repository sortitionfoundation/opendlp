"""ABOUTME: Backoffice routes for admin UI using Pines UI + Tailwind CSS
ABOUTME: Provides /backoffice/* routes with separate design system from GOV.UK pages"""

from flask import Blueprint, current_app, render_template
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.service_layer.user_service import get_user_assemblies

backoffice_bp = Blueprint("backoffice", __name__, template_folder="backoffice")


@backoffice_bp.route("/showcase")
def showcase() -> ResponseReturnValue:
    """Component showcase page demonstrating the backoffice design system."""
    return render_template("backoffice/showcase.html"), 200


@backoffice_bp.route("/dashboard")
@login_required
def dashboard() -> ResponseReturnValue:
    """Backoffice dashboard showing user's assemblies."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assemblies = get_user_assemblies(uow, current_user.id)

        return render_template("backoffice/dashboard.html", assemblies=assemblies), 200
    except Exception as e:
        current_app.logger.error(f"Backoffice dashboard error for user {current_user.id}: {e}")
        return render_template("backoffice/dashboard.html", assemblies=[]), 500
