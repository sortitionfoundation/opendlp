"""ABOUTME: Database selection routes for running sortition on DB-stored data
ABOUTME: Handles selection, validation, progress tracking and CSV downloads"""

import uuid

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.entrypoints.decorators import require_assembly_management
from opendlp.service_layer.assembly_service import (
    get_assembly_with_permissions,
    get_or_create_csv_config,
    update_csv_config,
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

from ..forms import DbSelectionSettingsForm

db_selection_bp = Blueprint("db_selection", __name__)


@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select", methods=["GET"])
@login_required
@require_assembly_management
def view_db_selection(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)

        return render_template(
            "db_selection/select.html",
            assembly=assembly,
            csv_config=csv_config,
            current_tab="db_selection",
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>", methods=["GET"])
@login_required
@require_assembly_management
def view_db_selection_with_run(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)
            result = get_selection_run_status(uow, run_id)

        if result.run_record and result.run_record.assembly_id != assembly_id:
            flash(_("Invalid task ID for this assembly"), "error")
            return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))

        return render_template(
            "db_selection/select.html",
            assembly=assembly,
            csv_config=csv_config,
            current_tab="db_selection",
            run_record=result.run_record,
            run_report=result.run_report,
            translated_report_html=translate_run_report_to_html(result.run_report),
            run_id=run_id,
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/check", methods=["POST"])
@login_required
@require_assembly_management
def check_db_data(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)

        uow2 = bootstrap.bootstrap()
        with uow2:
            check_result = check_db_selection_data(uow=uow2, user_id=current_user.id, assembly_id=assembly_id)

        return render_template(
            "db_selection/select.html",
            assembly=assembly,
            csv_config=csv_config,
            current_tab="db_selection",
            check_result=check_result,
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
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))


@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/run", methods=["POST"])
@login_required
@require_assembly_management
def start_db_selection(assembly_id: uuid.UUID) -> ResponseReturnValue:
    test_selection = request.form.get("test_selection") == "1"
    try:
        uow = bootstrap.bootstrap()
        with uow:
            task_id = start_db_select_task(uow, current_user.id, assembly_id, test_selection=test_selection)

        return redirect(url_for("db_selection.view_db_selection_with_run", assembly_id=assembly_id, run_id=task_id))

    except InvalidSelection as e:
        flash(_("Could not start selection task: %(error)s", error=str(e)), "error")
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))
    except NotFoundError as e:
        flash(_("Failed to start selection task: %(error)s", error=str(e)), "error")
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))
    except InsufficientPermissions:
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error starting db select for assembly {assembly_id}: {e}")
        flash(_("An unexpected error occurred while starting the selection task"), "error")
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))


@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>/progress", methods=["GET"])
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
                progress_url=url_for("db_selection.db_selection_progress", assembly_id=assembly_id, run_id=run_id),
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


@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>/cancel", methods=["POST"])
@login_required
@require_assembly_management
def cancel_db_selection(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            cancel_task(uow, current_user.id, assembly_id, run_id)
        flash(_("Task has been cancelled"), "success")
        return redirect(url_for("db_selection.view_db_selection_with_run", assembly_id=assembly_id, run_id=run_id))
    except NotFoundError:
        flash(_("Task not found"), "error")
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))
    except InvalidSelection as e:
        flash(str(e), "error")
        return redirect(url_for("db_selection.view_db_selection_with_run", assembly_id=assembly_id, run_id=run_id))
    except InsufficientPermissions:
        flash(_("You don't have permission to cancel this task"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>/download/selected", methods=["GET"])
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
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))
    except InvalidSelection as e:
        flash(str(e), "error")
        return redirect(url_for("db_selection.view_db_selection_with_run", assembly_id=assembly_id, run_id=run_id))
    except InsufficientPermissions:
        flash(_("You don't have permission to download this data"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>/download/remaining", methods=["GET"])
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
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))
    except InvalidSelection as e:
        flash(str(e), "error")
        return redirect(url_for("db_selection.view_db_selection_with_run", assembly_id=assembly_id, run_id=run_id))
    except InsufficientPermissions:
        flash(_("You don't have permission to download this data"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/settings", methods=["GET"])
@login_required
@require_assembly_management
def view_db_selection_settings(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)

        form = DbSelectionSettingsForm(
            check_same_address=csv_config.check_same_address,
            check_same_address_cols_string=", ".join(csv_config.check_same_address_cols)
            if csv_config.check_same_address_cols
            else "",
            columns_to_keep_string=", ".join(csv_config.columns_to_keep) if csv_config.columns_to_keep else "",
        )
        return render_template(
            "db_selection/settings.html",
            assembly=assembly,
            csv_config=csv_config,
            form=form,
            current_tab="db_selection",
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/settings", methods=["POST"])
@login_required
@require_assembly_management
def save_db_selection_settings(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        form = DbSelectionSettingsForm()
        if form.validate_on_submit():
            uow = bootstrap.bootstrap()
            update_csv_config(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                selection_algorithm="maximin",
                check_same_address=form.check_same_address.data or False,
                check_same_address_cols=_parse_comma_list(form.check_same_address_cols_string.data),
                columns_to_keep=_parse_comma_list(form.columns_to_keep_string.data),
            )
            flash(_("Selection settings saved"), "success")
            return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))

        # Re-render with validation errors
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)
        return render_template(
            "db_selection/settings.html",
            assembly=assembly,
            csv_config=csv_config,
            form=form,
            current_tab="db_selection",
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_replace", methods=["GET"])
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


def _parse_comma_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
