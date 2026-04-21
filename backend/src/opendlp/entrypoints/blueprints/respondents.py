"""ABOUTME: Backoffice routes for CRUD operations on assembly respondents
ABOUTME: Provides respondent viewing, CSV upload, and deletion under /backoffice/assembly/*/respondents"""

import uuid
from datetime import UTC, datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer.assembly_service import (
    CSVUploadStatus,
    delete_respondents_for_assembly,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    update_csv_config,
)
from opendlp.service_layer.exceptions import (
    InsufficientPermissions,
    InvalidSelection,
    NotFoundError,
    RespondentNotFoundError,
)
from opendlp.service_layer.respondent_service import (
    get_respondent,
    get_respondents_for_assembly_paginated,
    import_respondents_from_csv,
)
from opendlp.translations import gettext as _

from .backoffice import _determine_data_source, _get_tab_enabled_states

respondents_bp = Blueprint("respondents", __name__)


@respondents_bp.route("/assembly/<uuid:assembly_id>/data/upload-respondents", methods=["POST"])
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

        # Get optional id_column from form (empty string means use first column)
        id_column = request.form.get("id_column", "").strip() or None

        filename = file.filename or "unknown.csv"

        # Import respondents using service function
        uow = bootstrap.bootstrap()
        with uow:
            respondents, errors, resolved_id_column = import_respondents_from_csv(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                csv_content=csv_content,
                replace_existing=True,
                id_column=id_column,
            )

        # Save CSV config with resolved id column
        uow2 = bootstrap.bootstrap()
        update_csv_config(
            uow=uow2,
            user_id=current_user.id,
            assembly_id=assembly_id,
            last_import_filename=filename,
            last_import_timestamp=datetime.now(UTC),
            csv_id_column=resolved_id_column,
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


@respondents_bp.route("/assembly/<uuid:assembly_id>/data/delete-respondents", methods=["POST"])
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


@respondents_bp.route("/assembly/<uuid:assembly_id>/respondents")
@login_required
def view_assembly_respondents(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly respondents page."""
    try:
        # Get pagination parameters
        page = request.args.get("page", 1, type=int)
        per_page = 25

        # Get status filter - keep raw value for template, parse for service
        status_filter_str = request.args.get("status", "")
        status_filter = RespondentStatus.from_str(status_filter_str)

        # Get assembly with permissions
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

            # If filter string provided but not a valid enum, return empty results
            if status_filter_str and status_filter is None:
                respondents: list[Respondent] = []
                total_count = 0
            else:
                respondents, total_count = get_respondents_for_assembly_paginated(
                    uow,
                    user_id=current_user.id,
                    assembly_id=assembly_id,
                    page=page,
                    per_page=per_page,
                    status=status_filter,
                )

        # Calculate pagination info
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

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
            respondents=respondents,
            data_source=data_source,
            gsheet=gsheet,
            targets_enabled=targets_enabled,
            respondents_enabled=respondents_enabled,
            selection_enabled=selection_enabled,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            total_count=total_count,
            status_filter=status_filter_str,
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


@respondents_bp.route("/assembly/<uuid:assembly_id>/respondents/<uuid:respondent_id>")
@login_required
def view_respondent(assembly_id: uuid.UUID, respondent_id: uuid.UUID) -> ResponseReturnValue:
    """View one respondent"""
    try:
        # Get assembly with permissions
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            respondent = get_respondent(uow, current_user.id, assembly_id, respondent_id)

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
            "backoffice/assembly_view_respondent.html",
            assembly=assembly,
            respondent=respondent,
            data_source=data_source,
            gsheet=gsheet,
            targets_enabled=targets_enabled,
            respondents_enabled=respondents_enabled,
            selection_enabled=selection_enabled,
        ), 200
    except RespondentNotFoundError as e:
        current_app.logger.warning(f"Respondent {respondent_id} not found in assembly {assembly_id}: {e}")
        flash(_("Respondent not found"), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View respondent error for respondent {respondent_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while loading the respondent"), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
