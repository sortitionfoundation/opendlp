"""ABOUTME: Backoffice routes for CRUD operations on assembly respondents
ABOUTME: Provides respondent viewing, CSV upload, and deletion under /backoffice/assembly/*/respondents"""

import uuid
from datetime import UTC, datetime
from typing import Any

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.config import get_max_csv_upload_bytes, get_max_csv_upload_mb
from opendlp.domain.respondent_field_schema import CHOICE_TYPES, GROUP_DISPLAY_ORDER, GROUP_LABELS, FieldType
from opendlp.domain.respondents import _UNSET as _RESPONDENT_UNSET
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentStatus
from opendlp.entrypoints.edit_respondent_form import (
    ATTR_FIELD_PREFIX,
    build_edit_respondent_form,
    radio_or_none_to_bool,
    radio_to_bool,
)
from opendlp.service_layer.assembly_service import (
    CSVUploadStatus,
    delete_respondents_for_assembly,
    determine_data_source,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    get_tab_enabled_states,
    update_csv_config,
)
from opendlp.service_layer.csv_upload_stash import StashedUpload
from opendlp.service_layer.csv_upload_stash import clear as clear_stashed_upload
from opendlp.service_layer.csv_upload_stash import fetch as fetch_stashed_upload
from opendlp.service_layer.csv_upload_stash import stash as stash_pending_upload
from opendlp.service_layer.exceptions import (
    InsufficientPermissions,
    InvalidSelection,
    NotFoundError,
    RespondentNotFoundError,
)
from opendlp.service_layer.permissions import can_edit_respondent, can_manage_assembly
from opendlp.service_layer.respondent_field_schema_service import (
    compute_diff_for_pending_csv,
    get_schema,
    get_schema_grouped,
)
from opendlp.service_layer.respondent_service import (
    delete_respondent,
    get_respondent,
    get_respondent_with_comment_authors,
    get_respondents_for_assembly_paginated,
    import_respondents_from_csv,
    update_respondent,
)
from opendlp.translations import gettext as _

respondents_bp = Blueprint("respondents", __name__)


def _run_csv_import(
    assembly_id: uuid.UUID,
    csv_content: str,
    filename: str,
    id_column: str | None,
    replace_existing: bool,
) -> ResponseReturnValue:
    """Apply a respondent CSV import and redirect back to the data tab.

    Shared by the immediate-upload path and the confirm-diff path so both
    flows emit the same flash messages and saved-config side effects.
    """
    uow = bootstrap.bootstrap()
    with uow:
        respondents, errors, resolved_id_column = import_respondents_from_csv(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            csv_content=csv_content,
            replace_existing=replace_existing,
            id_column=id_column,
        )

    uow2 = bootstrap.bootstrap()
    update_csv_config(
        uow=uow2,
        user_id=current_user.id,
        assembly_id=assembly_id,
        last_import_filename=filename,
        last_import_timestamp=datetime.now(UTC),
        csv_id_column=resolved_id_column,
    )

    if errors:
        flash(
            _(
                "Respondents uploaded with warnings: %(count)d imported, %(errors)d errors",
                count=len(respondents),
                errors=len(errors),
            ),
            "warning",
        )
    else:
        flash(
            _("Respondents uploaded successfully: %(count)d imported", count=len(respondents)),
            "success",
        )
    return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))


