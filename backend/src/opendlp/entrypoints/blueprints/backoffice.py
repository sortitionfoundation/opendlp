"""ABOUTME: Backoffice routes for admin UI using Pines UI + Tailwind CSS
ABOUTME: Provides /backoffice/* routes for dashboard, assembly CRUD, data source, and team members"""

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
    DbSelectionSettingsForm,
    EditAssemblyForm,
    EditAssemblyGSheetForm,
)
from opendlp.service_layer.assembly_service import (
    CSVUploadStatus,
    create_assembly,
    determine_data_source,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    get_or_create_csv_config,
    get_or_create_selection_settings,
    get_tab_enabled_states,
    update_assembly,
)
from opendlp.service_layer.exceptions import (
    InsufficientPermissions,
    NotFoundError,
)
from opendlp.service_layer.permissions import has_global_admin
from opendlp.service_layer.respondent_service import get_respondent_attribute_columns
from opendlp.service_layer.user_service import (
    get_assembly_members,
    get_user_assemblies,
    grant_user_assembly_role,
    revoke_user_assembly_role,
    search_assembly_candidate_users,
)
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

        # Get gsheet config for tab state
        gsheet = None
        try:
            uow_gsheet = bootstrap.bootstrap()
            gsheet = get_assembly_gsheet(uow_gsheet, assembly_id, current_user.id)
        except Exception:  # noqa: S110
            pass  # No gsheet config exists - this is expected for new assemblies

        # Get CSV status
        csv_status: CSVUploadStatus | None = None
        try:
            uow_csv = bootstrap.bootstrap()
            csv_status = get_csv_upload_status(uow_csv, current_user.id, assembly_id)
        except Exception:  # noqa: S110
            pass  # No CSV data - expected for new assemblies

        # Determine data source and tab enabled states
        data_source, _locked = determine_data_source(gsheet, csv_status, request.args.get("source", ""))
        targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(
            data_source, gsheet, csv_status
        )

        return render_template(
            "backoffice/assembly_details.html",
            assembly=assembly,
            data_source=data_source,
            gsheet=gsheet,
            targets_enabled=targets_enabled,
            respondents_enabled=respondents_enabled,
            selection_enabled=selection_enabled,
        ), 200
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


