"""ABOUTME: Main application routes for dashboard and assembly listing
ABOUTME: Handles home page, dashboard, and assembly views with login requirements"""

import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required
from sortition_algorithms.features import maximum_selection, minimum_selection

from opendlp import bootstrap
from opendlp.entrypoints.decorators import require_assembly_management
from opendlp.service_layer.assembly_service import (
    add_assembly_gsheet,
    create_assembly,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    remove_assembly_gsheet,
    update_assembly,
    update_assembly_gsheet,
)
from opendlp.service_layer.exceptions import InsufficientPermissions
from opendlp.service_layer.sortition import (
    LoadRunResult,
    get_selection_run_status,
    start_gsheet_load_task,
    start_gsheet_replace_load_task,
    start_gsheet_replace_task,
    start_gsheet_select_task,
)
from opendlp.service_layer.user_service import get_user_assemblies
from opendlp.translations import gettext as _

from ..forms import CreateAssemblyForm, CreateAssemblyGSheetForm, EditAssemblyForm, EditAssemblyGSheetForm

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index() -> ResponseReturnValue:
    """Home page - redirects to dashboard if logged in, otherwise shows landing page."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("main/index.html"), 200


@main_bp.route("/dashboard")
@login_required
def dashboard() -> ResponseReturnValue:
    """User dashboard showing accessible assemblies."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assemblies = get_user_assemblies(uow, current_user.id)

        return render_template("main/dashboard.html", assemblies=assemblies), 200
    except Exception as e:
        current_app.logger.error(f"Dashboard error for user {current_user.id}: {e}")
        return render_template("errors/500.html"), 500


