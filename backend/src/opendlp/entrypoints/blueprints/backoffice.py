"""ABOUTME: Backoffice routes for admin UI using Pines UI + Tailwind CSS
ABOUTME: Provides /backoffice/* routes with separate design system from GOV.UK pages"""

import uuid

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.bootstrap import get_email_adapter, get_template_renderer, get_url_generator
from opendlp.domain.value_objects import AssemblyRole
from opendlp.entrypoints.forms import (
    AddUserToAssemblyForm,
    CreateAssemblyForm,
    CreateAssemblyGSheetForm,
    EditAssemblyForm,
    EditAssemblyGSheetForm,
)
from opendlp.service_layer.assembly_service import (
    add_assembly_gsheet,
    create_assembly,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    remove_assembly_gsheet,
    update_assembly,
    update_assembly_gsheet,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, NotFoundError
from opendlp.service_layer.permissions import has_global_admin
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.service_layer.user_service import get_user_assemblies, grant_user_assembly_role, revoke_user_assembly_role
from opendlp.translations import gettext as _

backoffice_bp = Blueprint("backoffice", __name__)


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


@backoffice_bp.route("/assembly/new", methods=["GET", "POST"])
@login_required
def new_assembly() -> ResponseReturnValue:
    """Create a new assembly in backoffice."""
    form = CreateAssemblyForm()

    if form.validate_on_submit():
        try:
            uow = bootstrap.bootstrap()
            with uow:
                assembly = create_assembly(
                    uow=uow,
                    title=form.title.data or "",
                    created_by_user_id=current_user.id,
                    question=form.question.data or "",
                    first_assembly_date=form.first_assembly_date.data,
                    number_to_select=form.number_to_select.data or 0,
                )

            flash(_("Assembly '%(title)s' created successfully", title=assembly.title), "success")
            return redirect(url_for("backoffice.view_assembly", assembly_id=assembly.id))
        except InsufficientPermissions as e:
            current_app.logger.warning(f"Insufficient permissions to create assembly for user {current_user.id}: {e}")
            flash(_("You don't have permission to create assemblies"), "error")
            return redirect(url_for("backoffice.dashboard"))
        except NotFoundError as e:
            current_app.logger.error(f"User not found during assembly creation for user {current_user.id}: {e}")
            flash(_("An error occurred while creating the assembly"), "error")
            return redirect(url_for("backoffice.dashboard"))
        except Exception as e:
            current_app.logger.error(f"Create assembly error for user {current_user.id}: {e}")
            flash(_("An error occurred while creating the assembly"), "error")
            return redirect(url_for("backoffice.dashboard"))

    return render_template("backoffice/create_assembly.html", form=form), 200


@backoffice_bp.route("/assembly/<uuid:assembly_id>")
@login_required
def view_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly details page."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        return render_template("backoffice/assembly_details.html", assembly=assembly), 200
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        # TODO: consider change to "Assembly not found" so as not to leak info
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
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
                return redirect(url_for("backoffice.dashboard"))
            except Exception as e:
                current_app.logger.error(f"Edit assembly error for assembly {assembly_id} user {current_user.id}: {e}")
                flash(_("An error occurred while updating the assembly"), "error")
                return redirect(url_for("backoffice.dashboard"))

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


@backoffice_bp.route("/assembly/<uuid:assembly_id>/selection")
@login_required
def view_assembly_selection(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly selection page."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        # Check if gsheet is configured
        gsheet = None
        try:
            uow_gsheet = bootstrap.bootstrap()
            gsheet = get_assembly_gsheet(uow_gsheet, assembly_id, current_user.id)
        except Exception as gsheet_error:
            current_app.logger.error(f"Error loading gsheet config for selection: {gsheet_error}")
            gsheet = None

        return render_template(
            "backoffice/assembly_selection.html",
            assembly=assembly,
            gsheet=gsheet,
        ), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for selection page: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} selection: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View assembly selection error for assembly {assembly_id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while loading the selection page"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/data")
@login_required
def view_assembly_data(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly data page."""
    try:
        # Initialize context
        gsheet = None
        gsheet_mode = "new"
        gsheet_form = None
        data_source_locked = False
        google_service_account_email = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_EMAIL", "UNKNOWN")

        # Get assembly with permissions
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        # Always check if gsheet config exists - if so, lock to gsheet source
        try:
            uow_gsheet = bootstrap.bootstrap()
            gsheet = get_assembly_gsheet(uow_gsheet, assembly_id, current_user.id)
        except Exception as gsheet_error:
            current_app.logger.error(f"Error loading gsheet config: {gsheet_error}")
            current_app.logger.exception("Gsheet loading stacktrace:")
            gsheet = None

        # If gsheet config exists, force gsheet source and lock the selector
        if gsheet:
            data_source = "gsheet"
            data_source_locked = True
        else:
            # No config exists - allow user to choose source from query param
            data_source = request.args.get("source", "")
            if data_source not in ("gsheet", "csv", ""):
                data_source = ""

        # Set up gsheet form if gsheet source is selected
        if data_source == "gsheet":
            mode_param = request.args.get("mode", "")
            # Config exists: default to view, allow edit. No config: always show new form
            gsheet_mode = ("edit" if mode_param == "edit" else "view") if gsheet else "new"
            # Create form based on mode - form has defaults built in
            gsheet_form = EditAssemblyGSheetForm(obj=gsheet) if gsheet else CreateAssemblyGSheetForm()

        return render_template(
            "backoffice/assembly_data.html",
            assembly=assembly,
            data_source=data_source,
            data_source_locked=data_source_locked,
            gsheet=gsheet,
            gsheet_mode=gsheet_mode,
            gsheet_form=gsheet_form,
            google_service_account_email=google_service_account_email,
        ), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View assembly data error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while loading assembly data"), "error")
        return redirect(url_for("backoffice.dashboard"))


def _get_gsheet_form_data(form: CreateAssemblyGSheetForm | EditAssemblyGSheetForm) -> dict:
    """Extract gsheet configuration data from form."""
    return {
        "url": form.url.data,
        "team": form.team.data,
        "select_registrants_tab": form.select_registrants_tab.data,
        "select_targets_tab": form.select_targets_tab.data,
        "replace_registrants_tab": form.replace_registrants_tab.data,
        "replace_targets_tab": form.replace_targets_tab.data,
        "already_selected_tab": form.already_selected_tab.data,
        "id_column": form.id_column.data,
        "check_same_address": form.check_same_address.data,
        "generate_remaining_tab": form.generate_remaining_tab.data,
        "check_same_address_cols_string": form.check_same_address_cols_string.data,
        "columns_to_keep_string": form.columns_to_keep_string.data,
    }


def _handle_gsheet_save_success(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    user_id: uuid.UUID,
    form: CreateAssemblyGSheetForm | EditAssemblyGSheetForm,
    is_update: bool,
) -> ResponseReturnValue:
    """Handle successful gsheet form validation and save to service layer."""
    form_data = _get_gsheet_form_data(form)

    if is_update:
        update_assembly_gsheet(uow=uow, assembly_id=assembly_id, user_id=user_id, **form_data)
        flash(_("Google Spreadsheet configuration updated successfully"), "success")
    else:
        add_assembly_gsheet(uow=uow, assembly_id=assembly_id, user_id=user_id, **form_data)
        flash(_("Google Spreadsheet configuration created successfully"), "success")

    # Soft validation warning - check if columns_to_keep is empty
    if not form.columns_to_keep_string.data or not form.columns_to_keep_string.data.strip():
        flash(
            _(
                "Warning: No columns to keep specified. "
                "This means the output will only include participant data columns "
                "used for the targets and address checking. Is this intentional?"
            ),
            "warning",
        )

    return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="gsheet"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/gsheet/save", methods=["POST"])
@login_required
def save_gsheet_config(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Save Google Spreadsheet configuration for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        existing_gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)
        is_update = existing_gsheet is not None
        form = EditAssemblyGSheetForm() if is_update else CreateAssemblyGSheetForm()

        if form.validate_on_submit():
            try:
                return _handle_gsheet_save_success(uow, assembly_id, current_user.id, form, is_update)
            except InsufficientPermissions as e:
                current_app.logger.warning(f"Insufficient permissions for gsheet save: {e}")
                flash(_("You don't have permission to manage Google Spreadsheet for this assembly"), "error")
                return redirect(url_for("backoffice.dashboard"))
            except NotFoundError as e:
                current_app.logger.error(f"Gsheet save validation error for assembly {assembly_id}: {e}")
                flash(_("Please check your input and try again"), "error")
            except Exception as e:
                current_app.logger.error(f"Gsheet save error for assembly {assembly_id}: {e}")
                flash(_("An error occurred while saving the Google Spreadsheet configuration"), "error")

        # Form validation failed or service error - re-render the page with errors
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        return render_template(
            "backoffice/assembly_data.html",
            assembly=assembly,
            data_source="gsheet",
            data_source_locked=is_update,  # Locked if updating existing config
            gsheet=existing_gsheet,
            gsheet_mode="edit" if is_update else "new",
            gsheet_form=form,
            google_service_account_email=current_app.config.get("GOOGLE_SERVICE_ACCOUNT_EMAIL", "UNKNOWN"),
        ), 200

    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for gsheet save: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions to save gsheet for assembly {assembly_id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Gsheet save error for assembly {assembly_id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while saving the Google Spreadsheet configuration"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="gsheet"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/gsheet/delete", methods=["POST"])
@login_required
def delete_gsheet_config(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Delete Google Spreadsheet configuration for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        remove_assembly_gsheet(uow, assembly_id, current_user.id)
        flash(_("Google Spreadsheet configuration removed successfully"), "success")
        # Redirect without source param - selector will be unlocked allowing user to choose again
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id))

    except NotFoundError as e:
        current_app.logger.warning(f"Gsheet config not found for delete: {e}")
        flash(_("Google Spreadsheet configuration not found"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions to delete gsheet for assembly {assembly_id}: {e}")
        flash(_("You don't have permission to manage Google Spreadsheet for this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Gsheet delete error for assembly {assembly_id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while removing the Google Spreadsheet configuration"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/members")
@login_required
def view_assembly_members(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly team members page."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

            # Get assembly users with their roles
            assembly_users = uow.user_assembly_roles.get_users_with_roles_for_assembly(assembly_id)

            # Check if current user can manage this assembly
            can_manage_assembly_users = has_global_admin(current_user)

        add_user_form = AddUserToAssemblyForm()

        return render_template(
            "backoffice/assembly_members.html",
            assembly=assembly,
            assembly_users=assembly_users,
            can_manage_assembly_users=can_manage_assembly_users,
            add_user_form=add_user_form,
            current_tab="members",
        ), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View assembly members error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An error occurred while loading team members"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/members/add", methods=["POST"])
@login_required
def add_user_to_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Add a user to an assembly with a specific role."""
    form = AddUserToAssemblyForm()

    try:
        uow = bootstrap.bootstrap()
        with uow:
            # Verify user can manage assembly users
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

                # Get email adapters for sending notification
                email_adapter = get_email_adapter()
                template_renderer = get_template_renderer(current_app)
                url_generator = get_url_generator(current_app)

                # Call service layer to add user to assembly
                grant_user_assembly_role(
                    uow=uow,
                    user_id=user_id,
                    assembly_id=assembly_id,
                    role=role,
                    current_user=current_user,
                    email_adapter=email_adapter,
                    template_renderer=template_renderer,
                    url_generator=url_generator,
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
                flash(_("Please select a user and role"), "error")

        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))

    except NotFoundError as e:
        current_app.logger.error(f"Error adding user to assembly {assembly_id}: {e}")
        flash(_("Could not add user to assembly: %(error)s", error=str(e)), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to add user to assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to add users to this assembly"), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(
            f"Unexpected error adding user to assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("An error occurred while adding the user to the assembly"), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/members/<uuid:user_id>/remove", methods=["POST"])
@login_required
def remove_user_from_assembly(assembly_id: uuid.UUID, user_id: uuid.UUID) -> ResponseReturnValue:
    """Remove a user from an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            # Verify user can manage assembly users
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

        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))

    except NotFoundError as e:
        current_app.logger.error(f"Error removing user from assembly {assembly_id}: {e}")
        flash(_("Could not remove user from assembly: %(error)s", error=str(e)), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to remove user from assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to remove users from this assembly"), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(
            f"Unexpected error removing user from assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("An error occurred while removing the user from the assembly"), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/members/search")
@login_required
def search_users(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Search for users not yet added to the assembly.

    Returns JSON array for use with autocomplete component.
    """
    try:
        search_term = request.args.get("q", "").strip()

        uow = bootstrap.bootstrap()
        with uow:
            # Verify user can manage assembly users
            if not has_global_admin(current_user):
                return jsonify([]), 403

            # Search for matching users not in assembly
            matching_users = uow.users.search_users_not_in_assembly(assembly_id, search_term) if search_term else []

        # Return JSON array with id, label, sublabel format expected by autocomplete
        results = [
            {
                "id": str(user.id),
                "label": user.email,
                "sublabel": user.display_name,
            }
            for user in matching_users
        ]

        return jsonify(results), 200

    except Exception as e:
        current_app.logger.error(f"Error searching users for assembly {assembly_id}: {e}")
        return jsonify([]), 500


@backoffice_bp.route("/showcase/search-demo")
def search_demo() -> ResponseReturnValue:
    """Demo search endpoint for showcase page.

    Returns mock data for demonstrating the search_dropdown component.
    """
    search_term = request.args.get("q", "").strip().lower()

    # Mock data for demonstration
    mock_users = [
        {"id": "1", "label": "alice@example.com", "sublabel": "Alice Johnson"},
        {"id": "2", "label": "bob@example.com", "sublabel": "Bob Smith"},
        {"id": "3", "label": "carol@example.com", "sublabel": "Carol Williams"},
        {"id": "4", "label": "david@example.com", "sublabel": "David Brown"},
        {"id": "5", "label": "eve@example.com", "sublabel": "Eve Davis"},
    ]

    if not search_term:
        return jsonify([]), 200

    # Filter mock data based on search term
    results = [
        user for user in mock_users if search_term in user["label"].lower() or search_term in user["sublabel"].lower()
    ]

    return jsonify(results), 200
