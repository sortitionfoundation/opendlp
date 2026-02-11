"""ABOUTME: Backoffice routes for admin UI using Pines UI + Tailwind CSS
ABOUTME: Provides /backoffice/* routes with separate design system from GOV.UK pages"""

import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.service_layer.assembly_service import get_assembly_with_permissions
from opendlp.service_layer.exceptions import NotFoundError
from opendlp.service_layer.user_service import get_user_assemblies
from opendlp.translations import gettext as _

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


@backoffice_bp.route("/assembly/<uuid:assembly_id>")
@login_required
def view_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly details page."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        return render_template("backoffice/assembly_details.html", assembly=assembly), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Backoffice assembly error for user {current_user.id}: {e}")
        flash(_("An error occurred while loading the assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