@main_bp.route("/assemblies/<uuid:assembly_id>")
@login_required
def view_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """View a single assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)

        return render_template("main/view_assembly.html", assembly=assembly, gsheet=gsheet), 200
    except ValueError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        # TODO: consider change to "Assembly not found" so as not to leak info
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View assembly error for assembly {assembly_id} user {current_user.id}: {e}")
        return render_template("errors/500.html"), 500


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet", methods=["GET", "POST"])
@login_required
def manage_assembly_gsheet(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Create or edit Google Spreadsheet configuration for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            existing_gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)

        # Choose form based on whether gsheet exists
        if existing_gsheet:
            form = EditAssemblyGSheetForm(obj=existing_gsheet)
            template = "main/edit_assembly_gsheet.html"
            action = "edit"
        else:
            form = CreateAssemblyGSheetForm()
            template = "main/create_assembly_gsheet.html"
            action = "create"

        if form.validate_on_submit():
            try:
                if action == "create":
                    add_assembly_gsheet(
                        uow=uow,
                        assembly_id=assembly_id,
                        user_id=current_user.id,
                        url=form.url.data,  # type: ignore[arg-type]
                        team=form.team.data,
                        select_registrants_tab=form.select_registrants_tab.data,
                        select_targets_tab=form.select_targets_tab.data,
                        replace_registrants_tab=form.replace_registrants_tab.data,
                        replace_targets_tab=form.replace_targets_tab.data,
                        id_column=form.id_column.data,
                        check_same_address=form.check_same_address.data,
                        generate_remaining_tab=form.generate_remaining_tab.data,
                        check_same_address_cols_string=form.check_same_address_cols_string.data,
                        columns_to_keep_string=form.columns_to_keep_string.data,
                    )
                    flash(_("Google Spreadsheet configuration created successfully"), "success")
                else:
                    update_assembly_gsheet(
                        uow=uow,
                        assembly_id=assembly_id,
                        user_id=current_user.id,
                        url=form.url.data,
                        team=form.team.data,
                        select_registrants_tab=form.select_registrants_tab.data,
                        select_targets_tab=form.select_targets_tab.data,
                        replace_registrants_tab=form.replace_registrants_tab.data,
                        replace_targets_tab=form.replace_targets_tab.data,
                        id_column=form.id_column.data,
                        check_same_address=form.check_same_address.data,
                        generate_remaining_tab=form.generate_remaining_tab.data,
                        check_same_address_cols_string=form.check_same_address_cols_string.data,
                        columns_to_keep_string=form.columns_to_keep_string.data,
                    )
                    flash(_("Google Spreadsheet configuration updated successfully"), "success")

                return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
            except InsufficientPermissions as e:
                current_app.logger.warning(
                    f"Insufficient permissions to {action} gsheet for assembly {assembly_id} by user {current_user.id}: {e}"
                )
                flash(_("You don't have permission to manage Google Spreadsheet for this assembly"), "error")
                return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
            except ValueError as e:
                current_app.logger.error(
                    f"Gsheet {action} validation error for assembly {assembly_id} user {current_user.id}: {e}"
                )
                flash(_("Please check your input and try again"), "error")
            except Exception as e:
                current_app.logger.error(
                    f"Gsheet {action} error for assembly {assembly_id} user {current_user.id}: {e}"
                )
                flash(_("An error occurred while saving the Google Spreadsheet configuration"), "error")

        return render_template(template, form=form, assembly=assembly, gsheet=existing_gsheet), 200
    except ValueError as e:
        current_app.logger.warning(
            f"Assembly {assembly_id} not found for gsheet management by user {current_user.id}: {e}"
        )
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to view assembly {assembly_id} for gsheet management by user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Gsheet management page error for assembly {assembly_id} user {current_user.id}: {e}")
        return render_template("errors/500.html"), 500


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet/delete", methods=["POST"])
@login_required
def delete_assembly_gsheet(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Remove Google Spreadsheet configuration from an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            remove_assembly_gsheet(uow, assembly_id, current_user.id)

        flash(_("Google Spreadsheet configuration removed successfully"), "success")
        return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
    except ValueError as e:
        current_app.logger.warning(f"Assembly or gsheet not found for deletion by user {current_user.id}: {e}")
        flash(_("Google Spreadsheet configuration not found"), "error")
        return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to delete gsheet for assembly {assembly_id} by user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to manage Google Spreadsheet for this assembly"), "error")
        return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Gsheet deletion error for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("An error occurred while removing the Google Spreadsheet configuration"), "error")
        return redirect(url_for("main.view_assembly", assembly_id=assembly_id))


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet_select", methods=["GET"])
@login_required
@require_assembly_management
def select_assembly_gsheet(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Display Google Sheets selection page for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)

        return render_template("main/gsheet_select.html", assembly=assembly, gsheet=gsheet), 200
    except ValueError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for selection by user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions for assembly {assembly_id} selection user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Selection page error for assembly {assembly_id} user {current_user.id}: {e}")
        return render_template("errors/500.html"), 500


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet_select/<uuid:run_id>", methods=["GET"])
@login_required
@require_assembly_management
def select_assembly_gsheet_with_run(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Display Google Sheets selection page with task status for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)
            result = get_selection_run_status(uow, run_id)

        # Validate that the run belongs to this assembly
        if result.run_record and result.run_record.assembly_id != assembly_id:
            current_app.logger.warning(
                f"Run {run_id} does not belong to assembly {assembly_id} - user {current_user.id}"
            )
            flash(_("Invalid task ID for this assembly"), "error")
            return redirect(url_for("main.select_assembly_gsheet", assembly_id=assembly_id))

        return render_template(
            "main/gsheet_select.html",
            assembly=assembly,
            gsheet=gsheet,
            run_record=result.run_record,
            celery_log_messages=result.log_messages,
            run_report=result.run_report,
            run_id=run_id,
        ), 200
    except ValueError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for selection by user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions for assembly {assembly_id} selection user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Selection page error for assembly {assembly_id} user {current_user.id}: {e}")
        return render_template("errors/500.html"), 500


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet_select/<uuid:run_id>/progress", methods=["GET"])
@login_required
@require_assembly_management
def gsheet_select_progress(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Return progress fragment for HTMX polling of Google Sheets selection task status."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)
            result = get_selection_run_status(uow, run_id)

        # Check if run record exists
        if not result.run_record:
            current_app.logger.warning(f"Run {run_id} not found for progress polling by user {current_user.id}")
            return "", 404

        # Validate that the run belongs to this assembly
        if result.run_record.assembly_id != assembly_id:
            current_app.logger.warning(
                f"Run {run_id} does not belong to assembly {assembly_id} - user {current_user.id}"
            )
            # Return empty response for HTMX to handle gracefully
            return "", 404

        response = current_app.make_response((
            render_template(
                "main/components/gsheet_select_progress.html",
                assembly=assembly,
                gsheet=gsheet,
                run_record=result.run_record,
                celery_log_messages=result.log_messages,
                run_report=result.run_report,
                run_id=run_id,
                progress_url=url_for("main.gsheet_select_progress", assembly_id=assembly_id, run_id=run_id),
            ),
            200,
        ))
        # if it has finished, force a full page refresh
        if result.run_record.has_finished:
            response.headers["HX-Refresh"] = "true"
        return response
    except ValueError as e:
        current_app.logger.warning(
            f"Assembly {assembly_id} not found for progress polling by user {current_user.id}: {e}"
        )
        return "", 404
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions for assembly {assembly_id} progress polling user {current_user.id}: {e}"
        )
        return "", 403
    except Exception as e:
        current_app.logger.error(f"Progress polling error for assembly {assembly_id} user {current_user.id}: {e}")
        return "", 500


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet_select", methods=["POST"])
@login_required
@require_assembly_management
def start_gsheet_select(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a Google Sheets loading task for an assembly."""
    # the form has a hidden parameter
    test_selection = request.form.get("test_selection") == "1"
    try:
        uow = bootstrap.bootstrap()
        with uow:
            # TODO: set number_people_wanted properly
            task_id = start_gsheet_select_task(uow, current_user.id, assembly_id, test_selection=test_selection)

        return redirect(url_for("main.select_assembly_gsheet_with_run", assembly_id=assembly_id, run_id=task_id))

    except ValueError as e:
        current_app.logger.warning(f"Failed to start gsheet select for assembly {assembly_id}: {e}")
        flash(_("Failed to start selection task: %(error)s", error=str(e)), "error")
        return redirect(url_for("main.select_assembly_gsheet", assembly_id=assembly_id))

    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions for starting gsheet select {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("main.dashboard"))

    except Exception as e:
        current_app.logger.error(f"Error starting gsheet select for assembly {assembly_id}: {e}")
        flash(_("An unexpected error occurred while starting the selection task"), "error")
        return redirect(url_for("main.select_assembly_gsheet", assembly_id=assembly_id))


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet_load", methods=["POST"])
@login_required
@require_assembly_management
def start_gsheet_load(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a Google Sheets loading task for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            task_id = start_gsheet_load_task(uow, current_user.id, assembly_id)

        return redirect(url_for("main.select_assembly_gsheet_with_run", assembly_id=assembly_id, run_id=task_id))

    except ValueError as e:
        current_app.logger.warning(f"Failed to start gsheet load for assembly {assembly_id}: {e}")
        flash(_("Failed to start loading task: %(error)s", error=str(e)), "error")
        return redirect(url_for("main.select_assembly_gsheet", assembly_id=assembly_id))

    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions for starting gsheet load {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("main.dashboard"))

    except Exception as e:
        current_app.logger.error(f"Error starting gsheet load for assembly {assembly_id}: {e}")
        flash(_("An unexpected error occurred while starting the loading task"), "error")
        return redirect(url_for("main.select_assembly_gsheet", assembly_id=assembly_id))


@main_bp.route("/assemblies/new", methods=["GET", "POST"])
@login_required
def create_assembly_page() -> ResponseReturnValue:
    """Create a new assembly."""
    form = CreateAssemblyForm()

    if form.validate_on_submit():
        try:
            uow = bootstrap.bootstrap()
            with uow:
                # ignoring warning for title - it will not be None due to form validation
                assembly = create_assembly(
                    uow=uow,
                    title=form.title.data,  # type: ignore[arg-type]
                    created_by_user_id=current_user.id,
                    question=form.question.data or "",
                    first_assembly_date=form.first_assembly_date.data,
                    number_to_select=form.number_to_select.data,
                )

            flash(_("Assembly '%(title)s' created successfully", title=assembly.title), "success")
            return redirect(url_for("main.view_assembly", assembly_id=assembly.id))
        except InsufficientPermissions as e:
            current_app.logger.warning(f"Insufficient permissions to create assembly for user {current_user.id}: {e}")
            flash(_("You don't have permission to create assemblies"), "error")
            return redirect(url_for("main.dashboard"))
        except ValueError as e:
            current_app.logger.error(f"Create assembly validation error for user {current_user.id}: {e}")
            flash(_("Please check your input and try again"), "error")
        except Exception as e:
            current_app.logger.error(f"Create assembly error for user {current_user.id}: {e}")
            flash(_("An error occurred while creating the assembly"), "error")

    return render_template("main/create_assembly.html", form=form), 200


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet_replace", methods=["GET"])
@login_required
@require_assembly_management
def replace_assembly_gsheet(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Display Google Sheets replacement selection page for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)

        return render_template("main/gsheet_replace.html", assembly=assembly, gsheet=gsheet), 200
    except ValueError as e:
        current_app.logger.warning(
            f"Assembly {assembly_id} not found for replacement selection by user {current_user.id}: {e}"
        )
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions for assembly {assembly_id} replacement selection user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(
            f"Replacement selection page error for assembly {assembly_id} user {current_user.id}: {e}"
        )
        return render_template("errors/500.html"), 500


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet_replace/<uuid:run_id>", methods=["GET"])
@login_required
@require_assembly_management
def replace_assembly_gsheet_with_run(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Display Google Sheets replacement selection page with task status for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)
            result = get_selection_run_status(uow, run_id)

        # Validate that the run belongs to this assembly
        if result.run_record and result.run_record.assembly_id != assembly_id:
            current_app.logger.warning(
                f"Run {run_id} does not belong to assembly {assembly_id} - user {current_user.id}"
            )
            flash(_("Invalid task ID for this assembly"), "error")
            return redirect(url_for("main.replace_assembly_gsheet", assembly_id=assembly_id))

        # Initialize query param variables
        min_select: int | None = None
        max_select: int | None = None
        num_to_select: int | None = None

        # Check if we already have min_select and max_select in query params
        # Check if this is a completed load task with features - if so, redirect with min/max params
        if (
            "min_select" not in request.args
            and isinstance(result, LoadRunResult)
            and result.features is not None
            and result.success
        ):
            # Calculate min and max selection bounds
            min_select = minimum_selection(result.features)
            max_select = maximum_selection(result.features)

            # Redirect to same URL with query params
            return redirect(
                url_for(
                    "main.replace_assembly_gsheet_with_run",
                    assembly_id=assembly_id,
                    run_id=run_id,
                    min_select=min_select,
                    max_select=max_select,
                )
            )

        # Get query params for template (if we didn't redirect above)
        min_select = request.args.get("min_select", type=int)
        max_select = request.args.get("max_select", type=int)
        num_to_select = request.args.get("num_to_select", type=int)

        return render_template(
            "main/gsheet_replace.html",
            assembly=assembly,
            gsheet=gsheet,
            run_record=result.run_record,
            celery_log_messages=result.log_messages,
            run_report=result.run_report,
            run_id=run_id,
            min_select=min_select,
            max_select=max_select,
            num_to_select=num_to_select,
        ), 200
    except ValueError as e:
        current_app.logger.warning(
            f"Assembly {assembly_id} not found for replacement selection by user {current_user.id}: {e}"
        )
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions for assembly {assembly_id} replacement selection user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(
            f"Replacement selection page error for assembly {assembly_id} user {current_user.id}: {e}"
        )
        return render_template("errors/500.html"), 500


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet_replace/<uuid:run_id>/progress", methods=["GET"])
@login_required
@require_assembly_management
def gsheet_replace_progress(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Return progress fragment for HTMX polling of Google Sheets replacement task status."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)
            result = get_selection_run_status(uow, run_id)

        # Check if run record exists
        if not result.run_record:
            current_app.logger.warning(f"Run {run_id} not found for progress polling by user {current_user.id}")
            return "", 404

        # Validate that the run belongs to this assembly
        if result.run_record.assembly_id != assembly_id:
            current_app.logger.warning(
                f"Run {run_id} does not belong to assembly {assembly_id} - user {current_user.id}"
            )
            # Return empty response for HTMX to handle gracefully
            return "", 404

        # If load task completed successfully, redirect to add query params with min/max
        if isinstance(result, LoadRunResult) and result.features is not None and result.success:
            # Calculate min and max selection bounds
            min_select = minimum_selection(result.features)
            max_select = maximum_selection(result.features)

            # Return HX-Redirect header to trigger client-side redirect
            redirect_url = url_for(
                "main.replace_assembly_gsheet_with_run",
                assembly_id=assembly_id,
                run_id=run_id,
                min_select=min_select,
                max_select=max_select,
            )
            response = current_app.make_response("")
            response.headers["HX-Redirect"] = redirect_url
            return response

        response = current_app.make_response((
            render_template(
                "main/components/gsheet_select_progress.html",
                assembly=assembly,
                gsheet=gsheet,
                run_record=result.run_record,
                celery_log_messages=result.log_messages,
                run_report=result.run_report,
                run_id=run_id,
                progress_url=url_for("main.gsheet_replace_progress", assembly_id=assembly_id, run_id=run_id),
            ),
            200,
        ))
        # if it has finished, force a full page refresh
        if result.run_record.has_finished:
            response.headers["HX-Refresh"] = "true"
        return response
    except ValueError as e:
        current_app.logger.warning(
            f"Assembly {assembly_id} not found for progress polling by user {current_user.id}: {e}"
        )
        return "", 404
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions for assembly {assembly_id} progress polling user {current_user.id}: {e}"
        )
        return "", 403
    except Exception as e:
        current_app.logger.error(f"Progress polling error for assembly {assembly_id} user {current_user.id}: {e}")
        return "", 500


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet_replace_load", methods=["POST"])
@login_required
@require_assembly_management
def start_gsheet_replace_load(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a Google Sheets replacement data loading task for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            task_id = start_gsheet_replace_load_task(uow, current_user.id, assembly_id)

        return redirect(url_for("main.replace_assembly_gsheet_with_run", assembly_id=assembly_id, run_id=task_id))

    except ValueError as e:
        current_app.logger.warning(f"Failed to start gsheet replacement load for assembly {assembly_id}: {e}")
        flash(_("Failed to start loading task: %(error)s", error=str(e)), "error")
        return redirect(url_for("main.replace_assembly_gsheet", assembly_id=assembly_id))

    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions for starting gsheet replacement load {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("main.dashboard"))

    except Exception as e:
        current_app.logger.error(f"Error starting gsheet replacement load for assembly {assembly_id}: {e}")
        flash(_("An unexpected error occurred while starting the loading task"), "error")
        return redirect(url_for("main.replace_assembly_gsheet", assembly_id=assembly_id))


@main_bp.route("/assemblies/<uuid:assembly_id>/gsheet_replace", methods=["POST"])
@login_required
@require_assembly_management
def start_gsheet_replace(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a Google Sheets replacement selection task for an assembly."""
    try:
        # Get and validate number_to_select from form
        number_to_select_str = request.form.get("number_to_select")
        if not number_to_select_str:
            flash(_("Number of people to select is required"), "error")
            return redirect(url_for("main.replace_assembly_gsheet", assembly_id=assembly_id))

        try:
            number_to_select = int(number_to_select_str)
            if number_to_select <= 0:
                flash(_("Number of people to select must be greater than zero"), "error")
                return redirect(url_for("main.replace_assembly_gsheet", assembly_id=assembly_id))
        except ValueError:
            flash(_("Number of people to select must be a valid integer"), "error")
            return redirect(url_for("main.replace_assembly_gsheet", assembly_id=assembly_id))

        uow = bootstrap.bootstrap()
        with uow:
            task_id = start_gsheet_replace_task(uow, current_user.id, assembly_id, number_to_select)

        return redirect(
            url_for(
                "main.replace_assembly_gsheet_with_run",
                assembly_id=assembly_id,
                run_id=task_id,
                num_to_select=number_to_select,
            )
        )

    except ValueError as e:
        current_app.logger.warning(f"Failed to start gsheet replacement for assembly {assembly_id}: {e}")
        flash(_("Failed to start replacement task: %(error)s", error=str(e)), "error")
        return redirect(url_for("main.replace_assembly_gsheet", assembly_id=assembly_id))

    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions for starting gsheet replacement {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("main.dashboard"))

    except Exception as e:
        current_app.logger.error(f"Error starting gsheet replacement for assembly {assembly_id}: {e}")
        flash(_("An unexpected error occurred while starting the replacement task"), "error")
        return redirect(url_for("main.replace_assembly_gsheet", assembly_id=assembly_id))


@main_bp.route("/assemblies/<uuid:assembly_id>/edit", methods=["GET", "POST"])
@login_required
def edit_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Edit an assembly."""
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
                return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
            except InsufficientPermissions as e:
                current_app.logger.warning(
                    f"Insufficient permissions to edit assembly {assembly_id} for user {current_user.id}: {e}"
                )
                flash(_("You don't have permission to edit this assembly"), "error")
                return redirect(url_for("main.view_assembly", assembly_id=assembly_id))
            except ValueError as e:
                current_app.logger.error(
                    f"Edit assembly validation error for assembly {assembly_id} user {current_user.id}: {e}"
                )
                flash(_("Please check your input and try again"), "error")
            except Exception as e:
                current_app.logger.error(f"Edit assembly error for assembly {assembly_id} user {current_user.id}: {e}")
                flash(_("An error occurred while updating the assembly"), "error")

        return render_template("main/edit_assembly.html", form=form, assembly=assembly), 200
    except ValueError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for edit by user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to view assembly {assembly_id} for edit by user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Edit assembly page error for assembly {assembly_id} user {current_user.id}: {e}")
        return render_template("errors/500.html"), 500
