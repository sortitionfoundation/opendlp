"""ABOUTME: Backoffice routes for admin UI using Pines UI + Tailwind CSS
ABOUTME: Provides /backoffice/* routes for dashboard, assembly CRUD, data source, and team members"""

import traceback
import uuid
from collections.abc import Callable
from typing import Any

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap, config
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
    CSVUploadStatus,
    create_assembly,
    delete_respondents_for_assembly,
    delete_targets_for_assembly,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    get_or_create_csv_config,
    import_targets_from_csv,
    update_assembly,
    update_csv_config,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection, NotFoundError
from opendlp.service_layer.permissions import has_global_admin
from opendlp.service_layer.respondent_service import import_respondents_from_csv
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
        data_source, _locked = _determine_data_source(gsheet, csv_status)
        targets_enabled, respondents_enabled, selection_enabled = _get_tab_enabled_states(
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


def _determine_data_source(gsheet: Any, csv_status: CSVUploadStatus | None) -> tuple[str, bool]:
    """Determine data source and whether it's locked based on existing configs."""
    if gsheet:
        return "gsheet", True
    if csv_status and csv_status.has_data:
        return "csv", True
    # No config exists - allow user to choose source from query param
    data_source = request.args.get("source", "")
    if data_source not in ("gsheet", "csv", ""):
        data_source = ""
    return data_source, False


def _get_tab_enabled_states(
    data_source: str, gsheet: Any, csv_status: CSVUploadStatus | None
) -> tuple[bool, bool, bool]:
    """Determine whether targets, respondents, and selection tabs should be enabled."""
    if data_source == "gsheet":
        enabled = gsheet is not None
        return enabled, enabled, enabled
    if data_source == "csv" and csv_status:
        return csv_status.has_targets, csv_status.has_respondents, csv_status.selection_enabled
    return False, False, False


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
        data_source, data_source_locked = _determine_data_source(gsheet, csv_status)

        # Set up gsheet form if gsheet source is selected
        gsheet_mode = "new"
        gsheet_form = None
        if data_source == "gsheet":
            mode_param = request.args.get("mode", "")
            gsheet_mode = ("edit" if mode_param == "edit" else "view") if gsheet else "new"
            gsheet_form = EditAssemblyGSheetForm(obj=gsheet) if gsheet else CreateAssemblyGSheetForm()

        # Determine tab enabled states
        targets_enabled, respondents_enabled, selection_enabled = _get_tab_enabled_states(
            data_source, gsheet, csv_status
        )

        return render_template(
            "backoffice/assembly_data.html",
            assembly=assembly,
            data_source=data_source,
            data_source_locked=data_source_locked,
            gsheet=gsheet,
            gsheet_mode=gsheet_mode,
            gsheet_form=gsheet_form,
            google_service_account_email=google_service_account_email,
            targets_enabled=targets_enabled,
            respondents_enabled=respondents_enabled,
            selection_enabled=selection_enabled,
            csv_status=csv_status,
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


# =============================================================================
# CSV Upload Routes
# =============================================================================


@backoffice_bp.route("/assembly/<uuid:assembly_id>/data/upload-targets", methods=["POST"])
@login_required
def upload_targets_csv(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Upload targets CSV file for an assembly."""
    try:
        # Check if file was uploaded
        if "file" not in request.files:
            flash(_("No file selected"), "error")
            return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

        file = request.files["file"]
        if file.filename == "":
            flash(_("No file selected"), "error")
            return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

        # Read CSV content
        csv_content = file.read().decode("utf-8")

        # Import targets using service function
        uow = bootstrap.bootstrap()
        with uow:
            categories = import_targets_from_csv(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                csv_content=csv_content,
                replace_existing=True,
            )

        flash(
            _("Targets uploaded successfully: %(count)d categories", count=len(categories)),
            "success",
        )
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

    except InvalidSelection as e:
        current_app.logger.warning(f"Invalid CSV format for targets upload assembly {assembly_id}: {e}")
        flash(_("Invalid CSV format: %(error)s", error=str(e)), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to upload targets for assembly {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to upload targets"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for targets upload: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Upload targets error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while uploading targets"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/data/delete-targets", methods=["POST"])
@login_required
def delete_targets(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Delete all targets for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            count = delete_targets_for_assembly(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )

        flash(_("Targets deleted: %(count)d categories removed", count=count), "success")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to delete targets for assembly {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to delete targets"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for targets deletion: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Delete targets error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while deleting targets"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/data/upload-respondents", methods=["POST"])
@login_required
def upload_respondents_csv(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Upload respondents (people) CSV file for an assembly."""
    try:
        # Check if file was uploaded
        if "file" not in request.files:
            flash(_("No file selected"), "error")
            return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

        file = request.files["file"]
        if file.filename == "":
            flash(_("No file selected"), "error")
            return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

        # Read CSV content
        csv_content = file.read().decode("utf-8")

        # Import respondents using service function
        uow = bootstrap.bootstrap()
        with uow:
            respondents, errors, _id_column = import_respondents_from_csv(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                csv_content=csv_content,
                replace_existing=True,
            )

        if errors:
            flash(
                _(
                    "Respondents uploaded with warnings: %(count)d imported, %(errors)d errors",
                    count=len(respondents),
                    errors=len(errors),
                ),
                "warning",
            )
        else:
            flash(
                _("Respondents uploaded successfully: %(count)d imported", count=len(respondents)),
                "success",
            )
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

    except InvalidSelection as e:
        current_app.logger.warning(f"Invalid CSV format for respondents upload assembly {assembly_id}: {e}")
        flash(_("Invalid CSV format: %(error)s", error=str(e)), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to upload respondents for assembly {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to upload respondents"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for respondents upload: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Upload respondents error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while uploading respondents"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/data/delete-respondents", methods=["POST"])
@login_required
def delete_respondents(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Delete all respondents for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            count = delete_respondents_for_assembly(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )

        flash(_("Respondents deleted: %(count)d removed", count=count), "success")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to delete respondents for assembly {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to delete respondents"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for respondents deletion: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Delete respondents error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while deleting respondents"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/targets")
@login_required
def view_assembly_targets(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly targets page."""
    try:
        # Get assembly with permissions
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        # Determine data source and whether tabs should be enabled
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

        # Determine data source
        data_source, _locked = _determine_data_source(gsheet, csv_status)

        # Tab enabled states
        targets_enabled, respondents_enabled, selection_enabled = _get_tab_enabled_states(
            data_source, gsheet, csv_status
        )

        return render_template(
            "backoffice/assembly_targets.html",
            assembly=assembly,
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
        current_app.logger.error(f"View assembly targets error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while loading assembly targets"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/respondents")
@login_required
def view_assembly_respondents(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly respondents page."""
    try:
        # Get assembly with permissions
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        # Determine data source and whether tabs should be enabled
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

        # Determine data source
        data_source, _locked = _determine_data_source(gsheet, csv_status)

        # Tab enabled states
        targets_enabled, respondents_enabled, selection_enabled = _get_tab_enabled_states(
            data_source, gsheet, csv_status
        )

        return render_template(
            "backoffice/assembly_respondents.html",
            assembly=assembly,
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
        current_app.logger.error(
            f"View assembly respondents error for assembly {assembly_id} user {current_user.id}: {e}"
        )
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while loading assembly respondents"), "error")
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
            assembly_users = uow.user_assembly_roles.get_users_with_roles_for_assembly(assembly_id)

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
        data_source, _locked = _determine_data_source(gsheet, csv_status)
        targets_enabled, respondents_enabled, selection_enabled = _get_tab_enabled_states(
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


# =============================================================================
# Developer Tools Dashboard (Admin-only)
# =============================================================================


@backoffice_bp.route("/dev")
@login_required
def dev_dashboard() -> ResponseReturnValue:
    """Developer tools dashboard.

    Admin-only page that links to all developer tools.
    Disabled in production for security.
    """
    if config.is_production():
        abort(404)

    if not has_global_admin(current_user):
        flash(_("You don't have permission to access developer tools"), "error")
        return redirect(url_for("backoffice.dashboard"))

    return render_template("backoffice/dev_dashboard.html"), 200


# =============================================================================
# Service Layer Documentation (Admin-only developer tools)
# =============================================================================


@backoffice_bp.route("/dev/service-docs")
@login_required
def service_docs() -> ResponseReturnValue:
    """Interactive service layer documentation page for CSV upload services.

    Admin-only page that provides interactive testing of service layer functions.
    Disabled in production for security.
    """
    # Disable in production - developer tools should not be available
    if config.is_production():
        abort(404)

    if not has_global_admin(current_user):
        flash(_("You don't have permission to access developer tools"), "error")
        return redirect(url_for("backoffice.dashboard"))

    # Get active tab from query parameter, default to 'respondents'
    active_tab = request.args.get("tab", "respondents")
    valid_tabs = ["respondents", "targets", "config", "selection"]
    if active_tab not in valid_tabs:
        active_tab = "respondents"

    # Get all assemblies for the dropdown (admin can see all via get_user_assemblies)
    uow = bootstrap.bootstrap()
    assemblies = get_user_assemblies(uow, current_user.id)

    return render_template("backoffice/service_docs.html", assemblies=assemblies, active_tab=active_tab), 200


@backoffice_bp.route("/dev/service-docs/execute", methods=["POST"])
@login_required
def service_docs_execute() -> ResponseReturnValue:
    """Execute a service layer function for testing.

    Accepts JSON with service name and parameters, returns JSON result.
    Disabled in production for security.
    """
    # Disable in production - developer tools should not be available
    if config.is_production():
        abort(404)

    if not has_global_admin(current_user):
        return jsonify({"status": "error", "error": "Unauthorized", "error_type": "InsufficientPermissions"}), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "error": "No JSON data provided", "error_type": "ValidationError"}), 400

        service_name = data.get("service")
        params = data.get("params", {})

        result = _execute_service(service_name, params)
        return jsonify(result), 200

    except Exception as e:
        current_app.logger.error(f"Service docs execute error: {e}")
        current_app.logger.exception("Full traceback:")
        return jsonify({
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }), 500


def _handle_import_respondents(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle import_respondents_from_csv service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    csv_content = params["csv_content"]
    replace_existing = params.get("replace_existing", False)
    id_column = params.get("id_column") or None

    with uow:
        try:
            respondents, errors, resolved_id_column = import_respondents_from_csv(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                csv_content=csv_content,
                replace_existing=replace_existing,
                id_column=id_column,
            )
            return {
                "status": "success",
                "imported_count": len(respondents),
                "errors": errors,
                "id_column_used": resolved_id_column,
                "sample_respondents": [
                    {
                        "external_id": r.external_id,
                        "attributes": r.attributes,
                        "email": r.email,
                        "consent": r.consent,
                        "eligible": r.eligible,
                        "can_attend": r.can_attend,
                    }
                    for r in respondents[:5]  # Show first 5 as sample
                ],
            }
        except InvalidSelection as e:
            return {"status": "error", "error": str(e), "error_type": "InvalidSelection"}
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_import_targets(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle import_targets_from_csv service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    csv_content = params["csv_content"]
    replace_existing = params.get("replace_existing", True)

    with uow:
        try:
            categories = import_targets_from_csv(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                csv_content=csv_content,
                replace_existing=replace_existing,
            )
            return {
                "status": "success",
                "categories_count": len(categories),
                "total_values_count": sum(len(c.values) for c in categories),
                "categories": [
                    {
                        "name": c.name,
                        "values": [
                            {
                                "value": v.value,
                                "min": v.min,
                                "max": v.max,
                                "min_flex": v.min_flex,
                                "max_flex": v.max_flex,
                            }
                            for v in c.values
                        ],
                    }
                    for c in categories
                ],
            }
        except InvalidSelection as e:
            return {"status": "error", "error": str(e), "error_type": "InvalidSelection"}
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_get_csv_config(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle get_or_create_csv_config service call."""
    assembly_id = uuid.UUID(params["assembly_id"])

    with uow:
        try:
            csv_config = get_or_create_csv_config(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )
            return {
                "status": "success",
                "config": {
                    "assembly_csv_id": str(csv_config.assembly_csv_id) if csv_config.assembly_csv_id else None,
                    "assembly_id": str(csv_config.assembly_id),
                    "id_column": csv_config.id_column,
                    "check_same_address": csv_config.check_same_address,
                    "check_same_address_cols": csv_config.check_same_address_cols,
                    "columns_to_keep": csv_config.columns_to_keep,
                    "selection_algorithm": csv_config.selection_algorithm,
                    "settings_confirmed": csv_config.settings_confirmed,
                    "last_import_filename": csv_config.last_import_filename,
                    "last_import_timestamp": csv_config.last_import_timestamp.isoformat()
                    if csv_config.last_import_timestamp
                    else None,
                    "created_at": csv_config.created_at.isoformat() if csv_config.created_at else None,
                    "updated_at": csv_config.updated_at.isoformat() if csv_config.updated_at else None,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_update_csv_config(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle update_csv_config service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    settings = {k: v for k, v in params.items() if k not in ("assembly_id",)}

    with uow:
        try:
            csv_config = update_csv_config(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                **settings,
            )
            return {
                "status": "success",
                "config": {
                    "assembly_csv_id": str(csv_config.assembly_csv_id) if csv_config.assembly_csv_id else None,
                    "assembly_id": str(csv_config.assembly_id),
                    "id_column": csv_config.id_column,
                    "check_same_address": csv_config.check_same_address,
                    "check_same_address_cols": csv_config.check_same_address_cols,
                    "columns_to_keep": csv_config.columns_to_keep,
                    "selection_algorithm": csv_config.selection_algorithm,
                    "settings_confirmed": csv_config.settings_confirmed,
                    "updated_at": csv_config.updated_at.isoformat() if csv_config.updated_at else None,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


# Mapping of service names to their handler functions
_SERVICE_HANDLERS: dict[str, Callable[[Any, dict[str, Any]], dict[str, Any]]] = {
    "import_respondents_from_csv": _handle_import_respondents,
    "import_targets_from_csv": _handle_import_targets,
    "get_or_create_csv_config": _handle_get_csv_config,
    "update_csv_config": _handle_update_csv_config,
}


def _execute_service(service_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a service layer function and return the result as JSON-serializable dict."""
    handler = _SERVICE_HANDLERS.get(service_name)
    if handler is None:
        return {"status": "error", "error": f"Unknown service: {service_name}", "error_type": "ValidationError"}

    uow = bootstrap.bootstrap()
    return handler(uow, params)


# =============================================================================
# Frontend Patterns Documentation (Admin-only developer tools)
# =============================================================================


@backoffice_bp.route("/dev/patterns")
@login_required
def patterns() -> ResponseReturnValue:
    """Interactive frontend patterns documentation page.

    Admin-only page that documents Alpine.js patterns, form handling,
    and other frontend patterns used in the backoffice.
    Disabled in production for security.
    """
    if config.is_production():
        abort(404)

    if not has_global_admin(current_user):
        flash(_("You don't have permission to access developer tools"), "error")
        return redirect(url_for("backoffice.dashboard"))

    # Get active tab from query parameter, default to 'dropdown'
    active_tab = request.args.get("tab", "dropdown")
    valid_tabs = ["dropdown", "form", "ajax", "file-upload"]
    if active_tab not in valid_tabs:
        active_tab = "dropdown"

    # Get assemblies for live examples
    uow = bootstrap.bootstrap()
    assemblies = get_user_assemblies(uow, current_user.id)

    return render_template("backoffice/patterns.html", assemblies=assemblies, active_tab=active_tab), 200
