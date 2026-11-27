"""ABOUTME: Backoffice Selection page: the tab itself, its history, and the redirects into it
ABOUTME: Provides /backoffice/project/*/selection and holds the page renderer the selection task routes share"""

import contextlib
import uuid
from collections.abc import Mapping
from typing import Any

import structlog
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required
from sortition_algorithms.features import maximum_selection, minimum_selection

from opendlp import bootstrap
from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.respondents import Respondent
from opendlp.domain.users import User
from opendlp.domain.value_objects import SelectionTaskType
from opendlp.entrypoints.forms import (
    DbSelectionSettingsForm,
)
from opendlp.service_layer.assembly_service import (
    CSVUploadStatus,
    determine_data_source,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    get_tab_enabled_states,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, NotFoundError, ServiceLayerError
from opendlp.service_layer.permissions import can_manage_assembly
from opendlp.service_layer.replacement_targets import (
    ReplacementPlan,
    ReplacementValidation,
    build_replacement_plan,
    check_replacement_plan,
    run_feasibility_check,
)
from opendlp.service_layer.report_translation import translate_run_report_to_html
from opendlp.service_layer.respondent_service import count_held_respondents, get_respondent_attribute_columns
from opendlp.service_layer.selection_history import name_history
from opendlp.service_layer.sortition import (
    LoadRunResult,
    TabManagementResult,
    check_and_update_task_health,
    get_active_initial_selection_run_id,
    get_manage_old_tabs_status,
    get_selected_respondents,
    get_selection_run_status,
)
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.service_layer.writing_guard import SelectionAlreadyRunning, running_task_query_param
from opendlp.translations import gettext as _

selection_bp = Blueprint("selection", __name__)

logger = structlog.get_logger(__name__)


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
    except ValueError, TypeError:
        # Invalid or malformed manage_tabs_param - ignore and return defaults
        pass
    return None, None, [], None


def _get_selection_modal_context(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, selection_param: str | None
) -> tuple[uuid.UUID | None, object | None, list, str, list[Respondent]]:
    """Get context for displaying the initial selection progress modal.

    Returns (current_selection, run_record, log_messages, translated_report_html,
    selected_respondents). The respondents are only loaded for a completed run;
    the modal lists them.
    """
    if not selection_param:
        return None, None, [], "", []

    try:
        current_selection = uuid.UUID(selection_param)
        check_and_update_task_health(uow, current_selection)
        result = get_selection_run_status(uow, current_selection)

        if result.run_record and result.run_record.assembly_id == assembly_id:
            selected_respondents = (
                get_selected_respondents(uow, result.run_record) if result.run_record.is_completed else []
            )
            return (
                current_selection,
                result.run_record,
                result.log_messages,
                translate_run_report_to_html(result.run_report) if result.run_report else "",
                selected_respondents,
            )
    except ValueError, TypeError:
        logger.debug("Invalid selection_param for _get_selection_modal_context: %r", selection_param)

    return None, None, [], "", []


def load_features_pending(run_record: object, result: object) -> bool:
    """True when a load task is COMPLETED in postgres but Celery's result backend
    hasn't surfaced the typed return value yet.

    The load task commits ``status=COMPLETED`` to postgres before its return value
    lands in the Celery result backend (Redis). A GET that arrives in that window
    sees the run record as finished but ``get_selection_run_status`` cannot build
    a ``LoadRunResult`` — so min/max can't be computed and the replacement modal
    would render in the "result" state with no form and no polling. Detect that
    state so the caller can keep the modal polling until the next tick.
    """
    if getattr(run_record, "task_type", None) != SelectionTaskType.LOAD_REPLACEMENT_GSHEET:
        return False
    if not getattr(run_record, "is_completed", False):
        return False
    return not (isinstance(result, LoadRunResult) and result.features is not None and result.success)


def _get_replacement_modal_context(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    replacement_param: str | None,
    initial_min_select: int | None,
    initial_max_select: int | None,
) -> tuple[uuid.UUID | None, object | None, list, str, int | None, int | None, bool]:
    """Get context for displaying the replacement selection modal.

    Returns (current_replacement, run_record, log_messages, translated_report_html,
    min_select, max_select, features_pending).
    """
    if not replacement_param:
        return None, None, [], "", initial_min_select, initial_max_select, False

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
                load_features_pending(result.run_record, result),
            )
    except ValueError, TypeError:
        logger.debug("Invalid replacement_param for _get_replacement_modal_context: %r", replacement_param)

    return None, None, [], "", initial_min_select, initial_max_select, False


