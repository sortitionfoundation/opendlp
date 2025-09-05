"""ABOUTME: Main application routes for dashboard and assembly listing
ABOUTME: Handles home page, dashboard, and assembly views with login requirements"""

import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.service_layer.assembly_service import (
    create_assembly,
    get_assembly_with_permissions,
    update_assembly,
)
from opendlp.service_layer.exceptions import InsufficientPermissions
from opendlp.service_layer.user_service import get_user_assemblies
from opendlp.translations import gettext as _

from ..forms import CreateAssemblyForm, EditAssemblyForm

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index() -> ResponseReturnValue:
    """Home page - redirects to dashboard if logged in, otherwise shows landing page."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
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


@main_bp.route("/assemblies/<uuid:assembly_id>")
@login_required
def view_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """View a single assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        return render_template("main/view_assembly.html", assembly=assembly), 200
    except ValueError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        # TODO: consider change to "Assembly not found" so as not to leak info
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View assembly error for assembly {assembly_id} user {current_user.id}: {e}")
        return render_template("errors/500.html"), 500


@main_bp.route("/assemblies/new", methods=["GET", "POST"])
@login_required
def create_assembly_page() -> ResponseReturnValue:
    """Create a new assembly."""
    form = CreateAssemblyForm()

    if form.validate_on_submit():
        try:
            uow = bootstrap.bootstrap()
            with uow:
                # ignoring warning for title - it will not be None due to form validation
                assembly = create_assembly(
                    uow=uow,
                    title=form.title.data,  # type: ignore[arg-type]
                    created_by_user_id=current_user.id,
                    question=form.question.data or "",
                    gsheet_url=form.gsheet_url.data or "",
                    first_assembly_date=form.first_assembly_date.data,
                )

            flash(_("Assembly '%(title)s' created successfully", title=assembly.title), "success")
            return redirect(url_for("main.view_assembly", assembly_id=assembly.id))
        except InsufficientPermissions as e:
            current_app.logger.warning(f"Insufficient permissions to create assembly for user {current_user.id}: {e}")
            flash(_("You don't have permission to create assemblies"), "error")
            return redirect(url_for("main.dashboard"))
        except ValueError as e:
            current_app.logger.error(f"Create assembly validation error for user {current_user.id}: {e}")
            flash(_("Please check your input and try again"), "error")
        except Exception as e:
            current_app.logger.error(f"Create assembly error for user {current_user.id}: {e}")
            flash(_("An error occurred while creating the assembly"), "error")

    return render_template("main/create_assembly.html", form=form), 200


@main_bp.route("/assemblies/<uuid:assembly_id>/edit", methods=["GET", "POST"])
@login_required
def edit_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Edit an assembly."""
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
                        gsheet_url=form.gsheet_url.data or "",
                        first_assembly_date=form.first_assembly_date.data,
                    )

                flash(_("Assembly '%(title)s' updated successfully", title=updated_assembly.title), "success")
                return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
            except InsufficientPermissions as e:
                current_app.logger.warning(
                    f"Insufficient permissions to edit assembly {assembly_id} for user {current_user.id}: {e}"
                )
                flash(_("You don't have permission to edit this assembly"), "error")
                return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
            except ValueError as e:
                current_app.logger.error(
                    f"Edit assembly validation error for assembly {assembly_id} user {current_user.id}: {e}"
                )
                flash(_("Please check your input and try again"), "error")
            except Exception as e:
                current_app.logger.error(f"Edit assembly error for assembly {assembly_id} user {current_user.id}: {e}")
                flash(_("An error occurred while updating the assembly"), "error")

        return render_template("main/edit_assembly.html", form=form, assembly=assembly), 200
    except ValueError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for edit by user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to view assembly {assembly_id} for edit by user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Edit assembly page error for assembly {assembly_id} user {current_user.id}: {e}")
        return render_template("errors/500.html"), 500
