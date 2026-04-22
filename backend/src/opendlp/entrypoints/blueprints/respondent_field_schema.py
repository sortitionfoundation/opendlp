"""ABOUTME: Backoffice routes for managing a per-assembly respondent field schema
ABOUTME: View the schema, edit labels, move between groups, reorder, delete, initialise"""

import contextlib
import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.domain.respondent_field_schema import (
    GROUP_DISPLAY_ORDER,
    GROUP_LABELS,
    RespondentFieldGroup,
)
from opendlp.service_layer.assembly_service import (
    determine_data_source,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    get_tab_enabled_states,
)
from opendlp.service_layer.exceptions import (
    InsufficientPermissions,
    NotFoundError,
)
from opendlp.service_layer.respondent_field_schema_service import (
    FieldDefinitionConflictError,
    FieldDefinitionNotFoundError,
    delete_field,
    get_schema,
    get_schema_grouped,
    initialise_empty_schema,
    reorder_group,
    update_field,
)
from opendlp.translations import gettext as _

respondent_field_schema_bp = Blueprint("respondent_field_schema", __name__)


def _schema_page_redirect(assembly_id: uuid.UUID) -> ResponseReturnValue:
    return redirect(url_for("respondent_field_schema.view_schema", assembly_id=assembly_id))


def _parse_group(raw: str | None) -> RespondentFieldGroup | None:
    """Parse a submitted group value; returns None if empty or unrecognised."""
    if not raw:
        return None
    try:
        return RespondentFieldGroup(raw)
    except ValueError:
        return None


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema")
@login_required
def view_schema(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Display and edit the respondent field schema for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        uow_schema = bootstrap.bootstrap()
        grouped = get_schema_grouped(uow_schema, current_user.id, assembly_id)
        sections = [
            {
                "group": group,
                "label": GROUP_LABELS[group],
                "fields": grouped.get(group, []),
            }
            for group in GROUP_DISPLAY_ORDER
        ]
        schema_has_rows = any(section["fields"] for section in sections)

        # Reuse the assembly-tabs computed state so the tab bar renders correctly.
        # Both lookups are optional — a fresh assembly has neither.
        gsheet = None
        with contextlib.suppress(Exception):
            gsheet = get_assembly_gsheet(bootstrap.bootstrap(), assembly_id, current_user.id)
        csv_status = None
        with contextlib.suppress(Exception):
            csv_status = get_csv_upload_status(bootstrap.bootstrap(), current_user.id, assembly_id)
        data_source, _locked = determine_data_source(gsheet, csv_status, request.args.get("source", ""))
        targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(
            data_source, gsheet, csv_status
        )

        group_choices = [(group.value, GROUP_LABELS[group]) for group in GROUP_DISPLAY_ORDER]

        return render_template(
            "backoffice/respondent_field_schema/view.html",
            assembly=assembly,
            sections=sections,
            group_choices=group_choices,
            schema_has_rows=schema_has_rows,
            data_source=data_source,
            gsheet=gsheet,
            targets_enabled=targets_enabled,
            respondents_enabled=respondents_enabled,
            selection_enabled=selection_enabled,
        ), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema/initialise", methods=["POST"])
@login_required
def initialise_schema(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Seed an empty schema (fixed-field rows only) for registration-first assemblies."""
    try:
        uow = bootstrap.bootstrap()
        inserted = initialise_empty_schema(uow, current_user.id, assembly_id)
        if inserted:
            flash(_("Schema initialised with %(count)d fixed fields.", count=inserted), "success")
        else:
            flash(_("Schema already exists."), "info")
    except InsufficientPermissions:
        flash(_("You don't have permission to initialise the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/update",
    methods=["POST"],
)
@login_required
def update_field_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Update a field's display label and/or group."""
    label = request.form.get("label", "").strip() or None
    group = _parse_group(request.form.get("group"))

    if label is None and group is None:
        flash(_("No changes submitted."), "info")
        return _schema_page_redirect(assembly_id)

    try:
        uow = bootstrap.bootstrap()
        update_field(uow, current_user.id, assembly_id, field_id, label=label, group=group)
        flash(_("Field updated."), "success")
    except FieldDefinitionNotFoundError:
        flash(_("Field not found."), "error")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/move",
    methods=["POST"],
)
@login_required
def move_field(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Shift a field up or down one slot within its group.

    Accepts a ``direction`` form field of ``"up"`` or ``"down"``. Reuses the
    service-layer ``reorder_group`` to re-issue sort_orders atomically.
    """
    direction = request.form.get("direction", "")
    if direction not in {"up", "down"}:
        flash(_("Invalid move direction."), "error")
        return _schema_page_redirect(assembly_id)

    try:
        uow = bootstrap.bootstrap()
        fields = get_schema(uow, current_user.id, assembly_id)
        target = next((f for f in fields if f.id == field_id), None)
        if target is None:
            flash(_("Field not found."), "error")
            return _schema_page_redirect(assembly_id)

        same_group = [f for f in fields if f.group == target.group]
        index = next(i for i, f in enumerate(same_group) if f.id == field_id)
        swap_with = index - 1 if direction == "up" else index + 1
        if swap_with < 0 or swap_with >= len(same_group):
            # Already at the top/bottom — silent no-op rather than a flash.
            return _schema_page_redirect(assembly_id)

        new_order = same_group[:]
        new_order[index], new_order[swap_with] = new_order[swap_with], new_order[index]
        uow_reorder = bootstrap.bootstrap()
        reorder_group(
            uow_reorder,
            current_user.id,
            assembly_id,
            target.group,
            [f.id for f in new_order],
        )
    except InsufficientPermissions:
        flash(_("You don't have permission to reorder fields"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/delete",
    methods=["POST"],
)
@login_required
def delete_field_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Delete a non-fixed field from the schema. Fixed fields are protected by the service layer."""
    try:
        uow = bootstrap.bootstrap()
        delete_field(uow, current_user.id, assembly_id, field_id)
        flash(_("Field removed."), "success")
    except FieldDefinitionConflictError as e:
        flash(str(e), "error")
    except FieldDefinitionNotFoundError:
        flash(_("Field not found."), "error")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)