def _get_history_context(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    page: int,
    per_page: int,
    show_all: bool,
) -> tuple[list[tuple[SelectionRunRecord, User | None]], int, dict[uuid.UUID, str], int]:
    """One page of the selection history, with a name for every run of the assembly.

    Unless ``show_all`` is set, the page covers only the current era: the run
    that started it and everything after. Returns (page of (record, user),
    count of runs in view, run names by task id, count of older runs hidden).

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    summaries = uow.selection_run_records.get_history_summaries(assembly_id)
    naming = name_history(summaries)
    era_start = naming.current_era_start
    older_count = 0 if era_start is None else sum(1 for s in summaries if s.created_at < era_start)
    since = None if show_all else era_start
    run_history, total_count = uow.selection_run_records.get_by_assembly_id_paginated(
        assembly_id, page, per_page, since=since
    )
    return run_history, total_count, naming.names, older_count


# --- Selection views ---


def _get_db_replacement_dialog_context(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    validation: ReplacementValidation | None,
) -> tuple[ReplacementPlan | None, ReplacementValidation | None]:
    """The plan and validation the database replacement dialog shows.

    Returns (None, None) for a user who may view the assembly but not manage
    it: the page renders for them with the dialog closed.

    The caller is expected to manage the `uow` context (`with uow: ...`), and
    to call run_feasibility_check() on the validation once it has closed.
    """
    try:
        plan = build_replacement_plan(uow, current_user.id, assembly_id)
    except InsufficientPermissions:
        return None, None
    if validation is not None:
        plan.apply_submitted(validation.submitted)
    elif not plan.nothing_to_fill:
        validation = check_replacement_plan(uow, assembly_id, plan)
    return plan, validation


# What a selection on a project held in OpenDLP can be waiting for, in the
# order the page lists them.
WAITING_FOR_TARGETS = "targets"
WAITING_FOR_RESPONDENTS = "respondents"
WAITING_FOR_SETTINGS = "settings"


def selection_waiting_for(csv_status: CSVUploadStatus, settings_confirmed: bool) -> list[str]:
    """What a project held in OpenDLP still needs before a selection can run."""
    waiting = []
    if not csv_status.has_targets:
        waiting.append(WAITING_FOR_TARGETS)
    if not csv_status.has_respondents:
        waiting.append(WAITING_FOR_RESPONDENTS)
    if not settings_confirmed:
        waiting.append(WAITING_FOR_SETTINGS)
    return waiting


def unbound_selection_settings_form(assembly: Assembly, available_columns: list[str]) -> DbSelectionSettingsForm:
    """The selection settings form as first shown: holding what is stored."""
    settings = assembly.selection_settings
    return DbSelectionSettingsForm(
        formdata=None,
        data={
            "check_same_address": settings.check_same_address if settings else False,
            "check_same_address_cols_string": settings.check_same_address_cols_string if settings else "",
        },
        available_columns=available_columns,
    )


def render_selection_page(
    assembly_id: uuid.UUID,
    *,
    replacement_form: Mapping[str, str] | None = None,
    replacement_validation: ReplacementValidation | None = None,
    selection_settings_form: DbSelectionSettingsForm | None = None,
) -> ResponseReturnValue:
    """Render the selection page for the current user.

    A project held in OpenDLP has its selection settings in a dialog over this
    page. A save that was refused without htmx re-renders the page with the
    dialog open and ``selection_settings_form`` carrying the reasons.

    The database replacement dialog re-renders this page after a rejected
    submission: ``replacement_form`` carries the numbers the organiser typed and
    ``replacement_validation`` the errors to show beside them. Either forces the
    dialog open. When the dialog opens without a submission, the calculated
    targets are validated here, so it shows their errors from the start.
    Service-layer exceptions propagate to the caller.
    """
    page = request.args.get("page", 1, type=int)
    per_page = 15

    current_selection: uuid.UUID | None = None
    run_record = None
    log_messages: list = []
    translated_report_html = ""
    selected_respondents: list[Respondent] = []

    # Manage tabs variables (extracted to helper for complexity)
    current_manage_tabs_param = request.args.get("current_manage_tabs")

    uow = bootstrap.get_flask_uow()
    with uow:
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        # Get selection modal context
        current_selection, run_record, log_messages, translated_report_html, selected_respondents = (
            _get_selection_modal_context(uow, assembly_id, request.args.get("current_selection"))
        )

        # Get replacement modal context
        (
            current_replacement,
            replacement_run_record,
            replacement_log_messages,
            replacement_translated_report_html,
            replacement_min_select,
            replacement_max_select,
            replacement_features_pending,
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

        # If the latest selection run is an unfinished initial-selection task, expose its id
        # so the Initial Selection card can offer "View Running Selection" instead of the
        # check/test/run buttons.
        active_initial_selection_run_id = get_active_initial_selection_run_id(uow, assembly_id)

    # Reuse the same UnitOfWork for the remaining sequential reads.
    # Check if gsheet is configured
    gsheet = None
    with uow:
        try:
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)
        except ServiceLayerError as gsheet_error:
            logger.error("Error loading gsheet config for selection", error=str(gsheet_error))

    # Fetch paginated selection history
    history_show_all = request.args.get("history") == "all"
    with uow:
        run_history, total_count, run_names, history_older_count = _get_history_context(
            uow, assembly_id, page, per_page, history_show_all
        )
        total_pages = (total_count + per_page - 1) // per_page

    replacement_modal_open = (
        request.args.get("replacement_modal") == "open"
        or current_replacement is not None
        or replacement_validation is not None
    )
    edit_number_modal_open = request.args.get("edit_number") == "1"

    # Get CSV status for tab enabled states
    csv_status = None
    # No CSV data is expected for new assemblies.
    with uow, contextlib.suppress(ServiceLayerError):
        csv_status = get_csv_upload_status(uow, current_user.id, assembly_id)

    # The tabs are worked out as on every other tab of the project.
    data_source, _locked = determine_data_source(gsheet, csv_status, assembly.data_source)
    targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(data_source, gsheet, csv_status)

    csv_held_count = 0
    csv_settings_confirmed = True  # Default to True (not applicable for gsheet)
    selection_waiting: list[str] = []
    selection_settings_columns: list[str] = []
    selection_settings_open = False
    can_manage_project = can_manage_assembly(current_user, assembly)
    replacement_plan = None
    if data_source == "csv" and csv_status:
        csv_settings_confirmed = csv_status.csv_config.settings_confirmed if csv_status.csv_config else False
        selection_waiting = selection_waiting_for(csv_status, csv_settings_confirmed)
        # The settings dialog is drawn with the page when a save was refused
        # without htmx, or the address asks for it (?settings=1).
        selection_settings_open = can_manage_project and (
            selection_settings_form is not None or request.args.get("settings") == "1"
        )
        if selection_settings_open:
            with uow:
                selection_settings_columns = get_respondent_attribute_columns(uow, assembly_id)
            if selection_settings_form is None:
                selection_settings_form = unbound_selection_settings_form(assembly, selection_settings_columns)
        # Count the respondents holding a place: selected or confirmed
        try:
            with uow:
                csv_held_count = count_held_respondents(uow, assembly_id)
        except ServiceLayerError as count_error:
            logger.error("Error counting held respondents", error=str(count_error))
        if replacement_modal_open:
            with uow:
                replacement_plan, replacement_validation = _get_db_replacement_dialog_context(
                    uow, assembly_id, replacement_validation
                )
            replacement_modal_open = replacement_plan is not None
            # The solver is the slow part, so it runs once the transaction has closed.
            if replacement_validation is not None:
                run_feasibility_check(replacement_validation)

    # Replacements fill places that are held by nobody: some people must hold a
    # place, and fewer than the assembly needs.
    replacement_enabled = (
        data_source == "csv"
        and not selection_waiting
        and 0 < csv_held_count < assembly.number_to_select
        and active_initial_selection_run_id is None
    )

    return render_template(
        "backoffice/assembly_selection.html",
        assembly=assembly,
        gsheet=gsheet,
        run_history=run_history,
        run_names=run_names,
        history_show_all=history_show_all,
        history_older_count=history_older_count,
        page=page,
        per_page=per_page,
        total_count=total_count,
        total_pages=total_pages,
        current_selection=current_selection,
        run_record=run_record,
        log_messages=log_messages,
        translated_report_html=translated_report_html,
        selected_respondents=selected_respondents,
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
        replacement_features_pending=replacement_features_pending,
        replacement_plan=replacement_plan,
        replacement_form=replacement_form or {},
        replacement_validation=replacement_validation,
        replacement_enabled=replacement_enabled,
        edit_number_modal_open=edit_number_modal_open,
        data_source=data_source,
        targets_enabled=targets_enabled,
        respondents_enabled=respondents_enabled,
        selection_enabled=selection_enabled,
        csv_held_count=csv_held_count,
        csv_settings_confirmed=csv_settings_confirmed,
        selection_waiting=selection_waiting,
        can_manage_project=can_manage_project,
        selection_settings_open=selection_settings_open,
        selection_settings_form=selection_settings_form if selection_settings_open else None,
        selection_settings_columns=selection_settings_columns,
        selection_settings_from="",
        active_initial_selection_run_id=active_initial_selection_run_id,
    ), 200


@selection_bp.route("/project/<uuid:assembly_id>/selection")
@login_required
def view_assembly_selection(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly selection page."""
    try:
        return render_selection_page(assembly_id)
    except NotFoundError as e:
        logger.warning("Assembly not found for selection page", assembly_id=str(assembly_id), error=str(e))
        flash(_("Project not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        logger.warning("Insufficient permissions for assembly selection", assembly_id=str(assembly_id), error=str(e))
        flash(_("You don't have permission to view this project"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        logger.exception("View assembly selection error", assembly_id=str(assembly_id), error=str(e))
        flash(_("An error occurred while loading the selection page"), "error")
        return redirect(url_for("backoffice.dashboard"))


@selection_bp.route("/project/<uuid:assembly_id>/selection/<uuid:run_id>")
@login_required
def view_assembly_selection_with_run(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Legacy route - redirects to query parameter version for backwards compatibility."""
    return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id, current_selection=run_id))


def redirect_to_running_task(assembly_id: uuid.UUID, running: SelectionAlreadyRunning) -> ResponseReturnValue:
    """Send the user into the progress modal of the task that holds the assembly, saying why.

    The modal has the cancel button, so from there they can wait or cancel.
    """
    flash(
        _(
            "Another task is already running on this project: %(task)s. You can wait for it to finish, or cancel it here.",
            task=running.task_label,
        ),
        "info",
    )
    params: dict[str, Any] = {running_task_query_param(running.task_type): running.task_id}
    return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id, **params))


# --- Selection history ---


@selection_bp.route("/project/<uuid:assembly_id>/selection/history/<uuid:run_id>")
@login_required
def view_run_details(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """View details of a selection run from history.

    Redirects to the appropriate section based on task type.
    """
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            # Verify user has permissions for this assembly
            get_assembly_with_permissions(uow, assembly_id, current_user.id)

            # Fetch the run record
            run_record = uow.selection_run_records.get_by_task_id(run_id)

            if not run_record:
                flash(_("Selection run not found"), "error")
                return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))

            # Validate the run belongs to this assembly
            if run_record.assembly_id != assembly_id:
                flash(_("Selection run does not belong to this project"), "error")
                return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))

            # For now, redirect back to selection page with current_selection parameter
            # This will show the task progress modal
            # TODO: Create dedicated detail pages for completed runs with full report
            return redirect(
                url_for("selection.view_assembly_selection", assembly_id=assembly_id, current_selection=run_id)
            )

    except NotFoundError as e:
        logger.warning("Assembly not found for run details", assembly_id=str(assembly_id), error=str(e))
        flash(_("Project not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        logger.warning("Insufficient permissions for assembly run details", assembly_id=str(assembly_id), error=str(e))
        flash(_("You don't have permission to view this project"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        logger.exception("View run details error", assembly_id=str(assembly_id), run_id=str(run_id), error=str(e))
        flash(_("An error occurred while loading the run details"), "error")
        return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id))


# --- Replacement views ---


@selection_bp.route("/project/<uuid:assembly_id>/replacement")
@login_required
def view_assembly_replacement(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Legacy route - redirects to selection page with replacement modal open."""
    return redirect(url_for("selection.view_assembly_selection", assembly_id=assembly_id, replacement_modal="open"))


@selection_bp.route("/project/<uuid:assembly_id>/replacement/<uuid:run_id>")
@login_required
def view_assembly_replacement_with_run(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Legacy route - redirects to query parameter version for backwards compatibility."""
    # Preserve min/max params if present
    min_select = request.args.get("min_select")
    max_select = request.args.get("max_select")
    return redirect(
        url_for(
            "selection.view_assembly_selection",
            assembly_id=assembly_id,
            current_replacement=run_id,
            min_select=min_select,
            max_select=max_select,
        )
    )
