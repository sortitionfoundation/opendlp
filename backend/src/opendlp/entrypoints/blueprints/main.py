"""ABOUTME: Main application routes for dashboard and assembly listing
ABOUTME: Handles home page, dashboard, and assembly views with login requirements"""

import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.service_layer.assembly_service import (
    add_assembly_gsheet,
    create_assembly,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    remove_assembly_gsheet,
    update_assembly,
    update_assembly_gsheet,
)
from opendlp.service_layer.exceptions import InsufficientPermissions
from opendlp.service_layer.user_service import get_user_assemblies
from opendlp.translations import gettext as _

from ..forms import CreateAssemblyForm, CreateAssemblyGSheetForm, EditAssemblyForm, EditAssemblyGSheetForm

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
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)

        return render_template("main/view_assembly.html", assembly=assembly, gsheet=gsheet), 200
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


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet", methods=["GET", "POST"])
@login_required
def manage_assembly_gsheet(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Create or edit Google Spreadsheet configuration for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            existing_gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)

        # Choose form based on whether gsheet exists
        if existing_gsheet:
            form = EditAssemblyGSheetForm(obj=existing_gsheet)
            template = "main/edit_assembly_gsheet.html"
            action = "edit"
        else:
            form = CreateAssemblyGSheetForm()
            template = "main/create_assembly_gsheet.html"
            action = "create"

        if form.validate_on_submit():
            try:
                if action == "create":
                    with uow:
                        add_assembly_gsheet(
                            uow=uow,
                            assembly_id=assembly_id,
                            user_id=current_user.id,
                            url=form.url.data,  # type: ignore[arg-type]
                            team=form.team.data,
                            select_registrants_tab=form.select_registrants_tab.data,
                            select_targets_tab=form.select_targets_tab.data,
                            replace_registrants_tab=form.replace_registrants_tab.data,
                            replace_targets_tab=form.replace_targets_tab.data,
                            id_column=form.id_column.data,
                            check_same_address=form.check_same_address.data,
                            generate_remaining_tab=form.generate_remaining_tab.data,
                        )
                    flash(_("Google Spreadsheet configuration created successfully"), "success")
                else:
                    with uow:
                        update_assembly_gsheet(
                            uow=uow,
                            assembly_id=assembly_id,
                            user_id=current_user.id,
                            url=form.url.data,
                            team=form.team.data,
                            select_registrants_tab=form.select_registrants_tab.data,
                            select_targets_tab=form.select_targets_tab.data,
                            replace_registrants_tab=form.replace_registrants_tab.data,
                            replace_targets_tab=form.replace_targets_tab.data,
                            id_column=form.id_column.data,
                            check_same_address=form.check_same_address.data,
                            generate_remaining_tab=form.generate_remaining_tab.data,
                        )
                    flash(_("Google Spreadsheet configuration updated successfully"), "success")

                return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
            except InsufficientPermissions as e:
                current_app.logger.warning(
                    f"Insufficient permissions to {action} gsheet for assembly {assembly_id} by user {current_user.id}: {e}"
                )
                flash(_("You don't have permission to manage Google Spreadsheet for this assembly"), "error")
                return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
            except ValueError as e:
                current_app.logger.error(
                    f"Gsheet {action} validation error for assembly {assembly_id} user {current_user.id}: {e}"
                )
                flash(_("Please check your input and try again"), "error")
            except Exception as e:
                current_app.logger.error(
                    f"Gsheet {action} error for assembly {assembly_id} user {current_user.id}: {e}"
                )
                flash(_("An error occurred while saving the Google Spreadsheet configuration"), "error")

        return render_template(template, form=form, assembly=assembly, gsheet=existing_gsheet), 200
    except ValueError as e:
        current_app.logger.warning(
            f"Assembly {assembly_id} not found for gsheet management by user {current_user.id}: {e}"
        )
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to view assembly {assembly_id} for gsheet management by user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Gsheet management page error for assembly {assembly_id} user {current_user.id}: {e}")
        return render_template("errors/500.html"), 500


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet/delete", methods=["POST"])
@login_required
def delete_assembly_gsheet(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Remove Google Spreadsheet configuration from an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            remove_assembly_gsheet(uow, assembly_id, current_user.id)

        flash(_("Google Spreadsheet configuration removed successfully"), "success")
        return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
    except ValueError as e:
        current_app.logger.warning(f"Assembly or gsheet not found for deletion by user {current_user.id}: {e}")
        flash(_("Google Spreadsheet configuration not found"), "error")
        return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to delete gsheet for assembly {assembly_id} by user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to manage Google Spreadsheet for this assembly"), "error")
        return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Gsheet deletion error for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("An error occurred while removing the Google Spreadsheet configuration"), "error")
        return redirect(url_for("main.view_assembly", assembly_id=assembly_id))


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
