"""ABOUTME: Backoffice Google Sheets routes for configuration, selection, replacement, and tab management
ABOUTME: Provides /backoffice/assembly/*/gsheet/*, selection/*, replacement/*, and manage-tabs/* routes"""

import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required
from sortition_algorithms.features import maximum_selection, minimum_selection

from opendlp import bootstrap
from opendlp.entrypoints.decorators import require_assembly_management
from opendlp.entrypoints.forms import (
    CreateAssemblyGSheetForm,
    EditAssemblyGSheetForm,
)
from opendlp.service_layer.assembly_service import (
    add_assembly_gsheet,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    remove_assembly_gsheet,
    update_assembly_gsheet,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, NotFoundError
from opendlp.service_layer.report_translation import translate_run_report_to_html
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
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import gettext as _

gsheets_bp = Blueprint("gsheets", __name__)


def _get_manage_tabs_context(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, manage_tabs_param: str | None
) -> tuple[uuid.UUID | None, object, list[str], object]:
    """Extract manage tabs modal context from query parameter.

    Returns tuple of (current_manage_tabs, manage_tabs_run_record, manage_tabs_tab_names, manage_tabs_status).
    """
    if not manage_tabs_param:
        return None, None, [], None

    try:
        current_manage_tabs = uuid.UUID(manage_tabs_param)
        check_and_update_task_health(uow, current_manage_tabs)
        result = get_selection_run_status(uow, current_manage_tabs)
        if result.run_record and result.run_record.assembly_id == assembly_id:
            tab_names = result.tab_names if isinstance(result, TabManagementResult) else []
            return current_manage_tabs, result.run_record, tab_names, get_manage_old_tabs_status(result)
    except (ValueError, TypeError):
        # Invalid or malformed manage_tabs_param - ignore and return defaults
        pass
    return None, None, [], None


def _get_selection_modal_context(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, selection_param: str | None
) -> tuple[uuid.UUID | None, object | None, list, str]:
    """Get context for displaying the initial selection progress modal.

    Returns (current_selection, run_record, log_messages, translated_report_html).
    """
    if not selection_param:
        return None, None, [], ""

    try:
        current_selection = uuid.UUID(selection_param)
        check_and_update_task_health(uow, current_selection)
        result = get_selection_run_status(uow, current_selection)

        if result.run_record and result.run_record.assembly_id == assembly_id:
            return (
                current_selection,
                result.run_record,
                result.log_messages,
                translate_run_report_to_html(result.run_report) if result.run_report else "",
            )
    except (ValueError, TypeError):
        current_app.logger.debug("Invalid selection_param for _get_selection_modal_context: %r", selection_param)

    return None, None, [], ""


def _get_replacement_modal_context(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    replacement_param: str | None,
    initial_min_select: int | None,
    initial_max_select: int | None,
) -> tuple[uuid.UUID | None, object | None, list, str, int | None, int | None]:
    """Get context for displaying the replacement selection modal.

    Returns (current_replacement, run_record, log_messages, translated_report_html, min_select, max_select).
    """
    if not replacement_param:
        return None, None, [], "", initial_min_select, initial_max_select

    try:
        current_replacement = uuid.UUID(replacement_param)
        check_and_update_task_health(uow, current_replacement)
        result = get_selection_run_status(uow, current_replacement)

        if result.run_record and result.run_record.assembly_id == assembly_id:
            min_select = initial_min_select
            max_select = initial_max_select

            if isinstance(result, LoadRunResult) and result.features is not None and result.success:
                min_select = minimum_selection(result.features)
                max_select = maximum_selection(result.features)

            return (
                current_replacement,
                result.run_record,
                result.log_messages,
                translate_run_report_to_html(result.run_report) if result.run_report else "",
                min_select,
                max_select,
            )
    except (ValueError, TypeError):
        current_app.logger.debug("Invalid replacement_param for _get_replacement_modal_context: %r", replacement_param)

    return None, None, [], "", initial_min_select, initial_max_select


# --- Selection views ---


@gsheets_bp.route("/assembly/<uuid:assembly_id>/selection")
@login_required
def view_assembly_selection(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly selection page."""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = 15

        current_selection: uuid.UUID | None = None
        run_record = None
        log_messages: list = []
        translated_report_html = ""

        # Manage tabs variables (extracted to helper for complexity)
        current_manage_tabs_param = request.args.get("current_manage_tabs")

        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

            # Get selection modal context
            current_selection, run_record, log_messages, translated_report_html = _get_selection_modal_context(
                uow, assembly_id, request.args.get("current_selection")
            )

            # Get replacement modal context
            (
                current_replacement,
                replacement_run_record,
                replacement_log_messages,
                replacement_translated_report_html,
                replacement_min_select,
                replacement_max_select,
            ) = _get_replacement_modal_context(
                uow,
                assembly_id,
                request.args.get("current_replacement"),
                request.args.get("min_select", type=int),
                request.args.get("max_select", type=int),
            )

            # Handle current_manage_tabs parameter for showing manage tabs modal
            current_manage_tabs, manage_tabs_run_record, manage_tabs_tab_names, manage_tabs_status = (
                _get_manage_tabs_context(uow, assembly_id, current_manage_tabs_param)
            )

        # Check if gsheet is configured
        gsheet = None
        try:
            uow_gsheet = bootstrap.bootstrap()
            gsheet = get_assembly_gsheet(uow_gsheet, assembly_id, current_user.id)
        except Exception as gsheet_error:
            current_app.logger.error(f"Error loading gsheet config for selection: {gsheet_error}")

        # Fetch paginated selection history
        run_history: list = []
        total_count = 0
        total_pages = 0
        try:
            uow_history = bootstrap.bootstrap()
            with uow_history:
                run_history, total_count = uow_history.selection_run_records.get_by_assembly_id_paginated(
                    assembly_id, page, per_page
                )
                total_pages = (total_count + per_page - 1) // per_page
        except Exception as history_error:
            current_app.logger.error(f"Error loading selection history for assembly {assembly_id}: {history_error}")

        replacement_modal_open = request.args.get("replacement_modal") == "open" or current_replacement is not None
        edit_number_modal_open = request.args.get("edit_number") == "1"

        # Determine data source and tab enabled states
        data_source = "gsheet" if gsheet else ""
        targets_enabled = gsheet is not None
        respondents_enabled = gsheet is not None

        return render_template(
            "backoffice/assembly_selection.html",
            assembly=assembly,
            gsheet=gsheet,
            run_history=run_history,
            page=page,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            current_selection=current_selection,
            run_record=run_record,
            log_messages=log_messages,
            translated_report_html=translated_report_html,
            current_manage_tabs=current_manage_tabs,
            manage_tabs_run_record=manage_tabs_run_record,
            manage_tabs_tab_names=manage_tabs_tab_names,
            manage_tabs_status=manage_tabs_status,
            replacement_modal_open=replacement_modal_open,
            current_replacement=current_replacement,
            replacement_run_record=replacement_run_record,
            replacement_log_messages=replacement_log_messages,
            replacement_translated_report_html=replacement_translated_report_html,
            replacement_min_select=replacement_min_select,
            replacement_max_select=replacement_max_select,
            edit_number_modal_open=edit_number_modal_open,
            data_source=data_source,
            targets_enabled=targets_enabled,
            respondents_enabled=respondents_enabled,
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


@gsheets_bp.route("/assembly/<uuid:assembly_id>/selection/<uuid:run_id>")
@login_required
def view_assembly_selection_with_run(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Legacy route - redirects to query parameter version for backwards compatibility."""
    return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id, current_selection=run_id))


