"""ABOUTME: Respondents blueprint for viewing and uploading respondents via CSV
ABOUTME: Provides routes for assembly-level respondent management with pagination"""

import math
import uuid
from datetime import UTC, datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer.assembly_service import (
    get_assembly_with_permissions,
    update_csv_config,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection, NotFoundError
from opendlp.service_layer.respondent_service import import_respondents_from_csv, reset_selection_status
from opendlp.translations import gettext as _

from ..forms import UploadRespondentsCsvForm

respondents_bp = Blueprint("respondents", __name__)

PER_PAGE = 50


@respondents_bp.route("/assemblies/<uuid:assembly_id>/respondents")
@login_required
def view_assembly_respondents(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        status_filter_str = request.args.get("status", "")
        status_filter: RespondentStatus | None = None
        if status_filter_str:
            try:
                status_filter = RespondentStatus(status_filter_str)
            except ValueError:
                status_filter = None

        uow2 = bootstrap.bootstrap()
        with uow2:
            all_respondents = uow2.respondents.get_by_assembly_id(assembly_id, status=status_filter)
            total_count = len(all_respondents)
            available_count = uow2.respondents.count_available_for_selection(assembly_id)

            page = request.args.get("page", 1, type=int)
            page = max(1, page)
            total_pages = max(1, math.ceil(total_count / PER_PAGE))
            page = min(page, total_pages)

            start = (page - 1) * PER_PAGE
            end = start + PER_PAGE
            respondents = [r.create_detached_copy() for r in all_respondents[start:end]]

        form = UploadRespondentsCsvForm()
        if assembly.csv and assembly.csv.id_column:
            form.id_column.data = assembly.csv.id_column

        return render_template(
            "respondents/view_respondents.html",
            assembly=assembly,
            respondents=respondents,
            total_count=total_count,
            available_count=available_count,
            form=form,
            page=page,
            per_page=PER_PAGE,
            total_pages=total_pages,
            current_tab="respondents",
            status_filter=status_filter_str,
        )

    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error viewing respondents for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An unexpected error occurred"), "error")
        return redirect(url_for("main.dashboard"))


@respondents_bp.route("/assemblies/<uuid:assembly_id>/respondents/upload", methods=["POST"])
@login_required
def upload_respondents_csv(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        form = UploadRespondentsCsvForm()

        if not form.validate_on_submit():
            uow = bootstrap.bootstrap()
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

            uow2 = bootstrap.bootstrap()
            with uow2:
                all_respondents = uow2.respondents.get_by_assembly_id(assembly_id)
                total_count = len(all_respondents)
                available_count = uow2.respondents.count_available_for_selection(assembly_id)

            return render_template(
                "respondents/view_respondents.html",
                assembly=assembly,
                respondents=[],
                total_count=total_count,
                available_count=available_count,
                form=form,
                page=1,
                per_page=PER_PAGE,
                total_pages=1,
                current_tab="respondents",
            ), 200

        csv_file = form.csv_file.data
        csv_content = csv_file.read().decode("utf-8-sig")
        filename = csv_file.filename or "unknown.csv"

        id_column = form.id_column.data.strip() if form.id_column.data else None

        uow = bootstrap.bootstrap()
        respondents, errors = import_respondents_from_csv(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            csv_content=csv_content,
            replace_existing=form.replace_existing.data or False,
            id_column=id_column if id_column else None,
        )

        uow2 = bootstrap.bootstrap()
        update_csv_config(
            uow=uow2,
            user_id=current_user.id,
            assembly_id=assembly_id,
            last_import_filename=filename,
            last_import_timestamp=datetime.now(UTC),
        )

        msg = _("Successfully imported %(count)s respondents from %(file)s", count=len(respondents), file=filename)
        flash(msg, "success")

        if errors:
            error_summary = "; ".join(errors[:10])
            if len(errors) > 10:
                error_summary += _(" ... and %(more)s more", more=len(errors) - 10)
            flash(
                _("%(count)s rows were skipped: %(errors)s", count=len(errors), errors=error_summary),
                "warning",
            )

        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))

    except InvalidSelection as e:
        current_app.logger.warning(f"Invalid respondents CSV for assembly {assembly_id}: {e}")
        flash(_("CSV import failed: %(error)s", error=str(e)), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to import respondents"), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
    except UnicodeDecodeError:
        flash(_("Could not read CSV file. Please ensure it is UTF-8 encoded."), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Upload respondents error for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An unexpected error occurred during import"), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))


@respondents_bp.route("/assemblies/<uuid:assembly_id>/respondents/reset-status", methods=["POST"])
@login_required
def reset_respondent_status(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        count = reset_selection_status(uow, current_user.id, assembly_id)
        flash(_("Reset %(count)s respondents to Pool status", count=count), "success")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to reset selection status"), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Reset respondent status error for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An unexpected error occurred"), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
