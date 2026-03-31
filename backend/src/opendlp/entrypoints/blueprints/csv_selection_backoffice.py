"""ABOUTME: Backoffice CSV selection routes for running sortition on DB-stored data
ABOUTME: Provides /backoffice/assembly/*/selection/csv/* routes for selection, progress, and downloads"""

import uuid

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.entrypoints.decorators import require_assembly_management
from opendlp.entrypoints.forms import DbSelectionSettingsForm
from opendlp.service_layer.assembly_service import (
    get_assembly_with_permissions,
    get_csv_upload_status,
    get_or_create_csv_config,
    update_csv_config,
    update_selection_settings,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection, NotFoundError
from opendlp.service_layer.report_translation import translate_run_report_to_html
from opendlp.service_layer.sortition import (
    cancel_task,
    check_and_update_task_health,
    check_db_selection_data,
    generate_selection_csvs,
    get_selection_run_status,
    start_db_select_task,
)
from opendlp.translations import gettext as _

csv_selection_backoffice_bp = Blueprint("csv_selection_backoffice", __name__)


@csv_selection_backoffice_bp.route("/assembly/<uuid:assembly_id>/selection/csv/check", methods=["POST"])
@login_required
@require_assembly_management
def check_csv_data(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Validate CSV/database data before running selection."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)

        if not csv_config.settings_confirmed:
            flash(_("Please review and save the selection settings before checking data."), "warning")
            return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

        uow2 = bootstrap.bootstrap()
        with uow2:
            check_result = check_db_selection_data(uow=uow2, user_id=current_user.id, assembly_id=assembly_id)

        if check_result.success:
            flash(
                _(
                    "Data validation passed: %(features)s targets, %(people)s respondents ready for selection.",
                    features=check_result.num_features,
                    people=check_result.num_people,
                ),
                "success",
            )
        else:
            for error in check_result.errors:
                flash(error, "error")

        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))

    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Check CSV data error for assembly {assembly_id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An unexpected error occurred while checking data"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))


@csv_selection_backoffice_bp.route("/assembly/<uuid:assembly_id>/selection/csv/run", methods=["POST"])
@login_required
@require_assembly_management
def start_csv_selection(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a CSV/database selection task."""
    try:
        test_mode = request.args.get("test") == "1"

        uow = bootstrap.bootstrap()
        with uow:
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)

            if not csv_config.settings_confirmed:
                flash(_("Please review and save the selection settings before running selection."), "warning")
                return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

            task_id = start_db_select_task(uow, current_user.id, assembly_id, test_selection=test_mode)

        return redirect(
            url_for(
                "gsheets.view_assembly_selection",
                assembly_id=assembly_id,
                current_selection=task_id,
            )
        )

    except InvalidSelection as e:
        flash(_("Could not start selection task: %(error)s", error=str(e)), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except NotFoundError as e:
        flash(_("Failed to start selection task: %(error)s", error=str(e)), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions:
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error starting CSV selection for assembly {assembly_id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An unexpected error occurred while starting the selection task"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))


@csv_selection_backoffice_bp.route("/assembly/<uuid:assembly_id>/selection/csv/modal-progress/<uuid:run_id>")
@login_required
def csv_selection_progress_modal(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Return modal progress HTML fragment for HTMX polling of CSV selection task status."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_status = get_csv_upload_status(uow, current_user.id, assembly_id)

            # Check task health
            check_and_update_task_health(uow, run_id)

            # Get run status
            result = get_selection_run_status(uow, run_id)

        if result.run_record is None:
            return "", 404

        if result.run_record.assembly_id != assembly_id:
            current_app.logger.warning(
                f"Run {run_id} does not belong to assembly {assembly_id} - user {current_user.id}"
            )
            return "", 404

        return render_template(
            "backoffice/components/csv_selection_progress_modal.html",
            assembly=assembly,
            csv_status=csv_status,
            run_record=result.run_record,
            log_messages=result.log_messages,
            run_report=result.run_report,
            translated_report_html=translate_run_report_to_html(result.run_report) if result.run_report else "",
            current_selection=run_id,
        ), 200
    except NotFoundError:
        return "", 404
    except InsufficientPermissions:
        return "", 403
    except Exception as e:
        current_app.logger.error(f"CSV selection progress modal error: {e}")
        return "", 500


@csv_selection_backoffice_bp.route("/assembly/<uuid:assembly_id>/selection/csv/<uuid:run_id>/cancel", methods=["POST"])
@login_required
@require_assembly_management
def cancel_csv_selection(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Cancel a running CSV selection task."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            cancel_task(uow, current_user.id, assembly_id, run_id)

        flash(_("Task cancelled"), "info")
        return redirect(
            url_for(
                "gsheets.view_assembly_selection",
                assembly_id=assembly_id,
                current_selection=run_id,
            )
        )
    except InvalidSelection as e:
        current_app.logger.warning(f"Cannot cancel task: {e}")
        flash(_("Cannot cancel task: %(error)s", error=str(e)), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except NotFoundError as e:
        current_app.logger.warning(f"Task not found for cancel: {e}")
        flash(_("Task not found"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions to cancel task: {e}")
        flash(_("You don't have permission to cancel this task"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Cancel CSV selection error: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while cancelling the task"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))


@csv_selection_backoffice_bp.route(
    "/assembly/<uuid:assembly_id>/selection/csv/<uuid:run_id>/download/selected", methods=["GET"]
)
@login_required
@require_assembly_management
def download_csv_selected(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Download the selected participants as CSV."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            get_assembly_with_permissions(uow, assembly_id, current_user.id)
            selected_csv, _remaining_csv = generate_selection_csvs(uow, assembly_id, run_id)

        return Response(
            selected_csv,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=selected-{run_id}.csv"},
        )
    except NotFoundError as e:
        flash(str(e), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except InvalidSelection as e:
        flash(str(e), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id, current_selection=run_id))
    except InsufficientPermissions:
        flash(_("You don't have permission to download this data"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Download selected CSV error for assembly {assembly_id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while generating the download"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))


@csv_selection_backoffice_bp.route(
    "/assembly/<uuid:assembly_id>/selection/csv/<uuid:run_id>/download/remaining", methods=["GET"]
)
@login_required
@require_assembly_management
def download_csv_remaining(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Download the remaining participants as CSV."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            get_assembly_with_permissions(uow, assembly_id, current_user.id)
            _selected_csv, remaining_csv = generate_selection_csvs(uow, assembly_id, run_id)

        return Response(
            remaining_csv,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=remaining-{run_id}.csv"},
        )
    except NotFoundError as e:
        flash(str(e), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except InvalidSelection as e:
        flash(str(e), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id, current_selection=run_id))
    except InsufficientPermissions:
        flash(_("You don't have permission to download this data"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Download remaining CSV error for assembly {assembly_id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while generating the download"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))


@csv_selection_backoffice_bp.route("/assembly/<uuid:assembly_id>/data/csv/settings", methods=["POST"])
@login_required
@require_assembly_management
def save_csv_settings(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Save CSV selection settings."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            # Get available columns for form validation
            respondents = uow.respondents.get_by_assembly_id(assembly_id)
            available_columns: list[str] = []
            if respondents and respondents[0].attributes:
                available_columns = sorted(respondents[0].attributes.keys())

        # Create form with request data for validation
        form = DbSelectionSettingsForm(available_columns=available_columns)

        if not form.validate_on_submit():
            # Re-render the page with validation errors
            for field_name, errors in form.errors.items():
                for error in errors:
                    flash(f"{field_name}: {error}", "error")
            return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

        # Parse comma-separated columns
        check_same_address_cols = (
            [c.strip() for c in form.check_same_address_cols_string.data.split(",") if c.strip()]
            if form.check_same_address_cols_string.data
            else []
        )
        columns_to_keep = (
            [c.strip() for c in form.columns_to_keep_string.data.split(",") if c.strip()]
            if form.columns_to_keep_string.data
            else []
        )

        # Update selection settings (check_same_address, columns, etc.)
        uow2 = bootstrap.bootstrap()
        with uow2:
            update_selection_settings(
                uow=uow2,
                user_id=current_user.id,
                assembly_id=assembly_id,
                check_same_address=form.check_same_address.data,
                check_same_address_cols=check_same_address_cols,
                columns_to_keep=columns_to_keep,
            )

        # Mark CSV config as confirmed
        uow3 = bootstrap.bootstrap()
        with uow3:
            update_csv_config(
                uow=uow3,
                user_id=current_user.id,
                assembly_id=assembly_id,
                settings_confirmed=True,
            )

        flash(_("Selection settings saved successfully."), "success")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Save CSV settings error for assembly {assembly_id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while saving settings"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))
