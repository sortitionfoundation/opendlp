"""ABOUTME: Routes behind the project details page: the values edited in place, and its team
ABOUTME: Each answers htmx with the piece of the page it changed, and a plain request with a redirect"""

import uuid

import structlog
from flask import Blueprint, abort, flash, redirect, render_template, render_template_string, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.entrypoints.decorators import require_assembly_management
from opendlp.entrypoints.forms import EditAssemblyForm
from opendlp.service_layer.assembly_service import get_assembly_with_permissions, update_assembly_reporting_changes
from opendlp.translations import gettext as _

project_details_bp = Blueprint("project_details", __name__)

logger = structlog.get_logger(__name__)

# The values of a project edited in place on its details page, each in a row
# of its own (templates/backoffice/project_details/_rows.html).
EDITABLE_FIELDS = ("title", "question", "number_to_select", "first_assembly_date")

# One row still open, as htmx swaps it in for the row on the page after a refusal.
_ROW_REFUSED = (
    '{% from "backoffice/project_details/_rows.html" import project_field_row %}'
    "{{ project_field_row(assembly, field, true, submitted=submitted, error=error) }}"
)


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _saved_message(field: str, targets_moved: bool) -> str:
    if field != "number_to_select":
        return _("Project details saved")
    if targets_moved:
        return _("Panel size saved. Target min and max recalculated.")
    return _("Panel size saved.")


@project_details_bp.route("/project/<uuid:assembly_id>/edit-field", methods=["POST"])
@login_required
@require_assembly_management
def edit_field(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Save one value of a project, edited in place on its details page.

    Each row posts its own value, named by `field`. Over htmx the answer is
    that row again: at rest with the saved value, with the flash, the time of
    the change and (for the title) the page heading sent out of band; or still
    open with the reason under the field (422). Without htmx a save goes back
    to the details page, and so does a refusal, with the reason flashed.
    """
    field = request.form.get("field", "")
    if field not in EDITABLE_FIELDS:
        abort(400)

    form = EditAssemblyForm()
    bound_field = form[field]
    error = ""
    if bound_field.validate(form):
        value = bound_field.data
        if field == "question":
            value = value or ""
        try:
            uow = bootstrap.get_flask_uow()
            with uow:
                assembly, changes = update_assembly_reporting_changes(
                    uow, assembly_id, current_user.id, **{field: value}
                )
                assembly = assembly.create_detached_copy()
        except Exception as e:
            logger.exception(
                "Edit project field error", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
            )
            error = _("An error occurred while updating the project")
        else:
            flash(_saved_message(field, bool(changes)), "success")
            if _is_htmx():
                return render_template(
                    "backoffice/project_details/_field_saved.html",
                    assembly=assembly,
                    field=field,
                    return_focus=request.form.get("return_focus") == "1",
                ), 200
            return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
    else:
        error = "\n".join(str(reason) for reason in bound_field.errors)

    if not _is_htmx():
        flash(error, "error")
        return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
    uow = bootstrap.get_flask_uow()
    with uow:
        stored = get_assembly_with_permissions(uow, assembly_id, current_user.id)
    return render_template_string(
        _ROW_REFUSED, assembly=stored, field=field, submitted=request.form.get(field, ""), error=error
    ), 422