@respondents_bp.route("/assembly/<uuid:assembly_id>/data/upload-respondents", methods=["POST"])
@login_required
def upload_respondents_csv(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Receive a CSV upload, then either import directly or surface a diff."""
    try:
        if "file" not in request.files:
            flash(_("No file selected"), "error")
            return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

        file = request.files["file"]
        if file.filename == "":
            flash(_("No file selected"), "error")
            return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

        raw = file.read()
        max_bytes = get_max_csv_upload_bytes()
        if len(raw) > max_bytes:
            current_app.logger.warning(
                f"Rejected oversized CSV upload for assembly {assembly_id}: {len(raw)} bytes exceeds limit {max_bytes}"
            )
            flash(
                _(
                    "CSV is too large: limit is %(limit)d MB. Update MAX_CSV_UPLOAD_MB if a larger file is needed.",
                    limit=get_max_csv_upload_mb(),
                ),
                "error",
            )
            return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))
        csv_content = raw.decode("utf-8")

        id_column = request.form.get("id_column", "").strip() or None
        filename = file.filename or "unknown.csv"

        # If a schema already exists, compute the diff against the new headers.
        # When the diff has changes the organiser sees a confirmation page first;
        # otherwise we proceed straight to the import as before.
        uow_diff = bootstrap.bootstrap()
        diff = compute_diff_for_pending_csv(
            uow_diff,
            current_user.id,
            assembly_id,
            csv_content,
            id_column,
        )
        if diff is not None and diff.has_changes:
            stash_pending_upload(
                user_id=current_user.id,
                assembly_id=assembly_id,
                upload=StashedUpload(
                    csv_content=csv_content,
                    filename=filename,
                    id_column=id_column,
                    replace_existing=True,
                ),
            )
            return redirect(
                url_for("respondents.confirm_upload_diff", assembly_id=assembly_id),
                code=303,
            )

        return _run_csv_import(
            assembly_id=assembly_id,
            csv_content=csv_content,
            filename=filename,
            id_column=id_column,
            replace_existing=True,
        )

    except InvalidSelection as e:
        current_app.logger.warning(f"Invalid CSV format for respondents upload assembly {assembly_id}: {e}")
        flash(_("Invalid CSV format: %(error)s", error=str(e)), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to upload respondents for assembly {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to upload respondents"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for respondents upload: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Upload respondents error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while uploading respondents"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))


@respondents_bp.route("/assembly/<uuid:assembly_id>/data/upload-respondents/confirm-diff", methods=["GET"])
@login_required
def confirm_upload_diff(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Render the schema-diff confirmation page for a pending CSV upload."""
    pending = fetch_stashed_upload(user_id=current_user.id, assembly_id=assembly_id)
    if pending is None:
        flash(_("Upload session expired. Please upload the CSV again."), "warning")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

    try:
        uow_diff = bootstrap.bootstrap()
        diff = compute_diff_for_pending_csv(
            uow_diff,
            current_user.id,
            assembly_id,
            pending.csv_content,
            pending.id_column,
        )
    except InvalidSelection as e:
        flash(_("Invalid CSV format: %(error)s", error=str(e)), "error")
        clear_stashed_upload(user_id=current_user.id, assembly_id=assembly_id)
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

    # diff should not be None here — we only redirect to this page when the
    # schema exists. Defensive: if it is, treat as empty diff and proceed.
    if diff is None or not diff.has_changes:
        clear_stashed_upload(user_id=current_user.id, assembly_id=assembly_id)
        return _run_csv_import(
            assembly_id=assembly_id,
            csv_content=pending.csv_content,
            filename=pending.filename,
            id_column=pending.id_column,
            replace_existing=pending.replace_existing,
        )

    uow = bootstrap.bootstrap()
    with uow:
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

    new_keys_with_labels = [
        {"key": key, "group": group, "group_label": GROUP_LABELS.get(group, group.value)}
        for key, group in diff.new_keys
    ]
    return render_template(
        "backoffice/respondents/confirm_upload_diff.html",
        assembly=assembly,
        filename=pending.filename,
        diff=diff,
        new_keys_with_labels=new_keys_with_labels,
        max_csv_upload_mb=get_max_csv_upload_mb(),
    ), 200


@respondents_bp.route("/assembly/<uuid:assembly_id>/data/upload-respondents/confirm-diff", methods=["POST"])
@login_required
def apply_upload_diff(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Apply a previously-stashed CSV upload, or cancel it."""
    pending = fetch_stashed_upload(user_id=current_user.id, assembly_id=assembly_id)
    if pending is None:
        flash(_("Upload session expired. Please upload the CSV again."), "warning")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

    if request.form.get("action") == "cancel":
        clear_stashed_upload(user_id=current_user.id, assembly_id=assembly_id)
        flash(_("Upload cancelled."), "info")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

    try:
        response = _run_csv_import(
            assembly_id=assembly_id,
            csv_content=pending.csv_content,
            filename=pending.filename,
            id_column=pending.id_column,
            replace_existing=pending.replace_existing,
        )
    finally:
        clear_stashed_upload(user_id=current_user.id, assembly_id=assembly_id)
    return response


@respondents_bp.route("/assembly/<uuid:assembly_id>/data/delete-respondents", methods=["POST"])
@login_required
def delete_respondents(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Delete all respondents for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            count = delete_respondents_for_assembly(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )

        flash(_("Respondents deleted: %(count)d removed", count=count), "success")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to delete respondents for assembly {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to delete respondents"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for respondents deletion: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Delete respondents error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while deleting respondents"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))


@respondents_bp.route("/assembly/<uuid:assembly_id>/respondents")
@login_required
def view_assembly_respondents(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly respondents page."""
    try:
        # Get pagination parameters
        page = request.args.get("page", 1, type=int)
        per_page = 25

        # Get status filter - keep raw value for template, parse for service
        status_filter_str = request.args.get("status", "")
        status_filter = RespondentStatus.from_str(status_filter_str)

        # Get assembly with permissions
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

            # If filter string provided but not a valid enum, return empty results
            if status_filter_str and status_filter is None:
                respondents: list[Respondent] = []
                total_count = 0
            else:
                respondents, total_count = get_respondents_for_assembly_paginated(
                    uow,
                    user_id=current_user.id,
                    assembly_id=assembly_id,
                    page=page,
                    per_page=per_page,
                    status=status_filter,
                )
            viewer = uow.users.get(current_user.id)
            assembly_obj = uow.assemblies.get(assembly_id)
            can_edit = bool(viewer and assembly_obj and can_edit_respondent(viewer, assembly_obj))

        # Calculate pagination info
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

        # Determine data source and whether tabs should be enabled
        gsheet = None
        try:
            uow_gsheet = bootstrap.bootstrap()
            gsheet = get_assembly_gsheet(uow_gsheet, assembly_id, current_user.id)
        except Exception:  # noqa: S110
            pass  # No gsheet config exists - this is expected for new assemblies

        # Get CSV status
        csv_status: CSVUploadStatus | None = None
        try:
            uow_csv = bootstrap.bootstrap()
            csv_status = get_csv_upload_status(uow_csv, current_user.id, assembly_id)
        except Exception:  # noqa: S110
            pass  # No CSV data - expected for new assemblies

        # Determine data source
        data_source, _locked = determine_data_source(gsheet, csv_status, request.args.get("source", ""))

        # Tab enabled states
        targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(
            data_source, gsheet, csv_status
        )

        return render_template(
            "backoffice/assembly_respondents.html",
            assembly=assembly,
            respondents=respondents,
            data_source=data_source,
            gsheet=gsheet,
            targets_enabled=targets_enabled,
            respondents_enabled=respondents_enabled,
            selection_enabled=selection_enabled,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            total_count=total_count,
            status_filter=status_filter_str,
            can_edit=can_edit,
        ), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(
            f"View assembly respondents error for assembly {assembly_id} user {current_user.id}: {e}"
        )
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while loading assembly respondents"), "error")
        return redirect(url_for("backoffice.dashboard"))


@respondents_bp.route(
    "/assembly/<uuid:assembly_id>/respondents/<uuid:respondent_id>/delete",
    methods=["POST"],
)
@login_required
def delete_respondent_route(assembly_id: uuid.UUID, respondent_id: uuid.UUID) -> ResponseReturnValue:
    """Blank personal data for a respondent (GDPR right to be forgotten)."""
    comment = request.form.get("comment", "").strip()
    if not comment:
        flash(_("A comment is required when deleting a respondent"), "error")
        return redirect(url_for("respondents.view_respondent", assembly_id=assembly_id, respondent_id=respondent_id))
    try:
        uow = bootstrap.bootstrap()
        with uow:
            delete_respondent(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                respondent_id=respondent_id,
                comment=comment,
            )
        flash(_("Respondent personal data deleted"), "success")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to delete respondent {respondent_id} "
            f"in assembly {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to delete respondents"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except RespondentNotFoundError as e:
        current_app.logger.warning(f"Respondent {respondent_id} not found in assembly {assembly_id}: {e}")
        flash(_("Respondent not found"), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for respondent deletion: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Delete respondent error for respondent {respondent_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while deleting the respondent"), "error")
        return redirect(url_for("respondents.view_respondent", assembly_id=assembly_id, respondent_id=respondent_id))


@respondents_bp.route("/assembly/<uuid:assembly_id>/respondents/<uuid:respondent_id>")
@login_required
def view_respondent(assembly_id: uuid.UUID, respondent_id: uuid.UUID) -> ResponseReturnValue:
    """View one respondent"""
    try:
        # Get assembly with permissions
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            respondent, comment_authors = get_respondent_with_comment_authors(
                uow, current_user.id, assembly_id, respondent_id
            )
            viewer = uow.users.get(current_user.id)
            assembly_obj = uow.assemblies.get(assembly_id)
            can_manage = bool(viewer and assembly_obj and can_manage_assembly(viewer, assembly_obj))
            can_edit = bool(viewer and assembly_obj and can_edit_respondent(viewer, assembly_obj))

        # Determine data source and whether tabs should be enabled
        gsheet = None
        try:
            uow_gsheet = bootstrap.bootstrap()
            gsheet = get_assembly_gsheet(uow_gsheet, assembly_id, current_user.id)
        except Exception:  # noqa: S110
            pass  # No gsheet config exists - this is expected for new assemblies

        # Get CSV status
        csv_status: CSVUploadStatus | None = None
        try:
            uow_csv = bootstrap.bootstrap()
            csv_status = get_csv_upload_status(uow_csv, current_user.id, assembly_id)
        except Exception:  # noqa: S110
            pass  # No CSV data - expected for new assemblies

        # Determine data source
        data_source, _locked = determine_data_source(gsheet, csv_status, request.args.get("source", ""))

        # Tab enabled states
        targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(
            data_source, gsheet, csv_status
        )

        # Load the per-assembly field schema and pack it into display sections.
        # Empty groups are filtered out so the template renders only populated sections.
        uow_schema = bootstrap.bootstrap()
        grouped_schema = get_schema_grouped(uow_schema, current_user.id, assembly_id)
        schema_sections = [
            {"label": GROUP_LABELS[group], "fields": grouped_schema[group]}
            for group in GROUP_DISPLAY_ORDER
            if grouped_schema.get(group)
        ]

        return render_template(
            "backoffice/assembly_view_respondent.html",
            assembly=assembly,
            respondent=respondent,
            data_source=data_source,
            gsheet=gsheet,
            targets_enabled=targets_enabled,
            respondents_enabled=respondents_enabled,
            selection_enabled=selection_enabled,
            schema_sections=schema_sections,
            can_manage=can_manage,
            can_edit=can_edit,
            comment_authors=comment_authors,
        ), 200
    except RespondentNotFoundError as e:
        current_app.logger.warning(f"Respondent {respondent_id} not found in assembly {assembly_id}: {e}")
        flash(_("Respondent not found"), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View respondent error for respondent {respondent_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while loading the respondent"), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))


def _collect_bool_updates(form: Any, schema: list) -> dict[str, Any]:
    """Pull each fixed-field bool radio value out of the submitted form.

    Returns a dict suitable for splatting into update_respondent — only
    includes keys that were actually present in the schema.
    """
    updates: dict[str, Any] = {}
    schema_by_key = {f.field_key: f for f in schema}
    for field_name in ("eligible", "can_attend", "consent", "stay_on_db"):
        field_def = schema_by_key.get(field_name)
        if field_def is None or field_def.effective_field_type != FieldType.BOOL_OR_NONE:
            continue
        raw = form[field_name].data if field_name in form else None
        updates[field_name] = radio_or_none_to_bool(raw)
    return updates


def _collect_attribute_updates(form: Any, schema: list) -> dict[str, Any]:
    """Build the attributes dict from attr_* form fields."""
    attrs: dict[str, Any] = {}
    for field_def in schema:
        if field_def.is_fixed or field_def.is_derived:
            continue
        effective = field_def.effective_field_type
        form_name = f"{ATTR_FIELD_PREFIX}{field_def.field_key}"
        if form_name not in form:
            continue
        raw = form[form_name].data
        if effective == FieldType.BOOL:
            attrs[field_def.field_key] = "true" if radio_to_bool(raw) else "false"
        elif effective == FieldType.BOOL_OR_NONE:
            coerced = radio_or_none_to_bool(raw)
            attrs[field_def.field_key] = "" if coerced is None else ("true" if coerced else "false")
        elif effective == FieldType.INTEGER:
            attrs[field_def.field_key] = "" if raw is None else str(raw)
        elif effective in CHOICE_TYPES:
            attrs[field_def.field_key] = raw or ""
        else:
            attrs[field_def.field_key] = raw or ""
    return attrs


def _edit_respondent_post(
    form: Any,
    schema: list,
    assembly_id: uuid.UUID,
    respondent_id: uuid.UUID,
) -> ResponseReturnValue | None:
    """Handle the POST branch of edit_respondent. Returns a response or None to re-render."""
    kwargs: dict[str, Any] = {}
    if "email" in form:
        kwargs["email"] = form["email"].data or ""
    else:
        kwargs["email"] = _RESPONDENT_UNSET
    kwargs.update(_collect_bool_updates(form, schema))
    attribute_updates = _collect_attribute_updates(form, schema)
    try:
        update_respondent(
            uow=bootstrap.bootstrap(),
            user_id=current_user.id,
            assembly_id=assembly_id,
            respondent_id=respondent_id,
            comment=form["comment"].data or "",
            attributes=attribute_updates,
            **kwargs,
        )
    except ValueError as e:
        flash(str(e), "error")
        return None
    except InsufficientPermissions:
        flash(_("You don't have permission to edit respondents"), "error")
        return redirect(url_for("respondents.view_respondent", assembly_id=assembly_id, respondent_id=respondent_id))
    flash(_("Respondent updated."), "success")
    return redirect(url_for("respondents.view_respondent", assembly_id=assembly_id, respondent_id=respondent_id))


@respondents_bp.route(
    "/assembly/<uuid:assembly_id>/respondents/<uuid:respondent_id>/edit",
    methods=["GET", "POST"],
)
@login_required
def edit_respondent(assembly_id: uuid.UUID, respondent_id: uuid.UUID) -> ResponseReturnValue:  # noqa: C901
    """Edit respondent attributes with a required change-note comment."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            viewer = uow.users.get(current_user.id)
            assembly_obj = uow.assemblies.get(assembly_id)
            if not (viewer and assembly_obj and can_edit_respondent(viewer, assembly_obj)):
                flash(_("You don't have permission to edit respondents"), "error")
                return redirect(
                    url_for("respondents.view_respondent", assembly_id=assembly_id, respondent_id=respondent_id)
                )

        respondent = get_respondent(bootstrap.bootstrap(), current_user.id, assembly_id, respondent_id)
        if respondent.selection_status == RespondentStatus.DELETED:
            flash(_("Cannot edit a deleted respondent"), "error")
            return redirect(
                url_for("respondents.view_respondent", assembly_id=assembly_id, respondent_id=respondent_id)
            )

        schema = get_schema(bootstrap.bootstrap(), current_user.id, assembly_id)
        form, warnings = build_edit_respondent_form(schema, respondent)

        if request.method == "POST" and form.validate_on_submit():
            response = _edit_respondent_post(form, schema, assembly_id, respondent_id)
            if response is not None:
                return response

        for warning in warnings:
            flash(warning, "warning")

        grouped_schema = get_schema_grouped(bootstrap.bootstrap(), current_user.id, assembly_id)
        ordered_sections = []
        for group in GROUP_DISPLAY_ORDER:
            fields_in_group = [f for f in grouped_schema.get(group, []) if not f.is_derived]
            if fields_in_group:
                ordered_sections.append({"label": GROUP_LABELS[group], "fields": fields_in_group})

        return render_template(
            "backoffice/assembly_edit_respondent.html",
            assembly=assembly,
            respondent=respondent,
            form=form,
            ordered_sections=ordered_sections,
            attr_prefix=ATTR_FIELD_PREFIX,
        ), 200
    except RespondentNotFoundError:
        flash(_("Respondent not found"), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
