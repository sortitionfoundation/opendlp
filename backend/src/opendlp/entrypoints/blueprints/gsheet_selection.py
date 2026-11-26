"""ABOUTME: Backoffice Google Sheets routes for selection, replacement and tab management tasks
ABOUTME: Provides the /backoffice/project/*/selection/*, replacement/* and manage-tabs/* task routes"""

import uuid

import structlog
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required
from sortition_algorithms.features import maximum_selection, minimum_selection

from opendlp import bootstrap
from opendlp.entrypoints.blueprints.selection import (
    load_features_pending,
    redirect_to_running_task,
)
from opendlp.entrypoints.decorators import require_assembly_management
from opendlp.service_layer.assembly_service import (
    get_assembly_gsheet,
    get_assembly_with_permissions,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, NotFoundError
from opendlp.service_layer.report_translation import translate_run_report_to_html
from opendlp.service_layer.selection_history import name_history
from opendlp.service_layer.sortition import (
    InvalidSelection,
    LoadRunResult,
    TabManagementResult,
    cancel_task,
    check_and_update_task_health,
    get_manage_old_tabs_status,
    get_selection_run_status,
    start_gsheet_load_task,
    start_gsheet_manage_tabs_task,
    start_gsheet_replace_load_task,
    start_gsheet_replace_task,
    start_gsheet_select_task,
)
from opendlp.service_layer.writing_guard import SelectionAlreadyRunning
from opendlp.translations import gettext as _

gsheet_selection_bp = Blueprint("gsheet_selection", __name__)

logger = structlog.get_logger(__name__)


@gsheet_selection_bp.route("/project/<uuid:assembly_id>/selection/modal-progress/<uuid:run_id>")
@login_required
def selection_progress_modal(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Return modal progress HTML fragment for HTMX polling of selection task status."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)

            # Check task health
            check_and_update_task_health(uow, run_id)

            # Get run status
            result = get_selection_run_status(uow, run_id)
            run_names = name_history(uow.selection_run_records.get_history_summaries(assembly_id)).names

        if result.run_record is None:
            return "", 404

        if result.run_record.assembly_id != assembly_id:
            logger.warning(
                "Run does not belong to assembly",
                run_id=str(run_id),
                assembly_id=str(assembly_id),
                user_id=str(current_user.id),
            )
            return "", 404

        return render_template(
            "backoffice/components/selection_progress_modal.html",
            assembly=assembly,
            gsheet=gsheet,
            run_names=run_names,
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
        logger.error("Selection progress modal error", error=str(e))
        return "", 500


@gsheet_selection_bp.route("/project/<uuid:assembly_id>/selection/replacement-modal-progress/<uuid:run_id>")
@login_required
def replacement_progress_modal(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Return replacement modal progress HTML fragment for HTMX polling."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)

            # Check task health
            check_and_update_task_health(uow, run_id)

            # Get run status
            result = get_selection_run_status(uow, run_id)
            run_names = name_history(uow.selection_run_records.get_history_summaries(assembly_id)).names

        if result.run_record is None:
            return "", 404

        if result.run_record.assembly_id != assembly_id:
            logger.warning(
                "Run does not belong to assembly",
                run_id=str(run_id),
                assembly_id=str(assembly_id),
                user_id=str(current_user.id),
            )
            return "", 404

        # Calculate min/max if load task completed successfully
        replacement_min_select: int | None = request.args.get("min_select", type=int)
        replacement_max_select: int | None = request.args.get("max_select", type=int)

        if isinstance(result, LoadRunResult) and result.features is not None and result.success:
            replacement_min_select = minimum_selection(result.features)
            replacement_max_select = maximum_selection(result.features)

        return render_template(
            "backoffice/components/replacement_modal.html",
            assembly=assembly,
            gsheet=gsheet,
            run_names=run_names,
            replacement_run_record=result.run_record,
            replacement_log_messages=result.log_messages,
            replacement_translated_report_html=(
                translate_run_report_to_html(result.run_report) if result.run_report else ""
            ),
            current_replacement=run_id,
            replacement_min_select=replacement_min_select,
            replacement_max_select=replacement_max_select,
            replacement_features_pending=load_features_pending(result.run_record, result),
        ), 200
    except NotFoundError:
        return "", 404
    except InsufficientPermissions:
        return "", 403
    except Exception as e:
        logger.error("Replacement progress modal error", error=str(e))
        return "", 500


@gsheet_selection_bp.route("/project/<uuid:assembly_id>/selection/load", methods=["POST"])
@login_required
@require_assembly_management
def start_selection_load(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a load/validation task for selection data."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            task_id = start_gsheet_load_task(uow, current_user.id, assembly_id)

        return redirect(
            url_for(
                "selection.view_assembly_selection",
                assembly_id=assembly_id,
                current_selection=task_id,
            )
        )
    except NotFoundError as e:
        logger.warning("Assembly or gsheet not found for load task", error=str(e))
        flash(_("Please configure Google Sheets first"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        logger.warning("Insufficient permissions for load task", error=str(e))
        flash(_("You don't have permission to run selection"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except Exception as e:
        logger.exception("Start selection load error", error=str(e))
        flash(_("An error occurred while starting the validation task"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))


@gsheet_selection_bp.route("/project/<uuid:assembly_id>/selection/run", methods=["POST"])
@login_required
@require_assembly_management
def start_selection_run(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a selection task."""
    try:
        # Check if test mode
        test_mode = request.args.get("test") == "1"

        uow = bootstrap.get_flask_uow()
        with uow:
            task_id = start_gsheet_select_task(uow, current_user.id, assembly_id, test_selection=test_mode)

        return redirect(
            url_for(
                "selection.view_assembly_selection",
                assembly_id=assembly_id,
                current_selection=task_id,
            )
        )
    except SelectionAlreadyRunning as e:
        return redirect_to_running_task(assembly_id, e)
    except NotFoundError as e:
        logger.warning("Assembly or gsheet not found for selection task", error=str(e))
        flash(_("Please configure Google Sheets first"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        logger.warning("Insufficient permissions for selection task", error=str(e))
        flash(_("You don't have permission to run selection"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except Exception as e:
        logger.exception("Start selection run error", error=str(e))
        flash(_("An error occurred while starting the selection task"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))


@gsheet_selection_bp.route("/project/<uuid:assembly_id>/selection/<uuid:run_id>/cancel", methods=["POST"])
@login_required
@require_assembly_management
def cancel_selection_run(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Cancel a running selection task."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            cancel_task(uow, current_user.id, assembly_id, run_id)

        flash(_("Task cancelled"), "info")
        return redirect(
            url_for(
                "selection.view_assembly_selection",
                assembly_id=assembly_id,
                current_selection=run_id,
            )
        )
    except InvalidSelection as e:
        logger.warning("Cannot cancel task", error=str(e))
        flash(_("Cannot cancel task: %(error)s", error=str(e)), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except NotFoundError as e:
        logger.warning("Task not found for cancel", error=str(e))
        flash(_("Task not found"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        logger.warning("Insufficient permissions to cancel task", error=str(e))
        flash(_("You don't have permission to cancel this task"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except Exception as e:
        logger.exception("Cancel selection run error", error=str(e))
        flash(_("An error occurred while cancelling the task"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))


# --- Manage tabs views ---


@gsheet_selection_bp.route("/project/<uuid:assembly_id>/manage-tabs/start-list", methods=["POST"])
@login_required
@require_assembly_management
def start_manage_tabs_list(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start listing old tabs task."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            task_id = start_gsheet_manage_tabs_task(uow, current_user.id, assembly_id, dry_run=True)

        return redirect(
            url_for("selection.view_assembly_selection", assembly_id=assembly_id, current_manage_tabs=task_id)
        )
    except NotFoundError as e:
        logger.warning("Assembly or gsheet not found for manage tabs list", error=str(e))
        flash(_("Please configure Google Sheets first"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        logger.warning("Insufficient permissions for manage tabs list", error=str(e))
        flash(_("You don't have permission to manage tabs"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except Exception as e:
        logger.exception("Start manage tabs list error", error=str(e))
        flash(_("An error occurred while starting the list tabs task"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))


@gsheet_selection_bp.route("/project/<uuid:assembly_id>/manage-tabs/start-delete", methods=["POST"])
@login_required
@require_assembly_management
def start_manage_tabs_delete(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start deleting old tabs task."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            task_id = start_gsheet_manage_tabs_task(uow, current_user.id, assembly_id, dry_run=False)

        return redirect(
            url_for("selection.view_assembly_selection", assembly_id=assembly_id, current_manage_tabs=task_id)
        )
    except SelectionAlreadyRunning as e:
        return redirect_to_running_task(assembly_id, e)
    except NotFoundError as e:
        logger.warning("Assembly or gsheet not found for manage tabs delete", error=str(e))
        flash(_("Please configure Google Sheets first"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        logger.warning("Insufficient permissions for manage tabs delete", error=str(e))
        flash(_("You don't have permission to manage tabs"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except Exception as e:
        logger.exception("Start manage tabs delete error", error=str(e))
        flash(_("An error occurred while starting the delete tabs task"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))


@gsheet_selection_bp.route("/project/<uuid:assembly_id>/manage-tabs/<uuid:run_id>/progress")
@login_required
@require_assembly_management
def manage_tabs_progress(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """HTMX endpoint for manage tabs progress modal."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)

            # Check task health
            check_and_update_task_health(uow, run_id)

            # Get run status
            result = get_selection_run_status(uow, run_id)

        if result.run_record is None:
            return "", 404

        if result.run_record.assembly_id != assembly_id:
            logger.warning(
                "Run does not belong to assembly",
                run_id=str(run_id),
                assembly_id=str(assembly_id),
                user_id=str(current_user.id),
            )
            return "", 404

        # Get tab names from TabManagementResult if available
        tab_names: list[str] = []
        if isinstance(result, TabManagementResult):
            tab_names = result.tab_names

        return render_template(
            "backoffice/components/manage_tabs_progress_modal.html",
            assembly=assembly,
            gsheet=gsheet,
            manage_tabs_run_record=result.run_record,
            manage_tabs_tab_names=tab_names,
            manage_tabs_status=get_manage_old_tabs_status(result),
            current_manage_tabs=run_id,
        ), 200
    except NotFoundError:
        return "", 404
    except InsufficientPermissions:
        return "", 403
    except Exception as e:
        logger.error("Manage tabs progress modal error", error=str(e))
        return "", 500


@gsheet_selection_bp.route("/project/<uuid:assembly_id>/manage-tabs/<uuid:run_id>/cancel", methods=["POST"])
@login_required
@require_assembly_management
def cancel_manage_tabs(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Cancel a running manage tabs task."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            cancel_task(uow, current_user.id, assembly_id, run_id)

        flash(_("Task cancelled"), "info")
        return redirect(
            url_for(
                "selection.view_assembly_selection",
                assembly_id=assembly_id,
                current_manage_tabs=run_id,
            )
        )
    except InvalidSelection as e:
        logger.warning("Cannot cancel manage tabs task", error=str(e))
        flash(_("Cannot cancel task: %(error)s", error=str(e)), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except NotFoundError as e:
        logger.warning("Manage tabs task not found for cancel", error=str(e))
        flash(_("Task not found"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        logger.warning("Insufficient permissions to cancel manage tabs task", error=str(e))
        flash(_("You don't have permission to cancel this task"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))
    except Exception as e:
        logger.exception("Cancel manage tabs error", error=str(e))
        flash(_("An error occurred while cancelling the task"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))


# --- Replacement views ---


@gsheet_selection_bp.route("/project/<uuid:assembly_id>/replacement/load", methods=["POST"])
@login_required
@require_assembly_management
def start_replacement_load(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a replacement data validation task."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            task_id = start_gsheet_replace_load_task(uow, current_user.id, assembly_id)

        return redirect(
            url_for("selection.view_assembly_replacement_with_run", assembly_id=assembly_id, run_id=task_id)
        )

    except InvalidSelection as e:
        logger.warning("Invalid selection attempted with replacement load", assembly_id=str(assembly_id), error=str(e))
        flash(_("Could not start task to read the spreadsheet: %(error)s", error=str(e)), "error")
        return redirect(url_for("selection.view_assembly_replacement", assembly_id=assembly_id))

    except NotFoundError as e:
        logger.warning("Failed to start replacement load for assembly", assembly_id=str(assembly_id), error=str(e))
        flash(_("Failed to start loading task: %(error)s", error=str(e)), "error")
        return redirect(url_for("selection.view_assembly_replacement", assembly_id=assembly_id))

    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions for starting replacement load",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to manage this project"), "error")
        return redirect(url_for("backoffice.dashboard"))

    except Exception as e:
        logger.error("Error starting replacement load for assembly", assembly_id=str(assembly_id), error=str(e))
        flash(_("An unexpected error occurred while starting the loading task"), "error")
        return redirect(url_for("selection.view_assembly_replacement", assembly_id=assembly_id))


@gsheet_selection_bp.route("/project/<uuid:assembly_id>/replacement/run", methods=["POST"])
@login_required
@require_assembly_management
def start_replacement_run(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a replacement selection task."""
    try:
        min_select = request.args.get("min_select", type=int) or 0
        max_select = request.args.get("max_select", type=int) or 0

        # Get and validate number_to_select from form
        number_to_select_str = request.form.get("number_to_select")
        if not number_to_select_str:
            flash(_("Number of people to select is required"), "error")
            return redirect(url_for("selection.view_assembly_replacement", assembly_id=assembly_id))

        try:
            number_to_select = int(number_to_select_str)
            if number_to_select <= 0:
                flash(_("Number of people to select must be greater than zero"), "error")
                return redirect(url_for("selection.view_assembly_replacement", assembly_id=assembly_id))
        except ValueError:
            flash(_("Number of people to select must be a valid integer"), "error")
            return redirect(url_for("selection.view_assembly_replacement", assembly_id=assembly_id))

        uow = bootstrap.get_flask_uow()
        with uow:
            task_id = start_gsheet_replace_task(uow, current_user.id, assembly_id, number_to_select)

        return redirect(
            url_for(
                "selection.view_assembly_replacement_with_run",
                assembly_id=assembly_id,
                run_id=task_id,
                num_to_select=number_to_select,
                min_select=min_select,
                max_select=max_select,
            )
        )

    except SelectionAlreadyRunning as e:
        return redirect_to_running_task(assembly_id, e)

    except NotFoundError as e:
        logger.warning("Failed to start replacement for assembly", assembly_id=str(assembly_id), error=str(e))
        flash(_("Failed to start replacement task: %(error)s", error=str(e)), "error")
        return redirect(url_for("selection.view_assembly_replacement", assembly_id=assembly_id))

    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions for starting replacement",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to manage this project"), "error")
        return redirect(url_for("backoffice.dashboard"))

    except Exception as e:
        logger.error("Error starting replacement for assembly", assembly_id=str(assembly_id), error=str(e))
        flash(_("An unexpected error occurred while starting the replacement task"), "error")
        return redirect(url_for("selection.view_assembly_replacement", assembly_id=assembly_id))


@gsheet_selection_bp.route("/project/<uuid:assembly_id>/replacement/<uuid:run_id>/cancel", methods=["POST"])
@login_required
@require_assembly_management
def cancel_replacement_run(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Cancel a running replacement task."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            cancel_task(uow, current_user.id, assembly_id, run_id)

        flash(_("Task has been cancelled"), "success")
        return redirect(url_for("selection.view_assembly_replacement_with_run", assembly_id=assembly_id, run_id=run_id))

    except NotFoundError as e:
        logger.warning(
            "Task not found for cancellation", run_id=str(run_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("Task not found"), "error")
        return redirect(url_for("selection.view_assembly_replacement", assembly_id=assembly_id))

    except InvalidSelection as e:
        logger.warning("Cannot cancel task", run_id=str(run_id), error=str(e))
        flash(str(e), "error")
        return redirect(url_for("selection.view_assembly_replacement_with_run", assembly_id=assembly_id, run_id=run_id))

    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions to cancel task",
            run_id=str(run_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to cancel this task"), "error")
        return redirect(url_for("backoffice.dashboard"))

    except Exception as e:
        logger.error("Error cancelling task", run_id=str(run_id), error=str(e))
        flash(_("An error occurred while cancelling the task"), "error")
        return redirect(url_for("selection.view_assembly_replacement_with_run", assembly_id=assembly_id, run_id=run_id))
