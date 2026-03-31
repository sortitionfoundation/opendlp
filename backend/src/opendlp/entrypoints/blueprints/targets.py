"""ABOUTME: Backoffice routes for CRUD operations on assembly targets
ABOUTME: Provides target viewing, CSV upload, and deletion under /backoffice/assembly/*/targets"""

import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.service_layer.assembly_service import (
    CSVUploadStatus,
    delete_targets_for_assembly,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    import_targets_from_csv,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection, NotFoundError
from opendlp.translations import gettext as _

from .backoffice import _determine_data_source, _get_tab_enabled_states

targets_bp = Blueprint("targets", __name__)


@targets_bp.route("/assembly/<uuid:assembly_id>/targets")
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


@targets_bp.route("/assembly/<uuid:assembly_id>/data/upload-targets", methods=["POST"])
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


@targets_bp.route("/assembly/<uuid:assembly_id>/data/delete-targets", methods=["POST"])
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