@backoffice_bp.route("/assembly/<uuid:assembly_id>/update-number-to-select", methods=["POST"])
@login_required
def update_number_to_select(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Update just the number_to_select field for an assembly."""
    try:
        number_to_select = request.form.get("number_to_select", type=int)
        if number_to_select is None or number_to_select < 1:
            flash(_("Please enter a valid positive number"), "error")
            return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id, edit_number=1))

        uow = bootstrap.bootstrap()
        with uow:
            updated_assembly = update_assembly(
                uow=uow,
                assembly_id=assembly_id,
                user_id=current_user.id,
                number_to_select=number_to_select,
            )

        flash(_("Number to select updated to %(number)s", number=updated_assembly.number_to_select), "success")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to update number_to_select for assembly {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to edit this assembly"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for update by user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/data")
@login_required
def view_assembly_data(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly data page."""
    try:
        google_service_account_email = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_EMAIL", "UNKNOWN")

        # Get assembly with permissions
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        # Get gsheet config if exists
        gsheet = None
        try:
            uow_gsheet = bootstrap.bootstrap()
            gsheet = get_assembly_gsheet(uow_gsheet, assembly_id, current_user.id)
        except Exception as gsheet_error:
            current_app.logger.error(f"Error loading gsheet config: {gsheet_error}")

        # Get CSV upload status
        try:
            uow_csv = bootstrap.bootstrap()
            csv_status = get_csv_upload_status(uow_csv, current_user.id, assembly_id)
        except Exception as csv_error:
            current_app.logger.error(f"Error loading CSV status: {csv_error}")
            csv_status = CSVUploadStatus(targets_count=0, respondents_count=0, csv_config=None)

        # Determine data source and locking
        data_source, data_source_locked = determine_data_source(gsheet, csv_status, request.args.get("source", ""))

        # Get selection settings for gsheet display and form population
        sel_settings = None
        try:
            uow_sel = bootstrap.bootstrap()
            sel_settings = get_or_create_selection_settings(uow_sel, current_user.id, assembly_id)
        except Exception as sel_error:
            current_app.logger.error(f"Error loading selection settings: {sel_error}")

        # Set up gsheet form if gsheet source is selected
        gsheet_mode = "new"
        gsheet_form = None
        if data_source == "gsheet":
            mode_param = request.args.get("mode", "")
            gsheet_mode = ("edit" if mode_param == "edit" else "view") if gsheet else "new"
            if gsheet:
                gsheet_form = EditAssemblyGSheetForm(
                    obj=gsheet,
                    id_column=sel_settings.id_column if sel_settings else "",
                    check_same_address=sel_settings.check_same_address if sel_settings else True,
                    check_same_address_cols_string=sel_settings.check_same_address_cols_string if sel_settings else "",
                    columns_to_keep_string=sel_settings.columns_to_keep_string if sel_settings else "",
                )
            else:
                gsheet_form = CreateAssemblyGSheetForm()

        # Set up CSV settings form if CSV source is selected
        csv_settings_form = None
        csv_available_columns: list[str] = []
        csv_mode = "view"  # Default to view mode
        csv_config = None
        if data_source == "csv":
            # Determine mode (view or edit)
            mode_param = request.args.get("mode", "")
            csv_mode = "edit" if mode_param == "edit" else "view"

            # Get or create CSV config
            uow_csv_config = bootstrap.bootstrap()
            with uow_csv_config:
                csv_config = get_or_create_csv_config(uow_csv_config, current_user.id, assembly_id)

                # Get available columns from respondents for validation hints
                csv_available_columns = get_respondent_attribute_columns(uow_csv_config, assembly_id)

            # Create form with current values from SelectionSettings
            csv_settings_form = DbSelectionSettingsForm(
                data={
                    "check_same_address": sel_settings.check_same_address if sel_settings else True,
                    "check_same_address_cols_string": sel_settings.check_same_address_cols_string
                    if sel_settings
                    else "",
                    "columns_to_keep_string": sel_settings.columns_to_keep_string if sel_settings else "",
                },
                available_columns=csv_available_columns,
            )

        # Determine tab enabled states
        targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(
            data_source, gsheet, csv_status
        )

        return render_template(
            "backoffice/assembly_data.html",
            assembly=assembly,
            data_source=data_source,
            data_source_locked=data_source_locked,
            gsheet=gsheet,
            selection_settings=sel_settings,
            gsheet_mode=gsheet_mode,
            gsheet_form=gsheet_form,
            google_service_account_email=google_service_account_email,
            targets_enabled=targets_enabled,
            respondents_enabled=respondents_enabled,
            selection_enabled=selection_enabled,
            csv_status=csv_status,
            csv_settings_form=csv_settings_form,
            csv_available_columns=csv_available_columns,
            csv_mode=csv_mode,
            csv_config=csv_config,
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


@backoffice_bp.route("/assembly/<uuid:assembly_id>/members")
@login_required
def view_assembly_members(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly team members page."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

            # Get assembly users with their roles
            assembly_users = get_assembly_members(uow, assembly_id, current_user)

            # Check if current user can manage this assembly
            can_manage_assembly_users = has_global_admin(current_user)

        # Get gsheet config for tab state
        gsheet = None
        try:
            uow_gsheet = bootstrap.bootstrap()
            gsheet = get_assembly_gsheet(uow_gsheet, assembly_id, current_user.id)
        except Exception:  # noqa: S110
            pass  # No gsheet config exists - this is expected for new assemblies

        # Get CSV status
        csv_status: CSVUploadStatus | None = None
        try:
            uow_csv = bootstrap.bootstrap()
            csv_status = get_csv_upload_status(uow_csv, current_user.id, assembly_id)
        except Exception:  # noqa: S110
            pass  # No CSV data - expected for new assemblies

        # Determine data source and tab enabled states
        data_source, _locked = determine_data_source(gsheet, csv_status, request.args.get("source", ""))
        targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(
            data_source, gsheet, csv_status
        )

        add_user_form = AddUserToAssemblyForm()

        return render_template(
            "backoffice/assembly_members.html",
            assembly=assembly,
            assembly_users=assembly_users,
            can_manage_assembly_users=can_manage_assembly_users,
            add_user_form=add_user_form,
            current_tab="members",
            data_source=data_source,
            gsheet=gsheet,
            targets_enabled=targets_enabled,
            respondents_enabled=respondents_enabled,
            selection_enabled=selection_enabled,
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
                _assembly_role, target_user = grant_user_assembly_role(
                    uow=uow,
                    user_id=user_id,
                    assembly_id=assembly_id,
                    role=role,
                    current_user=current_user,
                    email_adapter=email_adapter,
                    template_renderer=template_renderer,
                    url_generator=url_generator,
                )

                flash(
                    _(
                        "%(user)s added to assembly with role %(role)s",
                        user=target_user.display_name,
                        role=role.value,
                    ),
                    "success",
                )
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
            # Call service layer to remove user from assembly
            _assembly_role, target_user = revoke_user_assembly_role(
                uow=uow,
                user_id=user_id,
                assembly_id=assembly_id,
                current_user=current_user,
            )

            flash(
                _("%(user)s removed from assembly", user=target_user.display_name),
                "success",
            )

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
        matching_users = search_assembly_candidate_users(uow, assembly_id, search_term, current_user)

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

    except InsufficientPermissions:
        return jsonify([]), 403
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
