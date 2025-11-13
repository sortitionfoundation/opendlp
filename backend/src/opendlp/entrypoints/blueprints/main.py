"""ABOUTME: Main application routes for dashboard and assembly listing
ABOUTME: Handles home page, dashboard, and assembly views with login requirements"""

import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.domain.value_objects import AssemblyRole
from opendlp.service_layer.assembly_service import (
    create_assembly,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    update_assembly,
)
from opendlp.service_layer.exceptions import InsufficientPermissions
from opendlp.service_layer.permissions import has_global_admin
from opendlp.service_layer.user_service import get_user_assemblies, grant_user_assembly_role, revoke_user_assembly_role
from opendlp.translations import gettext as _

from ..forms import AddUserToAssemblyForm, CreateAssemblyForm, EditAssemblyForm

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
    """View assembly details page."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        return render_template(
            "main/view_assembly_details.html",
            assembly=assembly,
            current_tab="details",
        ), 200
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
        current_app.logger.exception("stacktrace")
        return render_template("errors/500.html"), 500


@main_bp.route("/assemblies/<uuid:assembly_id>/data")
@login_required
def view_assembly_data(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """View assembly data and selection page."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)

        return render_template(
            "main/view_assembly_data.html",
            assembly=assembly,
            gsheet=gsheet,
            current_tab="data",
        ), 200
    except ValueError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View assembly data error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("stacktrace")
        return render_template("errors/500.html"), 500


@main_bp.route("/assemblies/<uuid:assembly_id>/members")
@login_required
def view_assembly_members(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """View assembly team members page."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

            # Get assembly users with their roles (efficient database query)
            assembly_users = uow.user_assembly_roles.get_users_with_roles_for_assembly(assembly_id)

            # Get all users not already assigned to this assembly (for add form)
            available_users = list(uow.users.get_users_not_in_assembly(assembly_id))

            # Check if current user can manage this assembly
            can_manage_assembly_users = has_global_admin(current_user)

        add_user_form = AddUserToAssemblyForm()

        return render_template(
            "main/view_assembly_members.html",
            assembly=assembly,
            assembly_users=assembly_users,
            available_users=available_users,
            can_manage_assembly_users=can_manage_assembly_users,
            add_user_form=add_user_form,
            current_tab="members",
        ), 200
    except ValueError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View assembly members error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("stacktrace")
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
                    first_assembly_date=form.first_assembly_date.data,
                    number_to_select=form.number_to_select.data,
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
                        number_to_select=form.number_to_select.data,
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


@main_bp.route("/assemblies/<uuid:assembly_id>/members", methods=["POST"])
@login_required
def add_user_to_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Add a user to an assembly with a specific role."""
    form = AddUserToAssemblyForm()

    try:
        uow = bootstrap.bootstrap()
        with uow:
            # Verify assembly exists and user can manage it
            if not has_global_admin(current_user):
                raise InsufficientPermissions(
                    action="add_user_to_assembly",
                    required_role="admin, global-organiser, or assembly manager",
                )

            if form.validate_on_submit():
                user_id = uuid.UUID(form.user_id.data)

                # Role is already an AssemblyRole enum from form coercion
                role = form.role.data
                assert isinstance(role, AssemblyRole)

                # Call service layer to add user to assembly
                grant_user_assembly_role(
                    uow=uow,
                    user_id=user_id,
                    assembly_id=assembly_id,
                    role=role,
                    current_user=current_user,
                )

                target_user = uow.users.get(user_id)
                if target_user:
                    flash(
                        _(
                            "%(user)s added to assembly with role %(role)s",
                            user=target_user.display_name,
                            role=role.value,
                        ),
                        "success",
                    )
                else:
                    flash(_("User added to assembly successfully"), "success")
            else:
                flash(_("Please check the form and try again"), "error")

        return redirect(url_for("main.view_assembly_members", assembly_id=assembly_id))

    except ValueError as e:
        current_app.logger.error(f"Invalid user ID for assembly {assembly_id}: {e}")
        flash(_("Invalid user selection"), "error")
        return redirect(url_for("main.view_assembly_members", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to add user to assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to add users to this assembly"), "error")
        return redirect(url_for("main.view_assembly_members", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(
            f"Unexpected error adding user to assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("An error occurred while adding the user to the assembly"), "error")
        return redirect(url_for("main.view_assembly_members", assembly_id=assembly_id))


@main_bp.route("/assemblies/<uuid:assembly_id>/members/<uuid:user_id>/remove", methods=["POST"])
@login_required
def remove_user_from_assembly(assembly_id: uuid.UUID, user_id: uuid.UUID) -> ResponseReturnValue:
    """Remove a user from an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            # Verify assembly exists and user can manage it
            if not has_global_admin(current_user):
                raise InsufficientPermissions(
                    action="remove_user_from_assembly",
                    required_role="admin, global-organiser, or assembly manager",
                )

            # Call service layer to remove user from assembly
            revoke_user_assembly_role(
                uow=uow,
                user_id=user_id,
                assembly_id=assembly_id,
                current_user=current_user,
            )

            target_user = uow.users.get(user_id)
            if target_user:
                flash(
                    _("%(user)s removed from assembly", user=target_user.display_name),
                    "success",
                )
            else:
                flash(_("User removed from assembly successfully"), "success")

        return redirect(url_for("main.view_assembly_members", assembly_id=assembly_id))

    except ValueError as e:
        current_app.logger.error(f"Error removing user from assembly {assembly_id}: {e}")
        flash(_("Could not remove user from assembly: %(error)s", error=str(e)), "error")
        return redirect(url_for("main.view_assembly_members", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to remove user from assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to remove users from this assembly"), "error")
        return redirect(url_for("main.view_assembly_members", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(
            f"Unexpected error removing user from assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("An error occurred while removing the user from the assembly"), "error")
        return redirect(url_for("main.view_assembly_members", assembly_id=assembly_id))


@main_bp.route("/assemblies/<uuid:assembly_id>/search-users")
@login_required
def search_users(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Search for users not yet added to the assembly.

    HTMX endpoint that returns HTML fragment with matching users.
    The search term is sent as 'user_search' form parameter from HTMX.
    """
    try:
        # HTMX sends the input value as a form parameter with the input's name
        search_term = request.args.get("user_search", "").strip()

        uow = bootstrap.bootstrap()
        with uow:
            # Verify assembly exists and user can manage it
            if not has_global_admin(current_user):
                raise InsufficientPermissions(
                    action="search_users_for_assembly",
                    required_role="admin, global-organiser, or assembly manager",
                )

            # Search for matching users not in assembly
            matching_users = uow.users.search_users_not_in_assembly(assembly_id, search_term) if search_term else []

        return render_template(
            "main/search_user_results.html",
            users=matching_users,
            search_term=search_term,
        ), 200

    except InsufficientPermissions:
        return render_template("main/search_user_results.html", users=[], search_term=""), 403
    except Exception as e:
        current_app.logger.error(f"Error searching users for assembly {assembly_id}: {e}")
        return render_template("main/search_user_results.html", users=[], search_term=""), 500
