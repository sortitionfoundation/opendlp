"""ABOUTME: Routes behind the project details page: the values edited in place, and its team
ABOUTME: Each answers htmx with the piece of the page it changed, and a plain request with a redirect"""

import uuid
from typing import Any

import structlog
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    render_template_string,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.bootstrap import get_email_adapter, get_template_renderer, get_url_generator
from opendlp.domain.assembly import Assembly
from opendlp.domain.value_objects import AssemblyRole, assembly_role_labels
from opendlp.entrypoints.decorators import require_assembly_management
from opendlp.entrypoints.forms import AddUserToAssemblyForm, ChangeAssemblyRoleForm, EditAssemblyForm
from opendlp.service_layer.assembly_service import get_assembly_with_permissions, update_assembly_reporting_changes
from opendlp.service_layer.exceptions import CannotRemoveLastAssemblyManager, NotFoundError
from opendlp.service_layer.permissions import can_manage_assembly_members
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.service_layer.user_service import (
    change_user_assembly_role,
    get_assembly_members,
    grant_user_assembly_role,
    sole_assembly_manager_id,
)
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


# --- The team ---------------------------------------------------------------


def team_card_context(uow: AbstractUnitOfWork, assembly: Assembly) -> dict[str, Any]:
    """What the Team card renders from.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    return {
        "team_members": get_assembly_members(uow, assembly.id, current_user),
        # Named so the card can hide a bin and a pencil that would be refused:
        # a non-admin may not leave the project with no manager.
        "sole_manager_id": sole_assembly_manager_id(uow, assembly.id),
        "can_manage_team": can_manage_assembly_members(current_user, assembly),
    }


def _team_changed(assembly_id: uuid.UUID, **dialog: Any) -> ResponseReturnValue:
    """The Team card as it now stands, out of band, with the dialog closed or (given a form) open again."""
    uow = bootstrap.get_flask_uow()
    with uow:
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
        context = team_card_context(uow, assembly)
    return render_template("backoffice/project_details/_team_changed.html", assembly=assembly, **context, **dialog), 200


def _details_url(assembly_id: uuid.UUID) -> str:
    return url_for("backoffice.view_assembly", assembly_id=assembly_id, _anchor="team")


def _dialog_response(template: str, assembly_id: uuid.UUID, status: int = 200, **context: Any) -> ResponseReturnValue:
    uow = bootstrap.get_flask_uow()
    with uow:
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
    return render_template(template, assembly=assembly, **context), status


@project_details_bp.route("/project/<uuid:assembly_id>/team/add", methods=["GET", "POST"])
@login_required
@require_assembly_management
def add_team_member(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Add someone to the project's team, in a dialog over the details page.

    Over htmx a GET answers with the dialog. A POST that adds someone answers
    with an empty dialog host, which closes it, or - asked with ?again=1 - with
    the dialog again, empty and saying who was added; either way the Team card
    and the flash come out of band. A refusal is the dialog with the reason
    (422). Without htmx everything goes back to the details page.
    """
    if not _is_htmx() and request.method == "GET":
        return redirect(_details_url(assembly_id))

    form = AddUserToAssemblyForm()
    template = "backoffice/project_details/_team_add_dialog.html"
    if request.method == "GET":
        return _dialog_response(template, assembly_id, form=AddUserToAssemblyForm(formdata=None))

    form_error = ""
    if form.validate():
        role = form.role.data
        assert isinstance(role, AssemblyRole)
        try:
            uow = bootstrap.get_flask_uow()
            with uow:
                _assembly_role, added = grant_user_assembly_role(
                    uow=uow,
                    user_id=uuid.UUID(form.user_id.data),
                    assembly_id=assembly_id,
                    role=role,
                    current_user=current_user,
                    email_adapter=get_email_adapter(),
                    template_renderer=get_template_renderer(current_app),
                    url_generator=get_url_generator(current_app),
                )
        except (ValueError, NotFoundError) as e:
            logger.warning("Could not add team member", assembly_id=str(assembly_id), error=str(e))
            form.user_id.errors = [_("Choose a user from the list")]
        except Exception as e:
            logger.exception(
                "Unexpected error adding team member",
                assembly_id=str(assembly_id),
                user_id=str(current_user.id),
                error=str(e),
            )
            form_error = _("An error occurred while adding the user to the project")
        else:
            if not _is_htmx():
                flash(_added_message(added.display_name, role), "success")
                return redirect(_details_url(assembly_id))
            if request.args.get("again") == "1":
                return _team_changed(
                    assembly_id, form=AddUserToAssemblyForm(formdata=None), just_added=added.display_name
                )
            flash(_added_message(added.display_name, role), "success")
            return _team_changed(assembly_id)

    if not _is_htmx():
        flash(form_error or _("Please select a user and role"), "error")
        return redirect(_details_url(assembly_id))
    return _dialog_response(template, assembly_id, status=422, form=form, form_error=form_error)


def _added_message(name: str, role: AssemblyRole) -> str:
    return _("%(user)s added to project with role %(role)s", user=name, role=assembly_role_labels[role])


@project_details_bp.route("/project/<uuid:assembly_id>/team/<uuid:user_id>/role", methods=["GET", "POST"])
@login_required
@require_assembly_management
def change_team_role(assembly_id: uuid.UUID, user_id: uuid.UUID) -> ResponseReturnValue:
    """Change the role one person has on the project, in a dialog over the details page.

    Over htmx a GET answers with the dialog; a change with an empty dialog
    host, which closes it, and the Team card and the flash out of band; a
    refusal with the dialog and the reason (422). Without htmx everything goes
    back to the details page.
    """
    if not _is_htmx() and request.method == "GET":
        return redirect(_details_url(assembly_id))

    uow = bootstrap.get_flask_uow()
    with uow:
        member = uow.users.get(user_id)
        current_role = member.get_assembly_role(assembly_id) if member else None
        if member is None or current_role is None:
            abort(404)
        member = member.create_detached_copy()

    template = "backoffice/project_details/_team_role_dialog.html"
    if request.method == "GET":
        return _dialog_response(
            template, assembly_id, member=member, form=ChangeAssemblyRoleForm(formdata=None, role=current_role.name)
        )

    form = ChangeAssemblyRoleForm()
    form_error = ""
    if form.validate():
        role = form.role.data
        assert isinstance(role, AssemblyRole)
        try:
            with uow:
                change_user_assembly_role(
                    uow=uow, user_id=user_id, assembly_id=assembly_id, role=role, current_user=current_user
                )
        except CannotRemoveLastAssemblyManager as e:
            logger.warning(
                "Refused to leave assembly without a manager",
                assembly_id=str(assembly_id),
                user_id=str(current_user.id),
            )
            form_error = e.user_msg()
        except Exception as e:
            logger.exception(
                "Unexpected error changing a team role",
                assembly_id=str(assembly_id),
                user_id=str(current_user.id),
                error=str(e),
            )
            form_error = _("An error occurred while changing the role")
        else:
            flash(
                _("%(user)s is now %(role)s", user=member.display_name, role=assembly_role_labels[role]),
                "success",
            )
            if not _is_htmx():
                return redirect(_details_url(assembly_id))
            return _team_changed(assembly_id)

    if not _is_htmx():
        flash(form_error or _("Please select a role"), "error")
        return redirect(_details_url(assembly_id))
    return _dialog_response(template, assembly_id, status=422, member=member, form=form, form_error=form_error)
