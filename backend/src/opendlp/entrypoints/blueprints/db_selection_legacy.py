"""ABOUTME: Database selection routes for running sortition on DB-stored data
ABOUTME: Handles selection, validation, progress tracking and CSV downloads"""

import uuid
from dataclasses import dataclass

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.entrypoints.decorators import require_assembly_management
from opendlp.service_layer.assembly_service import (
    get_assembly_with_permissions,
    get_or_create_csv_config,
    get_or_create_selection_settings,
    update_csv_config,
    update_selection_settings,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection, NotFoundError
from opendlp.service_layer.report_translation import translate_run_report_to_html
from opendlp.service_layer.respondent_service import (
    count_non_pool_respondents,
    get_respondent_attribute_columns,
    reset_selection_status,
)
from opendlp.service_layer.sortition import (
    cancel_task,
    check_and_update_task_health,
    check_db_selection_data,
    generate_selection_csvs,
    get_selection_run_status,
    start_db_select_task,
)
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import gettext as _

from ..forms import DbSelectionSettingsForm

db_selection_legacy_bp = Blueprint("db_selection_legacy", __name__)


@dataclass
class SelectionReadiness:
    """Tracks whether the prerequisites for running a selection are met."""

    settings_confirmed: bool
    has_targets: bool
    has_respondents: bool
    non_pool_count: int

    @property
    def can_run_selection(self) -> bool:
        return self.settings_confirmed and self.has_targets and self.has_respondents and self.non_pool_count == 0


def _get_selection_readiness(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, settings_confirmed: bool
) -> SelectionReadiness:
    """Gather the readiness checks for running a selection."""
    return SelectionReadiness(
        settings_confirmed=settings_confirmed,
        has_targets=uow.target_categories.count_by_assembly_id(assembly_id) > 0,
        has_respondents=uow.respondents.count_by_assembly_id(assembly_id) > 0,
        non_pool_count=count_non_pool_respondents(uow, assembly_id),
    )


@db_selection_legacy_bp.route("/assemblies/<uuid:assembly_id>/db_select", methods=["GET"])
@login_required
@require_assembly_management
def view_db_selection(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)
            readiness = _get_selection_readiness(uow, assembly_id, csv_config.settings_confirmed)

        return render_template(
            "db_selection/select.html",
            assembly=assembly,
            csv_config=csv_config,
            current_tab="db_selection",
            readiness=readiness,
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_legacy_bp.route("/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>", methods=["GET"])
@login_required
@require_assembly_management
def view_db_selection_with_run(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)
            result = get_selection_run_status(uow, run_id)
            readiness = _get_selection_readiness(uow, assembly_id, csv_config.settings_confirmed)

        if result.run_record and result.run_record.assembly_id != assembly_id:
            flash(_("Invalid task ID for this assembly"), "error")
            return redirect(url_for("db_selection_legacy.view_db_selection", assembly_id=assembly_id))

        return render_template(
            "db_selection/select.html",
            assembly=assembly,
            csv_config=csv_config,
            current_tab="db_selection",
            run_record=result.run_record,
            run_report=result.run_report,
            translated_report_html=translate_run_report_to_html(result.run_report),
            run_id=run_id,
            readiness=readiness,
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_legacy_bp.route("/assemblies/<uuid:assembly_id>/db_select/check", methods=["POST"])
@login_required
@require_assembly_management
def check_db_data(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)
            readiness = _get_selection_readiness(uow, assembly_id, csv_config.settings_confirmed)

        if not csv_config.settings_confirmed:
            flash(_("Please review and save the selection settings before checking targets."), "warning")
            return redirect(url_for("db_selection_legacy.view_db_selection_settings", assembly_id=assembly_id))

        uow2 = bootstrap.bootstrap()
        with uow2:
            check_result = check_db_selection_data(uow=uow2, user_id=current_user.id, assembly_id=assembly_id)

        return render_template(
            "db_selection/select.html",
            assembly=assembly,
            csv_config=csv_config,
            current_tab="db_selection",
            check_result=check_result,
            readiness=readiness,
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Check data error for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An unexpected error occurred while checking data"), "error")
        return redirect(url_for("db_selection_legacy.view_db_selection", assembly_id=assembly_id))


@db_selection_legacy_bp.route("/assemblies/<uuid:assembly_id>/db_select/run", methods=["POST"])
@login_required
@require_assembly_management
def start_db_selection(assembly_id: uuid.UUID) -> ResponseReturnValue:
    test_selection = request.form.get("test_selection") == "1"
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            if assembly.csv is None or not assembly.csv.settings_confirmed:
                flash(_("Please review and save the selection settings before running selection."), "warning")
                return redirect(url_for("db_selection_legacy.view_db_selection_settings", assembly_id=assembly_id))
            task_id = start_db_select_task(uow, current_user.id, assembly_id, test_selection=test_selection)

        return redirect(
            url_for("db_selection_legacy.view_db_selection_with_run", assembly_id=assembly_id, run_id=task_id)
        )

    except InvalidSelection as e:
        flash(_("Could not start selection task: %(error)s", error=str(e)), "error")
        return redirect(url_for("db_selection_legacy.view_db_selection", assembly_id=assembly_id))
    except NotFoundError as e:
        flash(_("Failed to start selection task: %(error)s", error=str(e)), "error")
        return redirect(url_for("db_selection_legacy.view_db_selection", assembly_id=assembly_id))
    except InsufficientPermissions:
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error starting db select for assembly {assembly_id}: {e}")
        flash(_("An unexpected error occurred while starting the selection task"), "error")
        return redirect(url_for("db_selection_legacy.view_db_selection", assembly_id=assembly_id))


@db_selection_legacy_bp.route("/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>/progress", methods=["GET"])
@login_required
@require_assembly_management
def db_selection_progress(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            check_and_update_task_health(uow, run_id)
            result = get_selection_run_status(uow, run_id)

        if not result.run_record:
            return "", 404
        if result.run_record.assembly_id != assembly_id:
            return "", 404

        response = current_app.make_response((
            render_template(
                "db_selection/components/progress.html",
                assembly=assembly,
                run_record=result.run_record,
                translated_report_html=translate_run_report_to_html(result.run_report),
                run_id=run_id,
                progress_url=url_for(
                    "db_selection_legacy.db_selection_progress", assembly_id=assembly_id, run_id=run_id
                ),
            ),
            200,
        ))
        if result.run_record.has_finished:
            response.headers["HX-Refresh"] = "true"
        return response
    except (NotFoundError, InsufficientPermissions):
        return "", 404
    except Exception as e:
        current_app.logger.error(f"Progress polling error for assembly {assembly_id}: {e}")
        return "", 500


@db_selection_legacy_bp.route("/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>/cancel", methods=["POST"])
@login_required
@require_assembly_management
def cancel_db_selection(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            cancel_task(uow, current_user.id, assembly_id, run_id)
        flash(_("Task has been cancelled"), "success")
        return redirect(
            url_for("db_selection_legacy.view_db_selection_with_run", assembly_id=assembly_id, run_id=run_id)
        )
    except NotFoundError:
        flash(_("Task not found"), "error")
        return redirect(url_for("db_selection_legacy.view_db_selection", assembly_id=assembly_id))
    except InvalidSelection as e:
        flash(str(e), "error")
        return redirect(
            url_for("db_selection_legacy.view_db_selection_with_run", assembly_id=assembly_id, run_id=run_id)
        )
    except InsufficientPermissions:
        flash(_("You don't have permission to cancel this task"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_legacy_bp.route(
    "/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>/download/selected", methods=["GET"]
)
@login_required
@require_assembly_management
def download_selected_csv(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
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
        return redirect(url_for("db_selection_legacy.view_db_selection", assembly_id=assembly_id))
    except InvalidSelection as e:
        flash(str(e), "error")
        return redirect(
            url_for("db_selection_legacy.view_db_selection_with_run", assembly_id=assembly_id, run_id=run_id)
        )
    except InsufficientPermissions:
        flash(_("You don't have permission to download this data"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_legacy_bp.route(
    "/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>/download/remaining", methods=["GET"]
)
@login_required
@require_assembly_management
def download_remaining_csv(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
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
        return redirect(url_for("db_selection_legacy.view_db_selection", assembly_id=assembly_id))
    except InvalidSelection as e:
        flash(str(e), "error")
        return redirect(
            url_for("db_selection_legacy.view_db_selection_with_run", assembly_id=assembly_id, run_id=run_id)
        )
    except InsufficientPermissions:
        flash(_("You don't have permission to download this data"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_legacy_bp.route("/assemblies/<uuid:assembly_id>/db_select/settings", methods=["GET"])
@login_required
@require_assembly_management
def view_db_selection_settings(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)
            sel_settings = get_or_create_selection_settings(uow, current_user.id, assembly_id)
            available_columns = get_respondent_attribute_columns(uow, assembly_id)

        form = DbSelectionSettingsForm(
            available_columns=available_columns,
            check_same_address=sel_settings.check_same_address,
            check_same_address_cols_string=sel_settings.check_same_address_cols_string
            if sel_settings.check_same_address_cols
            else "",
            columns_to_keep_string=sel_settings.columns_to_keep_string if sel_settings.columns_to_keep else "",
        )
        return render_template(
            "db_selection/settings.html",
            assembly=assembly,
            csv_config=csv_config,
            form=form,
            available_columns=available_columns,
            current_tab="db_selection",
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_legacy_bp.route("/assemblies/<uuid:assembly_id>/db_select/settings", methods=["POST"])
@login_required
@require_assembly_management
def save_db_selection_settings(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)
            available_columns = get_respondent_attribute_columns(uow, assembly_id)

        form = DbSelectionSettingsForm(available_columns=available_columns)
        if form.validate_on_submit():
            uow2 = bootstrap.bootstrap()
            update_selection_settings(
                uow=uow2,
                user_id=current_user.id,
                assembly_id=assembly_id,
                selection_algorithm="maximin",
                check_same_address=form.check_same_address.data or False,
                check_same_address_cols=_parse_comma_list(form.check_same_address_cols_string.data),
                columns_to_keep=_parse_comma_list(form.columns_to_keep_string.data),
            )
            uow3 = bootstrap.bootstrap()
            update_csv_config(
                uow=uow3,
                user_id=current_user.id,
                assembly_id=assembly_id,
                settings_confirmed=True,
            )
            flash(_("Selection settings saved"), "success")
            return redirect(url_for("db_selection_legacy.view_db_selection", assembly_id=assembly_id))

        # Re-render with validation errors (assembly/csv_config already fetched above)
        return render_template(
            "db_selection/settings.html",
            assembly=assembly,
            csv_config=csv_config,
            form=form,
            available_columns=available_columns,
            current_tab="db_selection",
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_legacy_bp.route("/assemblies/<uuid:assembly_id>/db_replace", methods=["GET"])
@login_required
@require_assembly_management
def view_db_replacement(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
        return render_template(
            "db_selection/replace.html",
            assembly=assembly,
            current_tab="db_selection",
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_legacy_bp.route("/assemblies/<uuid:assembly_id>/db_select/reset-respondents", methods=["POST"])
@login_required
@require_assembly_management
def reset_respondents_for_selection(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        count = reset_selection_status(uow, current_user.id, assembly_id)
        flash(_("Reset %(count)s respondents to Pool status", count=count), "success")
        return redirect(url_for("db_selection_legacy.view_db_selection", assembly_id=assembly_id))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to reset selection status"), "error")
        return redirect(url_for("db_selection_legacy.view_db_selection", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Reset respondent status error for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An unexpected error occurred"), "error")
        return redirect(url_for("db_selection_legacy.view_db_selection", assembly_id=assembly_id))


def _parse_comma_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
