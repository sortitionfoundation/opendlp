"""ABOUTME: Backoffice routes for admin UI using Pines UI + Tailwind CSS
ABOUTME: Provides /backoffice/* routes with separate design system from GOV.UK pages"""

import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.entrypoints.forms import EditAssemblyForm
from opendlp.service_layer.assembly_service import get_assembly_with_permissions, update_assembly
from opendlp.service_layer.exceptions import InsufficientPermissions, NotFoundError
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


@backoffice_bp.route("/assembly/<uuid:assembly_id>/edit", methods=["GET", "POST"])
@login_required
def edit_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice edit assembly page."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        form = EditAssemblyForm(obj=assembly)

        if form.validate_on_submit():
            try:
                with uow:
                    updated_assembly = update_assembly(
                        uow=uow,
                        assembly_id=assembly_id,
                        user_id=current_user.id,
                        title=form.title.data,
                        question=form.question.data or "",
                        first_assembly_date=form.first_assembly_date.data,
                        number_to_select=form.number_to_select.data,
                    )

                flash(_("Assembly '%(title)s' updated successfully", title=updated_assembly.title), "success")
                return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
            except InsufficientPermissions as e:
                current_app.logger.warning(
                    f"Insufficient permissions to edit assembly {assembly_id} for user {current_user.id}: {e}"
                )
                flash(_("You don't have permission to edit this assembly"), "error")
                return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
            except NotFoundError as e:
                current_app.logger.error(
                    f"Assembly or user not found while editing assembly {assembly_id} user {current_user.id}: {e}"
                )
                flash(_("An error occurred while updating the assembly"), "error")
            except Exception as e:
                current_app.logger.error(f"Edit assembly error for assembly {assembly_id} user {current_user.id}: {e}")
                flash(_("An error occurred while updating the assembly"), "error")

        return render_template(
            "backoffice/edit_assembly.html",
            form=form,
            assembly=assembly,
        ), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for edit by user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to access assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to edit this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