@gsheets_bp.route("/assembly/<uuid:assembly_id>/selection/modal-progress/<uuid:run_id>")
@login_required
def selection_progress_modal(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Return modal progress HTML fragment for HTMX polling of selection task status."""
    try:
        uow = bootstrap.bootstrap()
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
            current_app.logger.warning(
                f"Run {run_id} does not belong to assembly {assembly_id} - user {current_user.id}"
            )
            return "", 404

        return render_template(
            "backoffice/components/selection_progress_modal.html",
            assembly=assembly,
            gsheet=gsheet,
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
        current_app.logger.error(f"Selection progress modal error: {e}")
        return "", 500


@gsheets_bp.route("/assembly/<uuid:assembly_id>/selection/replacement-modal-progress/<uuid:run_id>")
@login_required
def replacement_progress_modal(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Return replacement modal progress HTML fragment for HTMX polling."""
    try:
        uow = bootstrap.bootstrap()
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
            current_app.logger.warning(
                f"Run {run_id} does not belong to assembly {assembly_id} - user {current_user.id}"
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
            replacement_run_record=result.run_record,
            replacement_log_messages=result.log_messages,
            replacement_translated_report_html=(
                translate_run_report_to_html(result.run_report) if result.run_report else ""
            ),
            current_replacement=run_id,
            replacement_min_select=replacement_min_select,
            replacement_max_select=replacement_max_select,
        ), 200
    except NotFoundError:
        return "", 404
    except InsufficientPermissions:
        return "", 403
    except Exception as e:
        current_app.logger.error(f"Replacement progress modal error: {e}")
        return "", 500


@gsheets_bp.route("/assembly/<uuid:assembly_id>/selection/load", methods=["POST"])
@login_required
@require_assembly_management
def start_selection_load(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a load/validation task for selection data."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            task_id = start_gsheet_load_task(uow, current_user.id, assembly_id)

        return redirect(
            url_for(
                "gsheets.view_assembly_selection",
                assembly_id=assembly_id,
                current_selection=task_id,
            )
        )
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly or gsheet not found for load task: {e}")
        flash(_("Please configure a Google Spreadsheet first"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for load task: {e}")
        flash(_("You don't have permission to run selection"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Start selection load error: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while starting the validation task"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))


@gsheets_bp.route("/assembly/<uuid:assembly_id>/selection/run", methods=["POST"])
@login_required
@require_assembly_management
def start_selection_run(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a selection task."""
    try:
        # Check if test mode
        test_mode = request.args.get("test") == "1"

        uow = bootstrap.bootstrap()
        with uow:
            task_id = start_gsheet_select_task(uow, current_user.id, assembly_id, test_selection=test_mode)

        return redirect(
            url_for(
                "gsheets.view_assembly_selection",
                assembly_id=assembly_id,
                current_selection=task_id,
            )
        )
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly or gsheet not found for selection task: {e}")
        flash(_("Please configure a Google Spreadsheet first"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for selection task: {e}")
        flash(_("You don't have permission to run selection"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Start selection run error: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while starting the selection task"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))


@gsheets_bp.route("/assembly/<uuid:assembly_id>/selection/<uuid:run_id>/cancel", methods=["POST"])
@login_required
@require_assembly_management
def cancel_selection_run(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Cancel a running selection task."""
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
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Cancel selection run error: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while cancelling the task"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))


# --- Manage tabs views ---


@gsheets_bp.route("/assembly/<uuid:assembly_id>/manage-tabs/start-list", methods=["POST"])
@login_required
@require_assembly_management
def start_manage_tabs_list(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start listing old tabs task."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            task_id = start_gsheet_manage_tabs_task(uow, current_user.id, assembly_id, dry_run=True)

        return redirect(
            url_for("gsheets.view_assembly_selection", assembly_id=assembly_id, current_manage_tabs=task_id)
        )
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly or gsheet not found for manage tabs list: {e}")
        flash(_("Please configure a Google Spreadsheet first"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for manage tabs list: {e}")
        flash(_("You don't have permission to manage tabs"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Start manage tabs list error: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while starting the list tabs task"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))


@gsheets_bp.route("/assembly/<uuid:assembly_id>/manage-tabs/start-delete", methods=["POST"])
@login_required
@require_assembly_management
def start_manage_tabs_delete(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start deleting old tabs task."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            task_id = start_gsheet_manage_tabs_task(uow, current_user.id, assembly_id, dry_run=False)

        return redirect(
            url_for("gsheets.view_assembly_selection", assembly_id=assembly_id, current_manage_tabs=task_id)
        )
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly or gsheet not found for manage tabs delete: {e}")
        flash(_("Please configure a Google Spreadsheet first"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for manage tabs delete: {e}")
        flash(_("You don't have permission to manage tabs"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Start manage tabs delete error: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while starting the delete tabs task"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))


@gsheets_bp.route("/assembly/<uuid:assembly_id>/manage-tabs/<uuid:run_id>/progress")
@login_required
@require_assembly_management
def manage_tabs_progress(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """HTMX endpoint for manage tabs progress modal."""
    try:
        uow = bootstrap.bootstrap()
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
            current_app.logger.warning(
                f"Run {run_id} does not belong to assembly {assembly_id} - user {current_user.id}"
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
        current_app.logger.error(f"Manage tabs progress modal error: {e}")
        return "", 500


@gsheets_bp.route("/assembly/<uuid:assembly_id>/manage-tabs/<uuid:run_id>/cancel", methods=["POST"])
@login_required
@require_assembly_management
def cancel_manage_tabs(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Cancel a running manage tabs task."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            cancel_task(uow, current_user.id, assembly_id, run_id)

        flash(_("Task cancelled"), "info")
        return redirect(
            url_for(
                "gsheets.view_assembly_selection",
                assembly_id=assembly_id,
                current_manage_tabs=run_id,
            )
        )
    except InvalidSelection as e:
        current_app.logger.warning(f"Cannot cancel manage tabs task: {e}")
        flash(_("Cannot cancel task: %(error)s", error=str(e)), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except NotFoundError as e:
        current_app.logger.warning(f"Manage tabs task not found for cancel: {e}")
        flash(_("Task not found"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions to cancel manage tabs task: {e}")
        flash(_("You don't have permission to cancel this task"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Cancel manage tabs error: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while cancelling the task"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))


# --- Selection history ---


@gsheets_bp.route("/assembly/<uuid:assembly_id>/selection/history/<uuid:run_id>")
@login_required
def view_run_details(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """View details of a selection run from history.

    Redirects to the appropriate section based on task type.
    """
    try:
        uow = bootstrap.bootstrap()
        with uow:
            # Verify user has permissions for this assembly
            get_assembly_with_permissions(uow, assembly_id, current_user.id)

            # Fetch the run record
            run_record = uow.selection_run_records.get_by_task_id(run_id)

            if not run_record:
                flash(_("Selection run not found"), "error")
                return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))

            # Validate the run belongs to this assembly
            if run_record.assembly_id != assembly_id:
                flash(_("Selection run does not belong to this assembly"), "error")
                return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))

            # For now, redirect back to selection page with current_selection parameter
            # This will show the task progress modal
            # TODO: Create dedicated detail pages for completed runs with full report
            return redirect(
                url_for("gsheets.view_assembly_selection", assembly_id=assembly_id, current_selection=run_id)
            )

    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for run details: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} run details: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View run details error for assembly {assembly_id} run {run_id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while loading the run details"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))


# --- Replacement views ---


@gsheets_bp.route("/assembly/<uuid:assembly_id>/replacement")
@login_required
def view_assembly_replacement(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Legacy route - redirects to selection page with replacement modal open."""
    return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id, replacement_modal="open"))


@gsheets_bp.route("/assembly/<uuid:assembly_id>/replacement/<uuid:run_id>")
@login_required
def view_assembly_replacement_with_run(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Legacy route - redirects to query parameter version for backwards compatibility."""
    # Preserve min/max params if present
    min_select = request.args.get("min_select")
    max_select = request.args.get("max_select")
    return redirect(
        url_for(
            "gsheets.view_assembly_selection",
            assembly_id=assembly_id,
            current_replacement=run_id,
            min_select=min_select,
            max_select=max_select,
        )
    )


@gsheets_bp.route("/assembly/<uuid:assembly_id>/replacement/load", methods=["POST"])
@login_required
def start_replacement_load(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a replacement data validation task."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            task_id = start_gsheet_replace_load_task(uow, current_user.id, assembly_id)

        return redirect(url_for("gsheets.view_assembly_replacement_with_run", assembly_id=assembly_id, run_id=task_id))

    except InvalidSelection as e:
        current_app.logger.warning(f"Invalid selection attempted with replacement load for assembly {assembly_id}: {e}")
        flash(_("Could not start task to read gsheet: %(error)s", error=str(e)), "error")
        return redirect(url_for("gsheets.view_assembly_replacement", assembly_id=assembly_id))

    except NotFoundError as e:
        current_app.logger.warning(f"Failed to start replacement load for assembly {assembly_id}: {e}")
        flash(_("Failed to start loading task: %(error)s", error=str(e)), "error")
        return redirect(url_for("gsheets.view_assembly_replacement", assembly_id=assembly_id))

    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions for starting replacement load {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))

    except Exception as e:
        current_app.logger.error(f"Error starting replacement load for assembly {assembly_id}: {e}")
        flash(_("An unexpected error occurred while starting the loading task"), "error")
        return redirect(url_for("gsheets.view_assembly_replacement", assembly_id=assembly_id))


@gsheets_bp.route("/assembly/<uuid:assembly_id>/replacement/run", methods=["POST"])
@login_required
def start_replacement_run(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a replacement selection task."""
    try:
        min_select = request.args.get("min_select", type=int) or 0
        max_select = request.args.get("max_select", type=int) or 0

        # Get and validate number_to_select from form
        number_to_select_str = request.form.get("number_to_select")
        if not number_to_select_str:
            flash(_("Number of people to select is required"), "error")
            return redirect(url_for("gsheets.view_assembly_replacement", assembly_id=assembly_id))

        try:
            number_to_select = int(number_to_select_str)
            if number_to_select <= 0:
                flash(_("Number of people to select must be greater than zero"), "error")
                return redirect(url_for("gsheets.view_assembly_replacement", assembly_id=assembly_id))
        except ValueError:
            flash(_("Number of people to select must be a valid integer"), "error")
            return redirect(url_for("gsheets.view_assembly_replacement", assembly_id=assembly_id))

        uow = bootstrap.bootstrap()
        with uow:
            task_id = start_gsheet_replace_task(uow, current_user.id, assembly_id, number_to_select)

        return redirect(
            url_for(
                "gsheets.view_assembly_replacement_with_run",
                assembly_id=assembly_id,
                run_id=task_id,
                num_to_select=number_to_select,
                min_select=min_select,
                max_select=max_select,
            )
        )

    except NotFoundError as e:
        current_app.logger.warning(f"Failed to start replacement for assembly {assembly_id}: {e}")
        flash(_("Failed to start replacement task: %(error)s", error=str(e)), "error")
        return redirect(url_for("gsheets.view_assembly_replacement", assembly_id=assembly_id))

    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions for starting replacement {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))

    except Exception as e:
        current_app.logger.error(f"Error starting replacement for assembly {assembly_id}: {e}")
        flash(_("An unexpected error occurred while starting the replacement task"), "error")
        return redirect(url_for("gsheets.view_assembly_replacement", assembly_id=assembly_id))


@gsheets_bp.route("/assembly/<uuid:assembly_id>/replacement/<uuid:run_id>/cancel", methods=["POST"])
@login_required
def cancel_replacement_run(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Cancel a running replacement task."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            cancel_task(uow, current_user.id, assembly_id, run_id)

        flash(_("Task has been cancelled"), "success")
        return redirect(url_for("gsheets.view_assembly_replacement_with_run", assembly_id=assembly_id, run_id=run_id))

    except NotFoundError as e:
        current_app.logger.warning(f"Task {run_id} not found for cancellation by user {current_user.id}: {e}")
        flash(_("Task not found"), "error")
        return redirect(url_for("gsheets.view_assembly_replacement", assembly_id=assembly_id))

    except InvalidSelection as e:
        current_app.logger.warning(f"Cannot cancel task {run_id}: {e}")
        flash(str(e), "error")
        return redirect(url_for("gsheets.view_assembly_replacement_with_run", assembly_id=assembly_id, run_id=run_id))

    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions to cancel task {run_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to cancel this task"), "error")
        return redirect(url_for("backoffice.dashboard"))

    except Exception as e:
        current_app.logger.error(f"Error cancelling task {run_id}: {e}")
        flash(_("An error occurred while cancelling the task"), "error")
        return redirect(url_for("gsheets.view_assembly_replacement_with_run", assembly_id=assembly_id, run_id=run_id))


# --- GSheet config views ---


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
        final_gsheet = update_assembly_gsheet(uow=uow, assembly_id=assembly_id, user_id=user_id, **form_data)
        flash(_("Google Spreadsheet configuration updated successfully"), "success")
    else:
        final_gsheet = add_assembly_gsheet(uow=uow, assembly_id=assembly_id, user_id=user_id, **form_data)
        flash(_("Google Spreadsheet configuration created successfully"), "success")

    # Soft validation warning - check if columns_to_keep is empty
    if not final_gsheet.columns_to_keep:
        flash(
            _(
                "Warning: No columns to keep specified. "
                "This means the output will only include participant data columns "
                "used for the targets and address checking. Is this intentional?"
            ),
            "warning",
        )

    return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="gsheet"))


@gsheets_bp.route("/assembly/<uuid:assembly_id>/gsheet/save", methods=["POST"])
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


@gsheets_bp.route("/assembly/<uuid:assembly_id>/gsheet/delete", methods=["POST"])
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
